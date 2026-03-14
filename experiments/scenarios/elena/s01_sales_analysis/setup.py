#!/usr/bin/env python3
"""
Creates sales.db with regional sales and targets for Q1 2026.
Run before session: python setup.py --target /path/to/workspace/data/
"""
import argparse
import sqlite3
from pathlib import Path


def create_db(target_dir: Path):
    db_path = target_dir / "sales.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE regions (
            id     INTEGER PRIMARY KEY,
            name   TEXT NOT NULL,
            manager TEXT NOT NULL
        );

        CREATE TABLE sales (
            id          INTEGER PRIMARY KEY,
            region_id   INTEGER NOT NULL,
            month       TEXT NOT NULL,
            revenue     REAL NOT NULL,
            orders      INTEGER NOT NULL,
            FOREIGN KEY (region_id) REFERENCES regions(id)
        );

        CREATE TABLE targets (
            region_id   INTEGER NOT NULL,
            quarter     TEXT NOT NULL,
            target      REAL NOT NULL,
            PRIMARY KEY (region_id, quarter),
            FOREIGN KEY (region_id) REFERENCES regions(id)
        );
    """)

    regions = [
        (1, "North",      "James Osei"),
        (2, "South",      "Maria Kovacs"),
        (3, "East",       "Tom Brennan"),
        (4, "West",       "Yuki Tanaka"),
        (5, "Central",    "Priya Singh"),
    ]
    c.executemany("INSERT INTO regions VALUES (?,?,?)", regions)

    # Q1 2026 monthly sales (Jan-Mar)
    sales = [
        # North — performing well
        (1,  1, "2026-01", 82000, 341), (2,  1, "2026-02", 91000, 378), (3,  1, "2026-03", 88000, 362),
        # South — significantly below target
        (4,  2, "2026-01", 54000, 198), (5,  2, "2026-02", 49000, 181), (6,  2, "2026-03", 51000, 190),
        # East — slightly below
        (7,  3, "2026-01", 71000, 295), (8,  3, "2026-02", 68000, 280), (9,  3, "2026-03", 74000, 307),
        # West — meeting target
        (10, 4, "2026-01", 95000, 410), (11, 4, "2026-02", 99000, 425), (12, 4, "2026-03", 97000, 418),
        # Central — new region, one month of data missing (NULL equivalent — no row)
        (13, 5, "2026-02", 38000, 142), (14, 5, "2026-03", 42000, 158),
    ]
    c.executemany("INSERT INTO sales VALUES (?,?,?,?,?)", sales)

    targets = [
        (1, "Q1-2026", 255000),   # North target
        (2, "Q1-2026", 210000),   # South target — actual is ~154k, big miss
        (3, "Q1-2026", 225000),   # East target  — actual is ~213k, slight miss
        (4, "Q1-2026", 285000),   # West target  — actual is ~291k, on track
        (5, "Q1-2026", 120000),   # Central target — only 2 months data
    ]
    c.executemany("INSERT INTO targets VALUES (?,?,?)", targets)

    conn.commit()
    conn.close()
    print(f"Database created at: {db_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    Path(args.target).mkdir(parents=True, exist_ok=True)
    create_db(Path(args.target))


if __name__ == "__main__":
    main()
