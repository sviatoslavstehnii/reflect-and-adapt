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
    import os
    # Both gateways share ~/.openclaw as default workspace; read from there.
    shared_dir = os.path.expanduser("~/.openclaw")
    # Load all experiment sessions once, then split by arm prefix in session_id.
    df_all = get_scores(shared_dir, session_id="agent:main:exp-")
    if df_all.empty:
        print("No experiment scores found in shared ~/.openclaw DB.")
        return

    for arm_name, arm_cfg in arms_config.items():
        arm_prefix = arm_name[:4]  # "cont" or "trea"
        df = df_all[df_all["session_id"].str.contains(f"-{arm_prefix}-", regex=False)].copy()
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

    # Parse session metadata from session_id: agent:main:exp-{persona}-{arm4}-{scenario}-{uuid8}
    def parse_session_id(sid: str) -> tuple[str, str]:
        prefix = "agent:main:exp-"
        try:
            if sid.startswith(prefix):
                tail = sid[len(prefix):]  # "sofia-trea-s01_video_script-abc12345"
                parts = tail.split("-")   # ["sofia", "trea", "s01_video_script", "abc12345"]
                persona = parts[0]
                scenario = "-".join(parts[2:-1])  # skip arm (parts[1]) and uuid (last)
            else:
                persona, scenario = "unknown", "unknown"
        except (ValueError, IndexError):
            persona, scenario = "unknown", "unknown"
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
