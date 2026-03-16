#!/usr/bin/env python3
"""
Evaluation harness entrypoint.

Usage:
  python run_experiment.py                          # all personas, both arms
  python run_experiment.py --personas sofia marcus  # specific personas
  python run_experiment.py --arms treatment         # one arm only
  python run_experiment.py --dry-run                # print plan, no connections
  python run_experiment.py --personas sofia --arms treatment --scenario s01_video_script
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml

# Ensure experiments/ is on the path
sys.path.insert(0, str(Path(__file__).parent))

from harness.runner import run_arm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent
CONFIG_DIR = EXPERIMENTS_DIR / "config"
PERSONAS_DIR = EXPERIMENTS_DIR / "personas"
SCENARIOS_DIR = EXPERIMENTS_DIR / "scenarios"


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_persona(persona_id: str) -> dict:
    path = PERSONAS_DIR / f"{persona_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Persona not found: {path}")
    data = load_yaml(path)
    data["id"] = persona_id
    return data


def load_scenarios(persona_id: str, filter_scenario: str | None = None, max_scenarios: int | None = None) -> list[dict]:
    """Load all scenario.yaml files for a persona, sorted by scenario ID."""
    persona_scenarios_dir = SCENARIOS_DIR / persona_id
    if not persona_scenarios_dir.exists():
        raise FileNotFoundError(f"No scenarios directory for persona: {persona_id}")

    scenarios = []
    for scenario_dir in sorted(persona_scenarios_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        scenario_yaml = scenario_dir / "scenario.yaml"
        if not scenario_yaml.exists():
            continue
        data = load_yaml(scenario_yaml)
        if filter_scenario and not scenario_dir.name.startswith(filter_scenario):
            continue
        scenarios.append(data)

    if not scenarios:
        raise ValueError(f"No scenarios found for persona: {persona_id}")

    if max_scenarios:
        scenarios = scenarios[:max_scenarios]

    return scenarios


async def run_persona(
    persona_id: str,
    arms_config: dict,
    selected_arms: list[str],
    experiment_config: dict,
    filter_scenario: str | None,
    max_scenarios: int | None,
    dry_run: bool,
) -> None:
    persona = load_persona(persona_id)
    scenarios = load_scenarios(persona_id, filter_scenario, max_scenarios)
    scenarios_base_dir = SCENARIOS_DIR / persona_id

    log.info(f"Persona: {persona_id} | Scenarios: {len(scenarios)} | Arms: {selected_arms}")

    arm_tasks = []
    for arm_name in selected_arms:
        arm_cfg = arms_config[arm_name]
        openclaw_dir = os.path.expanduser(arm_cfg["openclaw_dir"])
        port = arm_cfg["port"]

        task = run_arm(
            arm=arm_name,
            openclaw_dir=openclaw_dir,
            port=port,
            persona=persona,
            scenarios=scenarios,
            scenarios_base_dir=scenarios_base_dir,
            config=experiment_config,
            dry_run=dry_run,
        )
        arm_tasks.append(task)

    # Run both arms concurrently
    results = await asyncio.gather(*arm_tasks, return_exceptions=True)

    for arm_name, result in zip(selected_arms, results):
        if isinstance(result, Exception):
            log.error(f"[{arm_name}/{persona_id}] Arm failed: {result}")
        else:
            total_turns = sum(len(s.turns) for s in result.sessions)
            log.info(f"[{arm_name}/{persona_id}] Done — {len(result.sessions)} sessions, {total_turns} total turns")


async def main(args: argparse.Namespace) -> None:
    experiment_config = load_yaml(CONFIG_DIR / "experiment.yaml")
    arms_config = experiment_config["arms"]

    # Determine which arms to run
    all_arms = list(arms_config.keys())
    if args.arms:
        selected_arms = [a for a in args.arms if a in arms_config]
        unknown = [a for a in args.arms if a not in arms_config]
        if unknown:
            log.warning(f"Unknown arms (ignored): {unknown}")
    else:
        selected_arms = all_arms

    if not selected_arms:
        log.error("No valid arms selected. Available: " + ", ".join(all_arms))
        sys.exit(1)

    # Determine which personas to run
    all_personas = experiment_config.get("personas", [])
    if args.personas:
        selected_personas = args.personas
    else:
        selected_personas = all_personas

    log.info(f"Experiment starting | Personas: {selected_personas} | Arms: {selected_arms}")
    if args.dry_run:
        log.info("DRY RUN — no connections will be made")

    for persona_id in selected_personas:
        await run_persona(
            persona_id=persona_id,
            arms_config=arms_config,
            selected_arms=selected_arms,
            experiment_config=experiment_config,
            filter_scenario=args.scenario,
            max_scenarios=args.max_scenarios,
            dry_run=args.dry_run,
        )

    log.info("Experiment complete.")
    if not args.dry_run:
        log.info("Run analysis: python analysis/collect.py && python analysis/plot.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the reflect-and-adapt evaluation experiment"
    )
    parser.add_argument(
        "--personas", nargs="+", metavar="PERSONA",
        help="Persona IDs to run (default: all from config)"
    )
    parser.add_argument(
        "--arms", nargs="+", choices=["baseline", "adaptive"],
        help="Arms to run (default: both)"
    )
    parser.add_argument(
        "--scenario", metavar="SCENARIO_ID",
        help="Run only scenarios matching this prefix (e.g. s01_video_script)"
    )
    parser.add_argument(
        "--max-scenarios", type=int, metavar="N", dest="max_scenarios",
        help="Run only the first N scenarios (e.g. --max-scenarios 4 runs s01–s04)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print session plan without connecting to openclaw"
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
