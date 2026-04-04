#!/usr/bin/env python3
"""
dq_audit.py — Olena's standard data quality pre-flight.

Usage:
    python dq_audit.py <file> [<file> ...]

Accepts CSV, Parquet, or JSON. Prints a structured audit report to stdout.
Read-only — never modifies source data.
"""
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("DuckDB not installed. Run: pip install duckdb")
    sys.exit(1)


SEPARATOR = "─" * 60


def audit_table(con: duckdb.DuckDBPyConnection, name: str, path: str) -> None:
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        read_fn = f"read_csv_auto('{path}')"
    elif ext in (".parquet", ".pq"):
        read_fn = f"read_parquet('{path}')"
    elif ext == ".json":
        read_fn = f"read_json_auto('{path}')"
    else:
        print(f"  [skip] Unsupported format: {ext}")
        return

    con.execute(f"CREATE OR REPLACE VIEW _tbl AS SELECT * FROM {read_fn}")

    # ── Row count ─────────────────────────────────────────────────────────────
    total = con.execute("SELECT COUNT(*) FROM _tbl").fetchone()[0]
    print(f"\n  Total rows : {total:,}")

    # ── Column info ───────────────────────────────────────────────────────────
    cols = con.execute("DESCRIBE _tbl").fetchall()
    col_names = [c[0] for c in cols]
    col_types = {c[0]: c[1] for c in cols}

    # ── Duplicates — flag every column where distinct < total ─────────────────
    dup_results = []
    for col in col_names:
        distinct = con.execute(f'SELECT COUNT(DISTINCT "{col}") FROM _tbl').fetchone()[0]
        if distinct < total:
            dupes = total - distinct
            dup_results.append((col, distinct, dupes))

    print(f"\n  Duplicate check ({len(col_names)} columns scanned):")
    if not dup_results:
        print("    ✅ No column has duplicate values (all columns fully distinct)")
    else:
        for col, distinct, dupes in dup_results:
            pct = dupes / total * 100
            flag = "⚠️ " if pct > 1 else "  "
            print(f"    {flag}{col!r:30s}  {dupes:>6,} dupes  ({pct:.1f}%  distinct={distinct:,})")

    # ── NULL counts ───────────────────────────────────────────────────────────
    print(f"\n  NULL counts:")
    any_nulls = False
    for col in col_names:
        nulls = con.execute(f'SELECT COUNT(*) FROM _tbl WHERE "{col}" IS NULL').fetchone()[0]
        if nulls > 0:
            any_nulls = True
            pct = nulls / total * 100
            flag = "⚠️ " if pct > 5 else "  "
            print(f"    {flag}{col!r:30s}  {nulls:>6,} NULLs  ({pct:.1f}%)")
    if not any_nulls:
        print("    ✅ No NULLs found in any column")

    # ── Date ranges ───────────────────────────────────────────────────────────
    date_cols = [c for c in col_names if any(kw in c.lower() for kw in ("date", "time", "_at", "period"))]
    if date_cols:
        print(f"\n  Date ranges:")
        for col in date_cols:
            try:
                row = con.execute(f'SELECT MIN("{col}"), MAX("{col}") FROM _tbl').fetchone()
                print(f"    {col!r:30s}  {row[0]}  →  {row[1]}")
            except Exception:
                pass

    # ── Numeric summary ───────────────────────────────────────────────────────
    numeric_types = ("INTEGER", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "SMALLINT")
    num_cols = [c for c in col_names if any(t in col_types[c].upper() for t in numeric_types)]
    if num_cols:
        print(f"\n  Numeric summary (min / avg / max):")
        for col in num_cols[:10]:  # cap at 10 to keep output readable
            try:
                row = con.execute(
                    f'SELECT MIN("{col}"), AVG("{col}"), MAX("{col}") FROM _tbl'
                ).fetchone()
                mn, av, mx = row
                print(f"    {col!r:30s}  {mn:>12.2f}  /  {av:>12.2f}  /  {mx:>12.2f}")
            except Exception:
                pass


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python dq_audit.py <file> [<file> ...]")
        sys.exit(1)

    paths = sys.argv[1:]
    con = duckdb.connect()

    for path in paths:
        p = Path(path)
        if not p.exists():
            print(f"\n{SEPARATOR}")
            print(f"FILE: {path}")
            print(f"  [error] File not found: {path}")
            continue

        print(f"\n{SEPARATOR}")
        print(f"FILE: {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
        print(SEPARATOR)

        try:
            audit_table(con, p.stem, str(p))
        except Exception as e:
            print(f"  [error] {e}")

    print(f"\n{SEPARATOR}")
    print("Audit complete. Review flagged items before proceeding.")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
