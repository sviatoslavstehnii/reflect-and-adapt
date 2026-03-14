#!/usr/bin/env python3
"""
Creates app_data.db — a SQLite database with users and transactions tables.
Run before session: python setup.py --target /path/to/workspace/data/
"""
import argparse
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path


def create_db(target_dir: Path):
    db_path = target_dir / "app_data.db"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE users (
            id          INTEGER PRIMARY KEY,
            email       TEXT NOT NULL,
            full_name   TEXT NOT NULL,
            signed_up   TEXT NOT NULL,
            plan        TEXT NOT NULL DEFAULT 'free'
        );

        CREATE TABLE transactions (
            id          INTEGER PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            amount      REAL NOT NULL,
            status      TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)

    # February signups (last month)
    feb_users = [
        (1, "james.carter@example.com",   "James Carter",   "2026-02-03", "free"),
        (2, "nina.shaw@techcorp.io",       "Nina Shaw",      "2026-02-07", "pro"),
        (3, "oliver.m@startup.co",         "Oliver Morris",  "2026-02-11", "free"),
        (4, "priya.k@designstudio.com",    "Priya Kumar",    "2026-02-14", "free"),
        (5, "sam.wilson@cloudbase.net",    "Sam Wilson",     "2026-02-19", "pro"),
        (6, "lea.dupont@agence.fr",        "Lea Dupont",     "2026-02-22", "free"),
        (7, "tom.brennan@finco.ie",        "Tom Brennan",    "2026-02-27", "free"),
    ]
    # March signups (this month — should be excluded)
    mar_users = [
        (8, "helen.fox@growthco.com",      "Helen Fox",      "2026-03-02", "pro"),
        (9, "david.ng@labs.ai",            "David Ng",       "2026-03-08", "free"),
    ]
    c.executemany("INSERT INTO users VALUES (?,?,?,?,?)", feb_users + mar_users)

    # Transactions — some Feb users have none (those are the ones we want)
    transactions = [
        (1, 2,  149.99, "completed", "2026-02-09"),
        (2, 2,   49.99, "completed", "2026-02-28"),
        (3, 3,   19.99, "completed", "2026-02-12"),   # Oliver has one
        (4, 5,  299.00, "completed", "2026-02-20"),
        (5, 5,   99.00, "refunded",  "2026-03-01"),
        (6, 8,  199.00, "completed", "2026-03-05"),   # March user
    ]
    # Users 1, 4, 6, 7 signed up in Feb with NO transactions
    c.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)", transactions)

    conn.commit()
    conn.close()
    print(f"Database created at: {db_path}")
    print("Tables: users (9 rows), transactions (6 rows)")
    print("Feb users with no transactions: ids 1, 4, 6, 7")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    Path(args.target).mkdir(parents=True, exist_ok=True)
    create_db(Path(args.target))


if __name__ == "__main__":
    main()
