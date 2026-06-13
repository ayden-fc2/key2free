"""构建实验性行业日频热度表 tmp.industry_daily（含 __ALL__ 全市场聚合行）。

实验性资产：不在 tushare 刷新流水线内，由本脚本基于 tushare.stock_daily_technical
覆盖式重建；验证有效后再正式扩展到 tushare 资产层。

运行（需独占 DuckDB）：PYTHONPATH=. ../.venv/Scripts/python.exe scripts/build_tmp_industry_daily.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "data.duckdb"

BUILD_SQL = """
create schema if not exists tmp;
create or replace table tmp.industry_daily as
with base as (
    select trade_date, industry, pct_chg, roc_20, qfq_close, ma_60, amount
    from tushare.stock_daily_technical
    where industry is not null
),
ind as (
    select
        trade_date,
        industry,
        count(*) as stock_count,
        avg(pct_chg) as avg_pct_chg,
        sum(case when roc_20 >= 0.25 then 1 else 0 end) as strong_count,
        avg(case when roc_20 >= 0.25 then 1.0 else 0.0 end) as strong_ratio,
        sum(case when pct_chg >= 9.7 then 1 else 0 end) as limit_up_count,
        sum(amount) as amount_sum,
        avg(case when qfq_close > ma_60 then 1.0 else 0.0 end) as above_ma60_ratio
    from base
    group by 1, 2
),
mkt as (
    select trade_date, sum(amount_sum) as total_amount
    from ind
    group by 1
),
ranked as (
    select
        i.*,
        i.amount_sum / nullif(m.total_amount, 0) as amount_share,
        row_number() over (
            partition by i.trade_date
            order by i.strong_count desc, i.amount_sum desc
        ) as heat_rank
    from ind i
    join mkt m using (trade_date)
),
overall as (
    select
        trade_date,
        '__ALL__' as industry,
        sum(stock_count) as stock_count,
        sum(avg_pct_chg * stock_count) / sum(stock_count) as avg_pct_chg,
        sum(strong_count) as strong_count,
        sum(strong_count) * 1.0 / sum(stock_count) as strong_ratio,
        sum(limit_up_count) as limit_up_count,
        sum(amount_sum) as amount_sum,
        sum(above_ma60_ratio * stock_count) / sum(stock_count) as above_ma60_ratio,
        cast(1.0 as double) as amount_share,
        cast(null as bigint) as heat_rank
    from ranked
    group by 1
)
select * from ranked
union all
select * from overall;
"""


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=False)
    try:
        con.execute(BUILD_SQL)
        total, days, industries = con.execute(
            """
            select count(*),
                   count(distinct trade_date),
                   count(distinct industry)
            from tmp.industry_daily
            """
        ).fetchone()
        sample = con.execute(
            """
            select industry, strong_count, strong_ratio, amount_share, heat_rank
            from tmp.industry_daily
            where trade_date = (select max(trade_date) from tmp.industry_daily)
              and industry != '__ALL__'
            order by heat_rank
            limit 5
            """
        ).fetchall()
        breadth = con.execute(
            """
            select above_ma60_ratio from tmp.industry_daily
            where industry = '__ALL__'
            order by trade_date desc limit 1
            """
        ).fetchone()[0]
        print(f"tmp.industry_daily built: rows={total} days={days} industries={industries}")
        print("最新交易日热度 top5:", [(r[0], int(r[1]), round(r[2], 2), round(r[3], 3)) for r in sample])
        print(f"最新全市场广度(close>ma60): {breadth:.1%}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
