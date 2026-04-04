"""
Runs a single scenario session or an approval session against one openclaw arm.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .client import OpenClawClient
from .metrics import get_last_cortex_run
from .simulator import UserSimulator

import re

log = logging.getLogger(__name__)


def _strip_agent_text(text: str) -> str:
    """Remove internal markup from agent responses before passing to simulator."""
    # Remove full <think>...</think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove stray <final> / </final> wrapper tags
    text = re.sub(r"</?final>", "", text)
    # Remove [[reply_to_current]] and similar internal directives
    text = re.sub(r"\[\[.*?\]\]", "", text)
    return text.strip()


@dataclass
class Turn:
    turn_number: int
    user_message: str
    agent_response: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SessionResult:
    session_key: str
    arm: str
    persona_id: str
    scenario_id: str
    turns: list[Turn] = field(default_factory=list)
    completed: bool = False
    error: Optional[str] = None


def _make_session_key(persona_id: str, arm: str, scenario_id: str) -> str:
    uid = str(uuid.uuid4())[:8]
    return f"agent:main:exp-{persona_id}-{arm[:4]}-{scenario_id}-{uid}"


def _prepare_workspace(
    openclaw_dir: str,
    scenario_dir: Path,
    workspace_files: list[str],
) -> None:
    """Copy scenario files into the arm's workspace/data directory."""
    data_dir = (
        Path(os.path.expanduser(openclaw_dir)) / "workspace" / "data"
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    # Clear previous session's data files
    for f in data_dir.iterdir():
        if f.is_file():
            f.unlink()
        elif f.is_dir():
            shutil.rmtree(f)

    # Run setup.py if present
    setup_py = scenario_dir / "setup.py"
    if setup_py.exists():
        log.info(f"Running setup.py for {scenario_dir.name}")
        subprocess.run(
            ["python3", str(setup_py), "--target", str(data_dir)],
            check=True,
        )

    # Copy static files (skip images if missing — they're optional for dry runs)
    for filename in workspace_files:
        if filename.startswith("#") or not filename.strip():
            continue
        # Strip inline comments
        clean_name = filename.split("#")[0].strip()
        src = scenario_dir / clean_name
        if src.exists():
            shutil.copy2(src, data_dir / clean_name)
            log.info(f"Copied {clean_name} → data/")
        else:
            log.warning(f"Workspace file not found (skipping): {src}")


async def run_session(
    arm: str,
    openclaw_dir: str,
    port: int,
    persona: dict,
    scenario: dict,
    scenario_dir: Path,
    max_turns: int = 12,
    silence_timeout_s: float = 15.0,
) -> SessionResult:
    """Drive a full multi-turn scenario session. Returns SessionResult."""
    from .simulator_memory import load as load_memory, update_from_session

    persona_id = persona["id"]
    scenario_id = scenario["id"]
    session_key = _make_session_key(persona_id, arm, scenario_id)

    result = SessionResult(
        session_key=session_key,
        arm=arm,
        persona_id=persona_id,
        scenario_id=scenario_id,
    )

    # Prepare workspace files
    workspace_files = scenario.get("workspace_files", [])
    if workspace_files:
        _prepare_workspace(openclaw_dir, scenario_dir, workspace_files)

    # Load prior session memory so simulator doesn't re-explain what was already said
    prior_memory = load_memory(persona_id, arm)
    simulator = UserSimulator(persona, scenario, prior_memory=prior_memory)

    try:
        async with OpenClawClient(port, openclaw_dir, silence_timeout_s) as client:
            # Turn 1: opening prompt
            opening = simulator.opening_prompt
            log.info(f"[{arm}/{scenario_id}] Turn 1 → {opening[:80]}...")
            agent_response = await client.send_message(session_key, opening)
            log.info(f"[{arm}/{scenario_id}] Agent: {agent_response[:100]}...")

            result.turns.append(Turn(1, opening, agent_response))
            agent_text = _strip_agent_text(agent_response)
            simulator.record_agent_response(
                agent_text or "(the agent is working on it — no visible reply yet)"
            )

            # Subsequent turns
            for turn_n in range(2, max_turns + 1):
                next_msg = await simulator.next_message()
                if next_msg is None:
                    log.info(f"[{arm}/{scenario_id}] Simulator signalled task complete at turn {turn_n}.")
                    result.completed = True
                    break

                log.info(f"[{arm}/{scenario_id}] Turn {turn_n} → {next_msg[:80]}...")
                agent_response = await client.send_message(session_key, next_msg)
                log.info(f"[{arm}/{scenario_id}] Agent: {agent_response[:100]}...")

                result.turns.append(Turn(turn_n, next_msg, agent_response))
                agent_text = _strip_agent_text(agent_response)
                simulator.record_agent_response(
                    agent_text or "(the agent is working on it — no visible reply yet)"
                )
            else:
                log.warning(f"[{arm}/{scenario_id}] Reached max_turns ({max_turns}) without completion.")
                result.completed = True

    except Exception as e:
        result.error = str(e)
        log.error(f"[{arm}/{scenario_id}] Session error: {e}", exc_info=True)

    # Update simulator memory with what the user communicated this session
    if result.turns:
        try:
            update_from_session(persona_id, arm, scenario_id, result.turns)
        except Exception as e:
            log.warning(f"[sim-memory] Update failed: {e}")

    return result


async def wait_for_cortex(
    openclaw_dir: str,
    t0: datetime,
    poll_interval_s: float = 3.0,
    timeout_s: float = 90.0,
) -> bool:
    """
    Poll the state table until lastCortexRun > t0.
    Returns True if Cortex completed, False on timeout.
    """
    t0_iso = t0.isoformat()
    deadline = asyncio.get_event_loop().time() + timeout_s

    while asyncio.get_event_loop().time() < deadline:
        last_run = get_last_cortex_run(openclaw_dir)
        if last_run and last_run > t0_iso:
            log.info(f"Cortex completed at {last_run}")
            return True
        await asyncio.sleep(poll_interval_s)

    log.warning("Cortex did not complete within timeout — proceeding anyway.")
    return False


async def run_approval_session(
    arm: str,
    openclaw_dir: str,
    port: int,
    persona_id: str,
    approval_prompt: str,
    silence_timeout_s: float = 15.0,
) -> bool:
    """
    Run a dedicated session for approving PENDING proposals.
    The before_agent_start hook will inject them automatically.
    Returns True on success.
    """
    session_key = _make_session_key(persona_id, arm, "approval")
    log.info(f"[{arm}] Running approval session: {session_key}")

    try:
        async with OpenClawClient(port, openclaw_dir, silence_timeout_s) as client:
            response = await client.send_message(session_key, approval_prompt)
            log.info(f"[{arm}] Approval response: {response[:200]}...")
        return True
    except Exception as e:
        log.error(f"[{arm}] Approval session error: {e}", exc_info=True)
        return False
