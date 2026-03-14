#!/usr/bin/env python3
"""
Aggregates evaluation scores from both arm databases into results/scores.csv.

Usage: python analysis/collect.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.metrics import get_scores

EXPERIMENTS_DIR = Path(__file__).parent.parent
CONFIG_PATH = EXPERIMENTS_DIR / "config" / "experiment.yaml"
RESULTS_DIR = EXPERIMENTS_DIR / "results"


def main() -> None:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    arms_config = config["arms"]
    RESULTS_DIR.mkdir(exist_ok=True)

    frames = []
    for arm_name, arm_cfg in arms_config.items():
        import os
        openclaw_dir = os.path.expanduser(arm_cfg["openclaw_dir"])
        df = get_scores(openclaw_dir)
        if df.empty:
            print(f"[{arm_name}] No scores found.")
            continue
        df["arm"] = arm_name
        frames.append(df)
        print(f"[{arm_name}] {len(df)} score rows loaded.")

    if not frames:
        print("No data collected. Did the experiment run?")
        return

    combined = pd.concat(frames, ignore_index=True)

    # Parse session metadata from session_id: agent:main:exp-{persona}-{arm}-{scenario}-{uuid}
    def parse_session_id(sid: str) -> tuple[str, str, str]:
        parts = sid.split("-")
        # Format: exp-{persona}-{arm4}-{scenario_id}-{uuid8}
        try:
            exp_idx = parts.index("exp")
            persona = parts[exp_idx + 1]
            scenario = "-".join(parts[exp_idx + 3:-1])  # everything between arm4 and uuid8
        except (ValueError, IndexError):
            persona = "unknown"
            scenario = "unknown"
        return persona, scenario

    combined[["persona", "scenario"]] = combined["session_id"].apply(
        lambda s: pd.Series(parse_session_id(s))
    )

    # Extract scenario number (s01, s02, ...) for ordering
    combined["session_num"] = combined["scenario"].str.extract(r"(s\d+)")[0]

    out_path = RESULTS_DIR / "scores.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(combined)} rows)")
    print(combined.groupby(["arm", "persona"])[["helpfulness", "conciseness"]].mean().round(2))


if __name__ == "__main__":
    main()
