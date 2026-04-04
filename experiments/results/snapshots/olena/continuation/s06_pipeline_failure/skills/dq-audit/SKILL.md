# dq-audit

Olena's standard data quality pre-flight. Run this before any analysis, join, or aggregation.
Checks for duplicates, NULLs, and row-count sanity across one or more tables.

## Trigger

Use when Olena provides a new dataset, asks to investigate a discrepancy, or before building
any report. Trigger phrases: "check the data first", "let's audit this", "before we join",
"are there duplicates?", "can you verify the data?", or any time a new CSV or table is loaded.

Always run proactively at session start if data files are present in `data/` — don't wait
to be asked.

## Usage

```bash
python skills/dq-audit/dq_audit.py <file_or_table> [<file_or_table> ...]
```

Examples:
```bash
python skills/dq-audit/dq_audit.py data/orders.csv
python skills/dq-audit/dq_audit.py data/orders.csv data/returns.csv data/customers.csv
python skills/dq-audit/dq_audit.py data/orders.parquet
```

The script accepts CSV, Parquet, or JSON files. DuckDB reads them directly — no loading step needed.

## What It Checks

For each table:
1. **Row count** — total rows
2. **Duplicate primary key candidates** — finds columns where `COUNT(DISTINCT val) < COUNT(*)`;
   flags any column with duplicates > 0
3. **NULL counts** — per column, absolute count and percentage
4. **Date range** — min/max of any column whose name contains `date`, `time`, or `_at`
5. **Numeric outliers** — min/max/avg for numeric columns (quick sanity check)

## Output

Prints a structured report to stdout. Paste it directly into the chat — Olena reviews the
findings before deciding next steps.

## Notes

- Olena always wants to see the raw audit numbers, not a summary. Print everything.
- If duplicates are found, do not silently deduplicate. Flag them and ask how to handle.
- If NULLs exceed 5% in a join-key column, call it out explicitly before proceeding.
- This script does not write any files or modify data. It is read-only.
