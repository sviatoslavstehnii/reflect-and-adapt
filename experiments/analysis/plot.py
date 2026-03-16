#!/usr/bin/env python3
"""
Generates charts from results/sessions.csv (session-level aggregates).

Saves to results/plots/:
  helpfulness_over_sessions.png     — adaptive vs baseline, per persona
  friction_over_sessions.png        — correction_rate + frustration_rate over sessions
  satisfaction_over_sessions.png    — user satisfaction trend
  turns_per_session.png             — turns needed to complete task (shorter = more efficient)
  personalization_hit_rate.png      — % turns where agent used unprompted user knowledge
  metrics_summary.png               — bar chart of key metrics, final 3 sessions

Usage: python analysis/plot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

EXPERIMENTS_DIR = Path(__file__).parent.parent
RESULTS_DIR = EXPERIMENTS_DIR / "results"
PLOTS_DIR = RESULTS_DIR / "plots"

SESSION_ORDER = ["s01", "s02", "s03", "s04", "s05", "s06", "s07", "s08", "s09", "s10"]
ARM_STYLES = {"adaptive": ("-o", "#2196F3"), ("baseline"): ("--s", "#9E9E9E")}


def load() -> pd.DataFrame:
    path = RESULTS_DIR / "sessions.csv"
    if not path.exists():
        # Fall back to raw scores.csv and recompute session aggregates
        raw_path = RESULTS_DIR / "scores.csv"
        if not raw_path.exists():
            print("Neither sessions.csv nor scores.csv found. Run collect.py first.")
            sys.exit(1)
        print("sessions.csv not found — falling back to scores.csv")
        return _aggregate_from_scores(pd.read_csv(raw_path))
    df = pd.read_csv(path)
    df["session_num"] = pd.Categorical(df["session_num"], categories=SESSION_ORDER, ordered=True)
    return df


def _aggregate_from_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute session-level aggregates from raw turn scores."""
    SATISFACTION_SCORE = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
    if "satisfaction_score" not in df.columns:
        df["satisfaction_score"] = df["user_satisfaction"].map(SATISFACTION_SCORE)
    turns_per = df.groupby("session_id").size().reset_index(name="turns_per_session")
    df = df.merge(turns_per, on="session_id", how="left")
    agg_funcs = {
        "helpfulness": "mean", "conciseness": "mean", "satisfaction_score": "mean",
        "correction_signal": "mean", "frustration_signal": "mean",
        "task_completed": "mean", "response_accepted": "mean",
        "format_match": "mean", "turns_per_session": "first",
    }
    if "personalization_hit" in df.columns:
        agg_funcs["personalization_hit"] = "mean"
    sessions = (
        df.groupby(["arm", "persona", "session_id", "session_num"])
        .agg(agg_funcs).reset_index()
        .rename(columns={"correction_signal": "correction_rate", "frustration_signal": "frustration_rate"})
    )
    sessions["session_num"] = pd.Categorical(sessions["session_num"], categories=SESSION_ORDER, ordered=True)
    return sessions


def _arm_style(arm: str) -> tuple[str, str]:
    return ARM_STYLES.get(arm, ("-o", "#795548"))


def _per_persona_line_chart(df, metric, ylabel, title, filename, ylim=None, pct=False):
    """Generic per-persona line chart, one subplot per persona."""
    personas = sorted(df["persona"].dropna().unique())
    fig, axes = plt.subplots(1, len(personas), figsize=(5.5 * len(personas), 4), squeeze=False)
    fig.suptitle(title, fontsize=13)

    for ax, persona in zip(axes[0], personas):
        subset = df[df["persona"] == persona]
        for arm in sorted(subset["arm"].unique()):
            style, color = _arm_style(arm)
            arm_data = subset[subset["arm"] == arm].sort_values("session_num")
            avg = arm_data.groupby("session_num", observed=True)[metric].mean()
            vals = avg.values * 100 if pct else avg.values
            ax.plot(avg.index.astype(str), vals, style, label=arm, color=color, linewidth=2, markersize=5)
        ax.set_title(persona, fontsize=11)
        ax.set_xlabel("Session")
        ax.set_ylabel(ylabel)
        if ylim:
            ax.set_ylim(*ylim)
        if pct:
            ax.yaxis.set_major_formatter(mticker.PercentFormatter())
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    _save(filename)


def helpfulness_over_sessions(df: pd.DataFrame) -> None:
    _per_persona_line_chart(
        df, "helpfulness", "Avg Helpfulness (1–5)",
        "Helpfulness over Sessions: Adaptive vs Baseline",
        "helpfulness_over_sessions.png", ylim=(1, 5),
    )


def satisfaction_over_sessions(df: pd.DataFrame) -> None:
    _per_persona_line_chart(
        df, "satisfaction_score", "Satisfaction (0=neg, 0.5=neutral, 1=pos)",
        "User Satisfaction over Sessions: Adaptive vs Baseline",
        "satisfaction_over_sessions.png", ylim=(0, 1),
    )


def friction_over_sessions(df: pd.DataFrame) -> None:
    """Correction rate + frustration rate per session — should fall for adaptive."""
    personas = sorted(df["persona"].dropna().unique())
    fig, axes = plt.subplots(2, len(personas), figsize=(5.5 * len(personas), 7), squeeze=False)
    fig.suptitle("Friction over Sessions: Correction & Frustration Rates", fontsize=13)

    for col, persona in enumerate(personas):
        subset = df[df["persona"] == persona]
        for metric, row, label in [
            ("correction_rate", 0, "Correction Rate"),
            ("frustration_rate", 1, "Frustration Rate"),
        ]:
            ax = axes[row][col]
            for arm in sorted(subset["arm"].unique()):
                style, color = _arm_style(arm)
                arm_data = subset[subset["arm"] == arm].sort_values("session_num")
                avg = arm_data.groupby("session_num", observed=True)[metric].mean()
                ax.plot(avg.index.astype(str), avg.values * 100, style, label=arm,
                        color=color, linewidth=2, markersize=5)
            if row == 0:
                ax.set_title(persona, fontsize=11)
            ax.set_ylabel(f"{label} (%)")
            ax.set_xlabel("Session")
            ax.set_ylim(0, 100)
            ax.yaxis.set_major_formatter(mticker.PercentFormatter())
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    _save("friction_over_sessions.png")


def turns_per_session(df: pd.DataFrame) -> None:
    """Turns needed per session — fewer turns over time = agent gets things right faster."""
    if "turns_per_session" not in df.columns:
        print("turns_per_session not in data — skipping chart.")
        return
    _per_persona_line_chart(
        df, "turns_per_session", "Avg Turns per Session",
        "Turns to Task Completion over Sessions\n(fewer = agent needs less back-and-forth)",
        "turns_per_session.png",
    )


def personalization_hit_rate(df: pd.DataFrame) -> None:
    """% of turns where agent used user-specific knowledge unprompted."""
    if "personalization_hit" not in df.columns:
        print("personalization_hit not in data — skipping chart.")
        return
    _per_persona_line_chart(
        df, "personalization_hit", "Personalization Hit Rate (%)",
        "Personalization Hit Rate over Sessions\n(agent uses user knowledge unprompted)",
        "personalization_hit_rate.png", ylim=(0, 100), pct=True,
    )


def metrics_summary(df: pd.DataFrame) -> None:
    """Bar chart comparing adaptive vs baseline on final 3 sessions (or all if fewer)."""
    late_sessions = SESSION_ORDER[-3:]
    late = df[df["session_num"].isin(late_sessions)]
    if late.empty:
        late = df

    candidates = [
        ("helpfulness", "Helpfulness\n(1–5 scale)"),
        ("satisfaction_score", "Satisfaction\n(0–1)"),
        ("correction_rate", "Correction\nRate"),
        ("frustration_rate", "Frustration\nRate"),
        ("response_accepted", "Response\nAccepted"),
        ("personalization_hit", "Personalization\nHit Rate"),
    ]
    available = [(col, label) for col, label in candidates if col in late.columns]
    cols = [c for c, _ in available]
    labels = [l for _, l in available]

    summary = late.groupby("arm")[cols].mean()

    fig, ax = plt.subplots(figsize=(max(10, len(cols) * 1.8), 5))
    x = range(len(cols))
    width = 0.35
    arms = list(summary.index)

    for i, arm in enumerate(arms):
        _, color = _arm_style(arm)
        offset = (i - len(arms) / 2 + 0.5) * width
        values = [summary.loc[arm, c] for c in cols]
        bars = ax.bar([xi + offset for xi in x], values, width, label=arm, color=color, alpha=0.85)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=8)

    ax.set_title("Metric Averages — Final 3 Sessions (S08–S10)", fontsize=13)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Score")
    ax.set_ylim(0, max(summary.max().max() * 1.2, 1.1))
    ax.legend(title="Arm")
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    _save("metrics_summary.png")


_current_plot_dir: Path = PLOTS_DIR


def _save(filename: str) -> None:
    _current_plot_dir.mkdir(parents=True, exist_ok=True)
    path = _current_plot_dir / filename
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


def main() -> None:
    global _current_plot_dir
    df = load()
    print(f"Loaded {len(df)} sessions. Personas: {sorted(df['persona'].unique())}")

    personas = sorted(df["persona"].unique())
    arms = sorted(df["arm"].unique())

    # Per-persona per-arm plots
    for persona in personas:
        for arm in arms:
            subset = df[(df["persona"] == persona) & (df["arm"] == arm)]
            if subset.empty:
                continue
            _current_plot_dir = PLOTS_DIR / persona / arm
            helpfulness_over_sessions(subset)
            satisfaction_over_sessions(subset)
            friction_over_sessions(subset)
            turns_per_session(subset)
            personalization_hit_rate(subset)

    # Combined cross-arm comparison plots (all personas, both arms)
    _current_plot_dir = PLOTS_DIR
    helpfulness_over_sessions(df)
    satisfaction_over_sessions(df)
    friction_over_sessions(df)
    turns_per_session(df)
    personalization_hit_rate(df)
    metrics_summary(df)

    print("Done.")


if __name__ == "__main__":
    main()
