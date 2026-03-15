#!/usr/bin/env python3
"""
Aggregates evaluation scores from both arm databases into:
  results/scores.csv        — raw per-turn scores
  results/sessions.csv      — session-level aggregates (one row per session)

Usage: python analysis/collect.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.metrics import get_scores

EXPERIMENTS_DIR = Path(__file__).parent.parent
CONFIG_PATH = EXPERIMENTS_DIR / "config" / "experiment.yaml"
RESULTS_DIR = EXPERIMENTS_DIR / "results"

SATISFACTION_SCORE = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}


def parse_session_id(sid: str) -> tuple[str, str]:
    """Extract (persona, scenario) from agent:main:exp-{persona}-{arm4}-{scenario}-{uuid8}."""
    prefix = "agent:main:exp-"
    try:
        if sid.startswith(prefix):
            tail = sid[len(prefix):]
            parts = tail.split("-")
            persona = parts[0]
            scenario = "-".join(parts[2:-1])  # skip arm (parts[1]) and uuid (last)
        else:
            persona, scenario = "unknown", "unknown"
    except (ValueError, IndexError):
        persona, scenario = "unknown", "unknown"
    return persona, scenario


def main() -> None:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    arms_config = config["arms"]
    RESULTS_DIR.mkdir(exist_ok=True)

    frames = []
    shared_dir = os.path.expanduser("~/.openclaw")
    df_all = get_scores(shared_dir, session_id="agent:main:exp-")
    if df_all.empty:
        print("No experiment scores found.")
        return

    for arm_name, arm_cfg in arms_config.items():
        arm_prefix = arm_name[:4]  # "base" or "adap"
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

    # Parse session metadata
    combined[["persona", "scenario"]] = combined["session_id"].apply(
        lambda s: pd.Series(parse_session_id(s))
    )
    combined["session_num"] = combined["scenario"].str.extract(r"(s\d+)")[0]

    # Numeric satisfaction score
    combined["satisfaction_score"] = combined["user_satisfaction"].map(SATISFACTION_SCORE)

    # Save raw turn-level scores
    out_path = RESULTS_DIR / "scores.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path} ({len(combined)} rows)")

    # ── Session-level aggregates ──────────────────────────────────────────────
    # Group by the unique session key to get turns_per_session, then merge
    turns_per_session = (
        combined.groupby("session_id")
        .size()
        .reset_index(name="turns_per_session")
    )
    combined = combined.merge(turns_per_session, on="session_id", how="left")

    agg_funcs = {
        "helpfulness": "mean",
        "conciseness": "mean",
        "satisfaction_score": "mean",
        "correction_signal": "mean",   # correction_rate
        "frustration_signal": "mean",  # frustration_rate
        "task_completed": "mean",
        "response_accepted": "mean",
        "format_match": "mean",
        "turns_per_session": "first",  # same value for all rows in a session
    }
    if "personalization_hit" in combined.columns:
        agg_funcs["personalization_hit"] = "mean"

    sessions = (
        combined.groupby(["arm", "persona", "session_id", "session_num"])
        .agg(agg_funcs)
        .reset_index()
        .rename(columns={
            "correction_signal": "correction_rate",
            "frustration_signal": "frustration_rate",
        })
    )

    sessions_path = RESULTS_DIR / "sessions.csv"
    sessions.to_csv(sessions_path, index=False)
    print(f"Saved: {sessions_path} ({len(sessions)} sessions)")

    # Summary print
    print("\n── Avg scores by arm + persona ──")
    cols = ["helpfulness", "satisfaction_score", "correction_rate", "frustration_rate"]
    available = [c for c in cols if c in sessions.columns]
    print(sessions.groupby(["arm", "persona"])[available].mean().round(3))


if __name__ == "__main__":
    main()
