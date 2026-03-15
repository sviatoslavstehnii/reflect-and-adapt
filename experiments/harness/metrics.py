"""
Reads evaluation scores from the plugin's reflect.db SQLite database.

DB path: <openclaw_dir>/workspace/.openclaw/extensions/reflect-and-adapt/reflect.db
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd


def _db_path(openclaw_dir: str) -> Path | None:
    """Find reflect.db: try arm-specific dir first, then ~/.openclaw fallback."""
    plugin_rel = Path("workspace") / ".openclaw" / "extensions" / "reflect-and-adapt" / "reflect.db"
    candidates = [
        Path(os.path.expanduser(openclaw_dir)) / plugin_rel,
        Path.home() / ".openclaw" / plugin_rel,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def get_scores(openclaw_dir: str, session_id: str | None = None) -> pd.DataFrame:
    """Return scores table as a DataFrame, optionally filtered by session_id prefix."""
    path = _db_path(openclaw_dir)
    if path is None:
        return pd.DataFrame()

    conn = sqlite3.connect(path)
    try:
        if session_id:
            df = pd.read_sql_query(
                "SELECT * FROM scores WHERE session_id LIKE ?",
                conn,
                params=(f"{session_id}%",),
            )
        else:
            df = pd.read_sql_query("SELECT * FROM scores", conn)
    finally:
        conn.close()

    return df


def get_last_cortex_run(openclaw_dir: str) -> str | None:
    """Return the ISO timestamp of lastCortexRun from the state table, or None."""
    path = _db_path(openclaw_dir)
    if path is None:
        return None

    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM state WHERE key='lastCortexRun'"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_proposals(openclaw_dir: str, status: str | None = None) -> pd.DataFrame:
    """Return proposals table, optionally filtered by status."""
    path = _db_path(openclaw_dir)
    if path is None:
        return pd.DataFrame()

    conn = sqlite3.connect(path)
    try:
        if status:
            df = pd.read_sql_query(
                "SELECT * FROM proposals WHERE status=?", conn, params=(status,)
            )
        else:
            df = pd.read_sql_query("SELECT * FROM proposals", conn)
    finally:
        conn.close()

    return df
