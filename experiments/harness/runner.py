"""
ArmRunner — drives a full S1→S10 sequence for one persona on one arm.

Responsibilities:
  - Load persona + all scenarios in order
  - Run each scenario session
  - After session >= approval_after_index in adaptive arm: run Cortex directly, then run approval
  - Collect results
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .session import SessionResult, run_approval_session, run_session

log = logging.getLogger(__name__)

SCENARIO_ORDER = [
    "s01", "s02", "s03", "s04", "s05",
    "s06", "s07", "s08", "s09", "s10",
]


@dataclass
class ArmResult:
    arm: str
    persona_id: str
    sessions: list[SessionResult] = field(default_factory=list)


WORKSPACE_TEMPLATES = Path(__file__).resolve().parents[1] / "config" / "workspace"


def reset_workspace_for_persona(persona_id: str, openclaw_dir: str, arm: str = "adaptive") -> None:
    """
    Reset the arm's openclaw workspace to a clean per-persona state before
    the first session. Copies default IDENTITY/SOUL/AGENTS and persona USER.md,
    and clears the vector memory DB so there's no cross-persona bleed.
    """
    workspace = Path(os.path.expanduser(openclaw_dir)) / "workspace"
    templates = WORKSPACE_TEMPLATES

    # Reset instruction files to defaults
    for fname in ("IDENTITY.md", "SOUL.md", "AGENTS.md"):
        src = templates / fname
        dst = workspace / fname
        if src.exists():
            shutil.copy2(src, dst)
            log.info(f"[reset] {fname} → default")

    # Reset USER.md to persona-specific template
    user_src = templates / "personas" / f"{persona_id}.md"
    if user_src.exists():
        shutil.copy2(user_src, workspace / "USER.md")
        log.info(f"[reset] USER.md → {persona_id}")
    else:
        log.warning(f"[reset] No persona template for {persona_id} — USER.md unchanged")

    # Clear MEMORY.md
    memory_file = workspace / "MEMORY.md"
    memory_file.write_text("# Memory\n\n_No memories yet._\n")
    log.info("[reset] MEMORY.md cleared")

    # Clear vector memory DB (truncate files/chunks tables, keep schema)
    mem_db = Path(os.path.expanduser(openclaw_dir)) / "memory" / "main.sqlite"
    if mem_db.exists():
        try:
            conn = sqlite3.connect(str(mem_db))
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM embedding_cache")
            conn.commit()
            conn.close()
            log.info("[reset] Vector memory DB cleared")
        except Exception as e:
            log.warning(f"[reset] Could not clear memory DB: {e}")

    # Remove daily memory files from previous persona
    mem_dir = workspace / "memory"
    if mem_dir.exists():
        for f in mem_dir.glob("*.md"):
            f.unlink()
        log.info("[reset] Daily memory files cleared")

    # Clear skills except manage-proposals (which is required for approval sessions)
    skills_dir = workspace / "skills"
    if skills_dir.exists():
        for entry in skills_dir.iterdir():
            if entry.name == "proposals":
                continue  # keep manage-proposals skill
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        log.info("[reset] Skills cleared (manage-proposals kept)")

    # Clear simulator memory so it starts fresh for this persona+arm
    sim_memory_file = RESULTS_DIR / "simulator_memory" / persona_id / f"{arm}.json"
    if sim_memory_file.exists():
        sim_memory_file.unlink()
        log.info("[reset] Simulator memory cleared")

    # Clear stale snapshots for this persona+arm so previous run data doesn't bleed through
    snapshot_dir = RESULTS_DIR / "snapshots" / persona_id / arm
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
        log.info(f"[reset] Snapshots cleared for {persona_id}/{arm}")

    # Plugin dir — used for reflect.db and memory.lance
    plugin_dir = (
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt"
    )

    # Clear reflect.db (proposals, scores, conversations) so stale proposals don't block the router
    reflect_db = plugin_dir / "reflect.db"
    if reflect_db.exists():
        try:
            conn = sqlite3.connect(str(reflect_db))
            conn.execute("DELETE FROM proposals")
            conn.execute("DELETE FROM scores")
            conn.execute("DELETE FROM conversations")
            conn.commit()
            conn.close()
            log.info("[reset] reflect.db cleared (proposals, scores, conversations)")
        except Exception as e:
            log.warning(f"[reset] Could not clear reflect.db: {e}")

    # Clear LanceDB vector memory (memory.lance in the arm's plugin dir)
    lance_db = plugin_dir / "memory.lance"
    if lance_db.exists():
        shutil.rmtree(lance_db)
        log.info("[reset] memory.lance cleared")

    # Sync plugin src/ from shared source so arm always runs latest code
    shared_plugin_src = Path.home() / ".openclaw" / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt" / "src"
    arm_plugin_src = plugin_dir / "src"
    if shared_plugin_src.exists():
        if arm_plugin_src.exists():
            shutil.rmtree(arm_plugin_src)
        shutil.copytree(shared_plugin_src, arm_plugin_src)
        log.info("[reset] Plugin src/ synced from shared source")

    log.info(f"[reset] Workspace ready for persona: {persona_id}")


async def _run_cortex(openclaw_dir: str) -> None:
    """Run the Cortex pipeline directly via node for the adaptive arm."""
    plugin_dir = (
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt"
    )
    cortex_script = plugin_dir / "src" / "cortex.js"
    if not cortex_script.exists():
        log.warning(f"[Cortex] Script not found at {cortex_script} — skipping.")
        return

    log.info(f"[Cortex] Running pipeline: node {cortex_script}")
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                ["node", str(cortex_script)],
                cwd=str(plugin_dir),
                capture_output=True,
                text=True,
                timeout=120,
            ),
        )
        for line in result.stdout.splitlines():
            log.info(f"[Cortex] {line}")
        if result.returncode != 0:
            log.warning(f"[Cortex] Exited {result.returncode}: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        log.warning("[Cortex] Timed out after 120s.")
    except Exception as e:
        log.warning(f"[Cortex] Failed: {e}")


def _approve_presented_proposals(openclaw_dir: str) -> int:
    """Mark all PRESENTED proposals as APPROVED after the approval session completes."""
    db_path = (
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db"
    )
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "UPDATE proposals SET status='APPROVED' WHERE status='PRESENTED'"
    ).rowcount
    conn.commit()
    conn.close()
    return count


def _get_pending_proposals(openclaw_dir: str) -> list[dict]:
    """Read all PENDING proposals from the adaptive arm's DB."""
    db_path = (
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db"
    )
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT id, proposal_type, target_file, proposed_change, rationale, risk_level "
        "FROM proposals WHERE status='PENDING' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "type": r[1], "file": r[2], "change": r[3], "rationale": r[4], "risk": r[5]}
        for r in rows
    ]


def _build_approval_prompt(proposals: list[dict], openclaw_dir: str) -> str:
    """Build a prompt with current file contents so the agent knows exactly what to edit."""
    workspace = Path(os.path.expanduser(openclaw_dir)) / "workspace"
    lines = [
        "You have workspace adaptation proposals to apply. "
        "For each proposal: (1) edit the file, then (2) run the approve command. Do both steps.\n"
    ]
    for i, p in enumerate(proposals, 1):
        target = workspace / p["file"]
        current = target.read_text().strip() if target.exists() else "(file does not exist — create it)"
        lines.append(f"## Proposal {i} (id: {p['id']}): {p['file']} [{p['type']}]")
        lines.append(f"Rationale: {p['rationale']}\n")
        lines.append(f"Change to apply:\n{p['change']}\n")
        lines.append(f"Current file content:\n```\n{current}\n```\n")
        lines.append(
            f"Steps:\n"
            f"1. Edit `{p['file']}` to incorporate the change above.\n"
            f"2. Run: node skills/proposals/manage-proposals.js approve {p['id']}\n"
        )

    lines.append(
        "Work through each proposal in order — edit the file, then approve it before moving to the next. "
        "After all are done, reply with exactly: "
        "'Done. Applied: " + ", ".join(p['file'] for p in proposals) + "'"
    )
    return "\n".join(lines)


RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

SNAPSHOT_FILES = ["IDENTITY.md", "USER.md", "AGENTS.md", "SOUL.md", "MEMORY.md"]


def _snapshot_workspace(persona_id: str, arm: str, scenario_id: str, openclaw_dir: str) -> None:
    """Save a copy of all workspace instruction files after each approval session."""
    workspace = Path(os.path.expanduser(openclaw_dir)) / "workspace"
    snapshot_dir = RESULTS_DIR / "snapshots" / persona_id / arm / scenario_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for fname in SNAPSHOT_FILES:
        src = workspace / fname
        if src.exists():
            shutil.copy2(src, snapshot_dir / fname)

    # Snapshot skills directory if any new skills were added
    skills_dir = workspace / "skills"
    if skills_dir.exists():
        skills_snapshot = snapshot_dir / "skills"
        if skills_snapshot.exists():
            shutil.rmtree(skills_snapshot)
        shutil.copytree(skills_dir, skills_snapshot)

    # Dump LanceDB memory entries to JSON — filtered to this arm's session prefix
    # memory.lance lives inside the arm's own plugin dir (not the shared source)
    plugin_dir = (
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt"
    )
    dump_script = plugin_dir / "src" / "dump-memories.js"
    if dump_script.exists():
        session_prefix = f"agent:main:exp-{persona_id}-{arm[:4]}"
        try:
            result = subprocess.run(
                ["node", str(dump_script), "--session-prefix", session_prefix],
                cwd=str(plugin_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                (snapshot_dir / "memories.json").write_text(result.stdout)
            else:
                log.warning(f"[snapshot] dump-memories.js error: {result.stderr[:200]}")
        except Exception as e:
            log.warning(f"[snapshot] Could not dump memories: {e}")

    log.info(f"[snapshot] Workspace state saved → {snapshot_dir.relative_to(RESULTS_DIR.parent)}")


async def run_arm(
    arm: str,
    openclaw_dir: str,
    port: int,
    persona: dict,
    scenarios: list[dict],
    scenarios_base_dir: Path,
    config: dict,
    dry_run: bool = False,
) -> ArmResult:
    """
    Run all scenarios for one persona on one arm sequentially.

    Args:
        arm: "baseline" or "adaptive"
        openclaw_dir: path to ~/.openclaw-{arm}
        port: openclaw WebSocket port
        persona: loaded persona dict
        scenarios: list of scenario dicts in S1→S10 order
        scenarios_base_dir: path to experiments/scenarios/{persona_id}/
        config: parsed experiment.yaml dict
        dry_run: if True, print plan without running anything
    """
    persona_id = persona["id"]
    result = ArmResult(arm=arm, persona_id=persona_id)
    approval_after = config.get("approval_after_session_index", 2)  # 0-based → after S3

    if not dry_run:
        reset_workspace_for_persona(persona_id, openclaw_dir, arm)

    for i, scenario in enumerate(scenarios):
        scenario_id = scenario["id"]
        scenario_dir = scenarios_base_dir / scenario_id

        if dry_run:
            approval_note = ""
            if arm == "adaptive" and i >= approval_after:
                approval_note = " [+ approval session]"
            log.info(f"[DRY RUN] [{arm}/{persona_id}] Session {i+1}: {scenario_id}{approval_note}")
            continue

        log.info(f"[{arm}/{persona_id}] === Session {i+1}/{len(scenarios)}: {scenario_id} ===")

        session_result = await run_session(
            arm=arm,
            openclaw_dir=openclaw_dir,
            port=port,
            persona=persona,
            scenario=scenario,
            scenario_dir=scenario_dir,
            max_turns=config.get("max_turns_per_session", 12),
            silence_timeout_s=config.get("turn_silence_timeout_s", 15.0),
        )
        result.sessions.append(session_result)

        # After approval_after index in adaptive arm: run Cortex directly, then approval
        if arm == "adaptive" and i >= approval_after:
            await _run_cortex(openclaw_dir)

            proposals = _get_pending_proposals(openclaw_dir)
            if proposals:
                log.info(f"[Cortex] {len(proposals)} pending proposal(s) — sending to agent for approval.")
                approval_prompt = _build_approval_prompt(proposals, openclaw_dir)
                await run_approval_session(
                    arm=arm,
                    openclaw_dir=openclaw_dir,
                    port=port,
                    persona_id=persona_id,
                    approval_prompt=approval_prompt,
                    silence_timeout_s=config.get("turn_silence_timeout_s", 15.0),
                )
                approved = _approve_presented_proposals(openclaw_dir)
                if approved:
                    log.info(f"[Cortex] Marked {approved} presented proposal(s) as APPROVED.")
            else:
                log.info("[Cortex] No pending proposals — skipping approval session.")

            # Always snapshot after Cortex (captures state even when no approval ran)
            _snapshot_workspace(persona_id, arm, scenario_id, openclaw_dir)

        # Small pause between sessions to avoid overwhelming openclaw
        await asyncio.sleep(2.0)

    return result
