from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np

from app.entities.stock_data_context import StockDailyFrame
from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_sql import TUSHARE_BAR_1D_QFQ_SQL, TUSHARE_UNIVERSE_DAILY_SQL


# 框架基础列：所有策略都会拿到（除主键 trade_date/code 外）。
SIGNAL_BASE_FLOAT_COLUMNS: tuple[str, ...] = (
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "vol",
    "is_st",
)
SIGNAL_BASE_TEXT_COLUMNS: tuple[str, ...] = ("name",)

# 行业上下文列（实验性）：来自 tmp.industry_daily（按 trade_date + industry join）。
# 策略在 required_columns 中声明这些列时自动联表；tmp 表由
# scripts/build_tmp_industry_daily.py 手工重建，不在 tushare 刷新流水线内。
INDUSTRY_CONTEXT_COLUMNS: dict[str, str] = {
    "industry_heat_rank": "ind.heat_rank",
    "industry_strong_count": "ind.strong_count",
    "industry_strong_ratio": "ind.strong_ratio",
    "industry_amount_share": "ind.amount_share",
    "industry_above_ma60_ratio": "ind.above_ma60_ratio",
}


class SignalRepository:
    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    # ------------------------------------------------------------------
    # 信号评估数据（宽表列式窗口）
    # ------------------------------------------------------------------

    def get_codes_in_range(self, *, start_date: date, end_date: date) -> list[str]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select distinct code
                from tushare.stock_daily_technical
                where trade_date between ? and ?
                  and code is not null
                order by code
                """,
                [start_date, end_date],
            ).fetchall()
        return [str(row[0]) for row in rows if row and row[0] is not None]

    def get_universe_counts_by_date(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[date, int]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select trade_date, count(*)
                from tushare.stock_daily_technical
                where trade_date between ? and ?
                group by trade_date
                """,
                [start_date, end_date],
            ).fetchall()
        return {row[0]: int(row[1]) for row in rows if isinstance(row[0], date)}

    def load_stock_frames(
        self,
        *,
        codes: list[str],
        start_date: date,
        end_date: date,
        window: int,
        extra_columns: tuple[str, ...] = (),
    ) -> dict[str, StockDailyFrame]:
        """按股票加载"区间起点前 window 根 + 区间内"的宽表行，返回列式结构。"""
        if not codes:
            return {}
        float_columns = list(SIGNAL_BASE_FLOAT_COLUMNS)
        industry_columns: list[str] = []
        for column in extra_columns:
            if column in INDUSTRY_CONTEXT_COLUMNS:
                if column not in industry_columns:
                    industry_columns.append(column)
            elif column not in float_columns:
                float_columns.append(column)
        select_columns = ["trade_date", "code", *float_columns, *industry_columns, *SIGNAL_BASE_TEXT_COLUMNS]
        column_sql = ", ".join(select_columns)
        if industry_columns:
            industry_select = ", ".join(
                f"{INDUSTRY_CONTEXT_COLUMNS[column]} as {column}" for column in industry_columns
            )
            source_sql = f"""
                select t.trade_date, t.code,
                       {', '.join(f't.{column}' for column in float_columns)},
                       {industry_select},
                       {', '.join(f't.{column}' for column in SIGNAL_BASE_TEXT_COLUMNS)}
                from tushare.stock_daily_technical t
                left join tmp.industry_daily ind
                  on ind.trade_date = t.trade_date
                 and ind.industry = t.industry
            """
        else:
            source_sql = "select * from tushare.stock_daily_technical"
        with self.duckdb.connect(read_only=True) as connection:
            frame = connection.execute(
                f"""
                with src as ({source_sql}),
                ranked_before as (
                    select {column_sql},
                           row_number() over (
                               partition by code
                               order by trade_date desc
                           ) as rn
                    from src
                    where trade_date < ?
                      and code in (select unnest(?))
                ),
                before_window as (
                    select {column_sql}
                    from ranked_before
                    where rn <= ?
                ),
                in_range as (
                    select {column_sql}
                    from src
                    where trade_date between ? and ?
                      and code in (select unnest(?))
                )
                select * from before_window
                union all
                select * from in_range
                order by code, trade_date
                """,
                [start_date, codes, window, start_date, end_date, codes],
            ).fetchdf()
        if frame.empty:
            return {}

        result: dict[str, StockDailyFrame] = {}
        for code, group in frame.groupby("code", sort=False):
            trade_dates = [
                value.date() if isinstance(value, datetime) else value
                for value in group["trade_date"].tolist()
            ]
            columns: dict[str, Any] = {
                column: group[column].to_numpy(dtype=np.float64, na_value=np.nan)
                for column in (*float_columns, *industry_columns)
            }
            for column in SIGNAL_BASE_TEXT_COLUMNS:
                columns[column] = group[column].to_numpy(dtype=object)
            result[str(code)] = StockDailyFrame(
                code=str(code),
                trade_dates=trade_dates,
                columns=columns,
            )
        return result

    # ------------------------------------------------------------------
    # 前端图表上下文（全量历史，沿用 qfq 视图）
    # ------------------------------------------------------------------

    def get_latest_universe_by_codes(self, *, codes: list[str]) -> list[dict[str, Any]]:
        if not codes:
            return []

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                with ranked as (
                    select *,
                           row_number() over (
                               partition by code
                               order by trade_date desc
                           ) as rn
                    from ({TUSHARE_UNIVERSE_DAILY_SQL}) universe
                    where code in (select unnest(?))
                )
                select * exclude (rn)
                from ranked
                where rn = 1
                order by code
                """,
                [codes],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return [self._normalize_row(columns, row) for row in rows]

    def get_full_bar_1d_qfq_history(
        self,
        *,
        codes: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not codes:
            return {}

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select *
                from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                where code in (select unnest(?))
                order by code, trade_date
                """,
                [codes],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]

        bars_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = self._normalize_row(columns, row)
            code = item.get("code")
            if not isinstance(code, str):
                continue
            bars_by_code.setdefault(code, []).append(item)
        return bars_by_code

    def _normalize_row(self, columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            column: self._normalize_value(value)
            for column, value in zip(columns, row)
        }

    def _normalize_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value
