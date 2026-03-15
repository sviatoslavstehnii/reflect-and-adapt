#!/usr/bin/env python3
"""
Generates charts from results/scores.csv.

Saves to results/plots/:
  - helpfulness_over_sessions.png   — treatment vs control, per persona
  - metrics_summary.png             — bar chart of all metrics, final 3 sessions
  - score_distribution.png          — violin plots, treatment vs control

Usage: python analysis/plot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

EXPERIMENTS_DIR = Path(__file__).parent.parent
RESULTS_DIR = EXPERIMENTS_DIR / "results"
PLOTS_DIR = RESULTS_DIR / "plots"

SESSION_ORDER = ["s01", "s02", "s03", "s04", "s05", "s06", "s07", "s08", "s09", "s10"]
METRICS = ["helpfulness", "conciseness", "task_completed", "response_accepted", "format_match"]


def load() -> pd.DataFrame:
    path = RESULTS_DIR / "scores.csv"
    if not path.exists():
        print(f"scores.csv not found at {path}. Run collect.py first.")
        sys.exit(1)
    df = pd.read_csv(path)
    # Normalise session_num ordering
    df["session_num"] = pd.Categorical(df["session_num"], categories=SESSION_ORDER, ordered=True)
    return df


def helpfulness_over_sessions(df: pd.DataFrame) -> None:
    personas = df["persona"].dropna().unique()
    fig, axes = plt.subplots(
        1, len(personas), figsize=(6 * len(personas), 4), squeeze=False
    )
    fig.suptitle("Helpfulness over Sessions: Treatment vs Control", fontsize=14)

    for ax, persona in zip(axes[0], personas):
        subset = df[df["persona"] == persona]
        for arm, style in [("treatment", "-o"), ("control", "--s")]:
            arm_data = subset[subset["arm"] == arm]
            if arm_data.empty:
                continue
            avg = arm_data.groupby("session_num", observed=True)["helpfulness"].mean()
            ax.plot(avg.index.astype(str), avg.values, style, label=arm, linewidth=2)
        ax.set_title(persona)
        ax.set_xlabel("Session")
        ax.set_ylabel("Avg Helpfulness (1–5)")
        ax.set_ylim(1, 5)
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    _save("helpfulness_over_sessions.png")


def metrics_summary(df: pd.DataFrame) -> None:
    """Bar chart comparing treatment vs control on final 3 sessions (or all if fewer)."""
    late_sessions = SESSION_ORDER[-3:]
    late = df[df["session_num"].isin(late_sessions)]
    if late.empty:
        late = df  # fall back to all available sessions

    numeric_metrics = ["helpfulness", "conciseness", "task_completed", "response_accepted", "format_match"]
    available = [m for m in numeric_metrics if m in late.columns]

    summary = late.groupby("arm")[available].mean()

    fig, ax = plt.subplots(figsize=(10, 5))
    summary.T.plot(kind="bar", ax=ax, rot=0)
    ax.set_title("Metric Averages — Final 3 Sessions (S08–S10)")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 5)
    ax.legend(title="Arm")
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    _save("metrics_summary.png")


def score_distribution(df: pd.DataFrame) -> None:
    """Violin plots of helpfulness distribution by arm."""
    fig, ax = plt.subplots(figsize=(7, 4))

    arms = df["arm"].unique()
    data_by_arm = [df[df["arm"] == a]["helpfulness"].dropna().values for a in arms]

    parts = ax.violinplot(data_by_arm, positions=range(len(arms)), showmedians=True)
    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels(arms)
    ax.set_ylabel("Helpfulness (1–5)")
    ax.set_title("Helpfulness Distribution: Treatment vs Control")
    ax.set_ylim(0.5, 5.5)
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    _save("score_distribution.png")


def _save(filename: str) -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLOTS_DIR / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def main() -> None:
    df = load()
    print(f"Loaded {len(df)} rows. Personas: {df['persona'].unique()}")

    helpfulness_over_sessions(df)
    metrics_summary(df)
    score_distribution(df)

    print("Done.")


if __name__ == "__main__":
    main()
