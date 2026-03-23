#!/usr/bin/env python3
"""
Generates a realistic dbt pipeline failure log.
Run before session: python setup.py --target /path/to/workspace/data/
"""
import argparse
from pathlib import Path


LOG = """\
03:00:01 | Running with dbt=1.7.4
03:00:01 | Registered adapter: postgres=1.7.4
03:00:02 | Found 34 models, 12 tests, 8 sources, 3 snapshots, 0 analyses
03:00:02 |
03:00:02 | Concurrency: 4 threads (target='prod')
03:00:02 |
03:00:02 | 1 of 34 START sql table model analytics.stg_orders .............. [RUN]
03:00:04 | 1 of 34 OK created sql table model analytics.stg_orders ......... [SELECT 8191 in 1.84s]
03:00:04 | 2 of 34 START sql table model analytics.stg_customers ........... [RUN]
03:00:06 | 2 of 34 OK created sql table model analytics.stg_customers ....... [SELECT 420312 in 2.11s]
03:00:06 | 3 of 34 START sql table model analytics.stg_returns .............. [RUN]
03:00:07 | 3 of 34 OK created sql table model analytics.stg_returns ......... [SELECT 1847 in 0.93s]
03:00:07 | 4 of 34 START sql table model analytics.int_order_items .......... [RUN]
03:00:09 | 4 of 34 OK created sql table model analytics.int_order_items ..... [SELECT 24891 in 2.34s]
03:00:09 | 5 of 34 START sql table model analytics.int_customer_orders ....... [RUN]
03:00:11 | 5 of 34 OK created sql table model analytics.int_customer_orders .. [SELECT 420312 in 2.18s]
03:00:11 | 6 of 34 START sql table model analytics.fct_daily_revenue ......... [RUN]
03:00:13 | 6 of 34 OK created sql table model analytics.fct_daily_revenue .... [SELECT 127 in 1.92s]
03:00:13 | 7 of 34 START sql table model analytics.fct_customer_ltv .......... [RUN]
03:00:17 | 7 of 34 OK created sql table model analytics.fct_customer_ltv ..... [SELECT 420312 in 4.11s]
03:00:17 | 8 of 34 START sql table model analytics.fct_cohort_retention ....... [RUN]
03:00:19 | 8 of 34 OK created sql table model analytics.fct_cohort_retention .. [SELECT 48 in 2.03s]
03:00:19 | 9 of 34 START sql table model analytics.mart_finance_daily ......... [RUN]
03:00:23 | 9 of 34 ERROR creating sql table model analytics.mart_finance_daily  [ERROR in 3.84s]
03:00:23 |
03:00:23 | Finished running 9 models in 0 hours 0 minutes and 22.41 seconds (22.41s).
03:00:23 |
03:00:23 | Completed with 1 error and 0 warnings:
03:00:23 |
03:00:23 | Database Error in model mart_finance_daily (models/marts/mart_finance_daily.sql)
03:00:23 |   null value in column "product_category_id" of relation "mart_finance_daily"
03:00:23 |   violates not-null constraint
03:00:23 |   DETAIL:  Failing row contains (2026-03-13, null, 4821, 78234.50, 312, ...).
03:00:23 |   HINT:  This column was added with a NOT NULL constraint in migration 20260310_add_category_fk.
03:00:23 |   CONTEXT:  COPY mart_finance_daily, line 1
03:00:23 |
03:00:23 |   > select
03:00:23 |       o.date,
03:00:23 |       p.category_id as product_category_id,   -- new join added 2026-03-10
03:00:23 |       count(o.id) as order_count,
03:00:23 |       sum(o.amount) as gross_revenue,
03:00:23 |       count(distinct o.customer_id) as unique_customers
03:00:23 |     from {{ ref('fct_daily_revenue') }} o
03:00:23 |     left join {{ ref('dim_products') }} p on o.product_id = p.id
03:00:23 |
03:00:23 | Done. PASS=8 WARN=0 ERROR=1 SKIP=25 TOTAL=34
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    log_path = target / "pipeline.log"
    log_path.write_text(LOG)
    print(f"Log written to: {log_path}")


if __name__ == "__main__":
    main()
