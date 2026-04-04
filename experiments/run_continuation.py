#!/usr/bin/env python3
"""
Continuation experiment — Arm A:
  Load the s10 adaptive snapshot (already-adapted workspace) and run
  10 more sessions with Cortex still enabled, to measure whether
  adaptation keeps compounding after the initial 10-session run.

Results are written to results/continuation/ to avoid polluting the
original experiment data.

Usage:
  python run_continuation.py --persona marcus
  python run_continuation.py --persona marcus --dry-run
  python run_continuation.py --persona olena --max-scenarios 5
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from harness.runner import (
    RESULTS_DIR,
    WORKSPACE_TEMPLATES,
    _approve_presented_proposals,
    _build_approval_prompt,
    _get_pending_proposals,
    _run_cortex,
)
from harness.session import run_approval_session, run_session, SessionResult
from dataclasses import dataclass, field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent
SNAPSHOTS_DIR = RESULTS_DIR / "snapshots"
CONTINUATION_RESULTS_DIR = RESULTS_DIR / "continuation"

ARM = "adaptive"
PORT = 3101
OPENCLAW_DIR = os.path.expanduser("~/.openclaw-adaptive")


# ── Snapshot-based workspace reset ───────────────────────────────────────────

def reset_workspace_from_snapshot(persona_id: str, openclaw_dir: str) -> None:
    """
    Reset the adaptive workspace to the state captured at the end of
    the original 10-session run (s10 snapshot), rather than blank templates.
    """
    # Find the s10 snapshot directory for this persona
    snapshot_root = SNAPSHOTS_DIR / persona_id / ARM
    s10_dirs = sorted(d for d in snapshot_root.iterdir() if d.name.startswith("s10"))
    if not s10_dirs:
        raise FileNotFoundError(
            f"No s10 snapshot found for {persona_id}/{ARM} — "
            f"run the original experiment first."
        )
    snapshot_dir = s10_dirs[-1]
    log.info(f"[reset] Loading s10 snapshot: {snapshot_dir.name}")

    workspace = Path(os.path.expanduser(openclaw_dir)) / "workspace"

    # Restore workspace instruction files from snapshot
    for fname in ("IDENTITY.md", "SOUL.md", "AGENTS.md", "USER.md", "MEMORY.md"):
        src = snapshot_dir / fname
        if src.exists():
            shutil.copy2(src, workspace / fname)
            log.info(f"[reset] {fname} ← snapshot")
        else:
            # Fall back to template for any missing file
            tmpl = WORKSPACE_TEMPLATES / fname
            if tmpl.exists():
                shutil.copy2(tmpl, workspace / fname)
                log.warning(f"[reset] {fname} not in snapshot — using template")

    # Restore skills from snapshot (excluding proposals which is required)
    skills_dst = workspace / "skills"
    skills_src = snapshot_dir / "skills"
    if skills_src.exists():
        for entry in skills_dst.iterdir():
            if entry.name == "proposals":
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        for entry in skills_src.iterdir():
            if entry.name == "proposals":
                continue
            dst = skills_dst / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dst)
            else:
                shutil.copy2(entry, dst)
        log.info("[reset] Skills restored from snapshot")

    plugin_dir = (
        Path(os.path.expanduser(openclaw_dir))
        / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt"
    )

    # Clear reflect.db for a fresh evaluation slate
    reflect_db = plugin_dir / "reflect.db"
    if reflect_db.exists():
        try:
            conn = sqlite3.connect(str(reflect_db))
            conn.execute("DELETE FROM proposals")
            conn.execute("DELETE FROM scores")
            conn.execute("DELETE FROM conversations")
            conn.commit()
            conn.close()
            log.info("[reset] reflect.db cleared")
        except Exception as e:
            log.warning(f"[reset] Could not clear reflect.db: {e}")

    # Clear LanceDB — start fresh (the distilled context is in the text files)
    lance_db = plugin_dir / "memory.lance"
    if lance_db.exists():
        shutil.rmtree(lance_db)
        log.info("[reset] memory.lance cleared")

    # Clear vector memory DB
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

    # Clear simulator memory for a clean simulation run
    sim_memory_file = RESULTS_DIR / "simulator_memory" / persona_id / f"continuation.json"
    if sim_memory_file.exists():
        sim_memory_file.unlink()
        log.info("[reset] Simulator memory cleared")

    # Sync plugin src/ from shared source
    shared_src = Path.home() / ".openclaw" / "workspace" / ".openclaw" / "extensions" / "reflect-and-adapt" / "src"
    arm_src = plugin_dir / "src"
    if shared_src.exists():
        if arm_src.exists():
            shutil.rmtree(arm_src)
        shutil.copytree(shared_src, arm_src)
        log.info("[reset] Plugin src/ synced")

    log.info(f"[reset] Workspace ready for continuation run: {persona_id}")


# ── Override snapshot to write into continuation/ subdir ─────────────────────

def _snapshot_continuation(persona_id: str, scenario_id: str, openclaw_dir: str) -> None:
    """Same as _snapshot_workspace but writes to results/continuation/snapshots/."""
    workspace = Path(os.path.expanduser(openclaw_dir)) / "workspace"
    snapshot_dir = CONTINUATION_RESULTS_DIR / "snapshots" / persona_id / scenario_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for fname in ("IDENTITY.md", "USER.md", "AGENTS.md", "SOUL.md", "MEMORY.md"):
        src = workspace / fname
        if src.exists():
            shutil.copy2(src, snapshot_dir / fname)

    skills_dir = workspace / "skills"
    if skills_dir.exists():
        skills_snap = snapshot_dir / "skills"
        if skills_snap.exists():
            shutil.rmtree(skills_snap)
        shutil.copytree(skills_dir, skills_snap)

    log.info(f"[snapshot] Continuation state saved → continuation/snapshots/{persona_id}/{scenario_id}")


# ── Run loop ──────────────────────────────────────────────────────────────────

@dataclass
class ContinuationResult:
    persona_id: str
    sessions: list[SessionResult] = field(default_factory=list)


async def run_continuation(
    persona: dict,
    scenarios: list[dict],
    scenarios_base_dir: Path,
    config: dict,
    dry_run: bool = False,
    skip_reset: bool = False,
) -> ContinuationResult:
    persona_id = persona["id"]
    result = ContinuationResult(persona_id=persona_id)
    approval_after = config.get("approval_after_session_index", 0)

    if not dry_run and not skip_reset:
        # Back up sessions.csv before reset clears the adaptive DB
        sessions_csv = RESULTS_DIR / "sessions.csv"
        sessions_bak = RESULTS_DIR / "sessions.csv.bak"
        if sessions_csv.exists():
            shutil.copy2(sessions_csv, sessions_bak)
            log.info(f"[backup] sessions.csv → sessions.csv.bak")
        reset_workspace_from_snapshot(persona_id, OPENCLAW_DIR)
    elif skip_reset:
        log.info(f"[resume] Skipping workspace reset — continuing from existing state")
    else:
        log.info(f"[DRY RUN] Would reset workspace from s10 snapshot for {persona_id}")

    for i, scenario in enumerate(scenarios):
        scenario_id = scenario["id"]
        scenario_dir = scenarios_base_dir / scenario_id

        if dry_run:
            approval_note = " [+ Cortex + approval]" if i >= approval_after else ""
            log.info(f"[DRY RUN] [continuation/{persona_id}] Session {i+1}: {scenario_id}{approval_note}")
            continue

        log.info(f"[continuation/{persona_id}] === Session {i+1}/{len(scenarios)}: {scenario_id} ===")

        session_result = await run_session(
            arm="continuation",
            openclaw_dir=OPENCLAW_DIR,
            port=PORT,
            persona=persona,
            scenario=scenario,
            scenario_dir=scenario_dir,
            max_turns=config.get("max_turns_per_session", 12),
            silence_timeout_s=config.get("turn_silence_timeout_s", 15.0),
        )
        result.sessions.append(session_result)

        if i >= approval_after:
            await _run_cortex(OPENCLAW_DIR)

            proposals = _get_pending_proposals(OPENCLAW_DIR)
            if proposals:
                log.info(f"[Cortex] {len(proposals)} pending proposal(s) — sending to agent for approval.")
                approval_prompt = _build_approval_prompt(proposals, OPENCLAW_DIR)
                await run_approval_session(
                    arm="continuation",
                    openclaw_dir=OPENCLAW_DIR,
                    port=PORT,
                    persona_id=persona_id,
                    approval_prompt=approval_prompt,
                    silence_timeout_s=config.get("turn_silence_timeout_s", 15.0),
                )
                approved = _approve_presented_proposals(OPENCLAW_DIR)
                if approved:
                    log.info(f"[Cortex] Marked {approved} proposal(s) as APPROVED.")
            else:
                log.info("[Cortex] No pending proposals.")

            _snapshot_continuation(persona_id, scenario_id, OPENCLAW_DIR)

        await asyncio.sleep(2.0)

    return result


# ── Entry point ───────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


async def main(args: argparse.Namespace) -> None:
    config = load_yaml(EXPERIMENTS_DIR / "config" / "experiment.yaml")
    persona_data = load_yaml(EXPERIMENTS_DIR / "personas" / f"{args.persona}.yaml")
    persona_data["id"] = args.persona

    persona_scenarios_dir = EXPERIMENTS_DIR / "scenarios" / args.persona
    scenarios = []
    for d in sorted(persona_scenarios_dir.iterdir()):
        if not d.is_dir():
            continue
        syaml = d / "scenario.yaml"
        if syaml.exists():
            scenarios.append(load_yaml(syaml))

    if args.max_scenarios:
        scenarios = scenarios[:args.max_scenarios]

    if args.skip_scenarios:
        scenarios = scenarios[args.skip_scenarios:]

    log.info(f"Continuation run | persona={args.persona} | scenarios={len(scenarios)} | arm=adaptive (s10 snapshot)")
    if args.dry_run:
        log.info("DRY RUN — no connections will be made")

    result = await run_continuation(
        persona=persona_data,
        scenarios=scenarios,
        scenarios_base_dir=persona_scenarios_dir,
        config=config,
        dry_run=args.dry_run,
        skip_reset=args.skip_scenarios > 0,
    )

    if not args.dry_run:
        total_turns = sum(len(s.turns) for s in result.sessions)
        log.info(f"Done — {len(result.sessions)} sessions, {total_turns} total turns")
        log.info(f"Snapshots at: results/continuation/snapshots/{args.persona}/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuation experiment — Arm A (s10 snapshot + ongoing Cortex)")
    parser.add_argument("--persona", required=True, choices=["marcus", "aisha", "olena", "sofia"],
                        help="Persona to run")
    parser.add_argument("--max-scenarios", type=int, metavar="N", dest="max_scenarios",
                        help="Run only the first N scenarios")
    parser.add_argument("--skip-scenarios", type=int, metavar="N", dest="skip_scenarios", default=0,
                        help="Skip the first N scenarios (resume mode — also skips workspace reset)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without connecting to openclaw")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
