"""
ArmRunner — drives a full S1→S10 sequence for one persona on one arm.

Responsibilities:
  - Load persona + all scenarios in order
  - Run each scenario session
  - After session >= approval_after_index in treatment arm: wait for Cortex, then run approval
  - Collect results
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .session import SessionResult, run_approval_session, run_session, wait_for_cortex

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
        arm: "control" or "treatment"
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

    for i, scenario in enumerate(scenarios):
        scenario_id = scenario["id"]
        scenario_dir = scenarios_base_dir / scenario_id

        if dry_run:
            approval_note = ""
            if arm == "treatment" and i >= approval_after:
                approval_note = " [+ approval session]"
            log.info(f"[DRY RUN] [{arm}/{persona_id}] Session {i+1}: {scenario_id}{approval_note}")
            continue

        log.info(f"[{arm}/{persona_id}] === Session {i+1}/{len(scenarios)}: {scenario_id} ===")
        t0 = datetime.now(timezone.utc)

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

        # After S3+ in treatment: wait for Cortex, then run approval
        if arm == "treatment" and i >= approval_after:
            log.info(f"[{arm}/{persona_id}] Waiting for Cortex to complete...")
            await wait_for_cortex(
                openclaw_dir=openclaw_dir,
                t0=t0,
                poll_interval_s=config.get("cortex_poll_interval_s", 3.0),
                timeout_s=config.get("cortex_poll_timeout_s", 90.0),
            )

            approval_prompt = config.get("approval_prompt", "Please apply all pending proposals.")
            await run_approval_session(
                arm=arm,
                openclaw_dir=openclaw_dir,
                port=port,
                persona_id=persona_id,
                approval_prompt=approval_prompt,
                silence_timeout_s=config.get("turn_silence_timeout_s", 15.0),
            )

        # Small pause between sessions to avoid overwhelming openclaw
        await asyncio.sleep(2.0)

    return result
