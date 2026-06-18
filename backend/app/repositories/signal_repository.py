from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from app.dtos.signal_dto import DailySignalItemDTO, DailySignalResultDTO, DailySignalTaskDTO
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
DEFAULT_SIGNAL_COLUMNS: tuple[str, ...] = (
    "ts_code",
    "code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
    "adj_factor",
    "latest_adj_factor",
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "qfq_pre_close",
    "name",
    "industry",
    "area",
    "pe",
    "pe_ttm",
    "ps",
    "ps_ttm",
    "pb",
    "dv_ratio",
    "dv_ttm",
    "float_share",
    "total_share",
    "daily_basic_float_share",
    "daily_basic_total_share",
    "free_share",
    "total_mv",
    "circ_mv",
    "turnover_rate",
    "turnover_rate_f",
    "daily_basic_volume_ratio",
    "total_assets",
    "liquid_assets",
    "fixed_assets",
    "reserved",
    "reserved_pershare",
    "eps",
    "bvps",
    "list_date",
    "undp",
    "per_undp",
    "rev_yoy",
    "profit_yoy",
    "gpr",
    "npr",
    "holder_num",
    "is_st",
    "atr_5",
    "atr_14",
    "atr_30",
    "atr_pct_5",
    "atr_pct_14",
    "atr_pct_30",
    "avg_volume_5",
    "avg_volume_10",
    "avg_volume_20",
    "volume_ratio_5",
    "volume_ratio_10",
    "volume_ratio_20",
    "vwap_5",
    "vwap_14",
    "vwap_20",
    "vwap_30",
    "ma_5",
    "ma_10",
    "ma_20",
    "ma_30",
    "ma_60",
    "ma_120",
    "bias_5",
    "bias_10",
    "bias_20",
    "bias_30",
    "bias_60",
    "bias_120",
    "ma_slope_5",
    "ma_slope_10",
    "ma_slope_20",
    "ma_slope_30",
    "ma_slope_60",
    "ma_slope_120",
    "er_10",
    "er_20",
    "er_60",
    "boll_upper_10_2",
    "boll_middle_10_2",
    "boll_lower_10_2",
    "boll_bandwidth_10_2",
    "boll_percent_b_10_2",
    "boll_upper_20_2",
    "boll_middle_20_2",
    "boll_lower_20_2",
    "boll_bandwidth_20_2",
    "boll_percent_b_20_2",
    "boll_upper_60_2",
    "boll_middle_60_2",
    "boll_lower_60_2",
    "boll_bandwidth_60_2",
    "boll_percent_b_60_2",
    "macd_dif_12_26_9",
    "macd_dea_12_26_9",
    "macd_hist_12_26_9",
    "rsi_5",
    "rsi_14",
    "rsi_20",
    "roc_5",
    "roc_10",
    "roc_20",
    "roc_60",
    "roc_120",
    "kdj_k_9_3_3",
    "kdj_d_9_3_3",
    "kdj_j_9_3_3",
    "body_atr14_ratio",
    "range_atr14_ratio",
    "body_range_ratio",
    "upper_shadow_range_ratio",
    "lower_shadow_range_ratio",
    "overnight_return",
    "rebuilt_at",
)
MINUTE_DERIVED_SIGNAL_COLUMNS: frozenset[str] = frozenset({"min5_close"})


class SignalRepository:
    MAX_LOG_LINES = 2000

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def ensure_tables(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute("create schema if not exists meta")
            connection.execute("create sequence if not exists meta.daily_signal_task_id_seq")
            connection.execute(
                """
                create table if not exists meta.daily_signal_task (
                    id bigint primary key default nextval('meta.daily_signal_task_id_seq'),
                    status varchar not null,
                    trade_date date not null,
                    strategy_name varchar not null,
                    universe_count bigint,
                    processed_count bigint not null default 0,
                    signal_count bigint,
                    started_at timestamp,
                    finished_at timestamp,
                    created_at timestamp not null default current_timestamp,
                    updated_at timestamp not null default current_timestamp,
                    logs varchar not null default ''
                )
                """
            )
            for statement in (
                "alter table meta.daily_signal_task add column if not exists universe_count bigint",
                "alter table meta.daily_signal_task add column if not exists processed_count bigint default 0",
                "alter table meta.daily_signal_task add column if not exists signal_count bigint",
                "alter table meta.daily_signal_task add column if not exists started_at timestamp",
                "alter table meta.daily_signal_task add column if not exists finished_at timestamp",
                "alter table meta.daily_signal_task add column if not exists logs varchar default ''",
            ):
                connection.execute(statement)
            connection.execute(
                """
                create table if not exists meta.daily_signal_result (
                    task_id bigint not null,
                    trade_date date not null,
                    strategy_name varchar not null,
                    code varchar not null,
                    code_name varchar,
                    universe_json varchar,
                    signal_json varchar not null,
                    created_at timestamp not null default current_timestamp
                )
                """
            )

    def create_daily_signal_task(
        self,
        *,
        trade_date: date,
        strategy_name: str,
        initial_log: str,
    ) -> DailySignalTaskDTO:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            task_id = connection.execute(
                "select coalesce(max(id), 0) + 1 from meta.daily_signal_task"
            ).fetchone()[0]
            row = connection.execute(
                """
                insert into meta.daily_signal_task(
                    id, status, trade_date, strategy_name, processed_count, started_at, logs
                )
                values (?, 'running', ?, ?, 0, current_timestamp, ?)
                returning *
                """,
                [task_id, trade_date, strategy_name, self._format_log(initial_log)],
            ).fetchone()
        task = self._to_daily_signal_task(row)
        if task is None:
            raise RuntimeError("failed to create daily signal task")
        return task

    def get_daily_signal_task(self, task_id: int) -> DailySignalTaskDTO | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                "select * from meta.daily_signal_task where id = ?",
                [task_id],
            ).fetchone()
        return self._to_daily_signal_task(row)

    def get_latest_daily_signal_task(
        self,
        *,
        trade_date: date | None = None,
        strategy_name: str | None = None,
    ) -> DailySignalTaskDTO | None:
        self.ensure_tables()
        clauses: list[str] = []
        values: list[Any] = []
        if trade_date is not None:
            clauses.append("trade_date = ?")
            values.append(trade_date)
        if strategy_name is not None:
            clauses.append("strategy_name = ?")
            values.append(strategy_name)
        where_sql = "" if not clauses else f"where {' and '.join(clauses)}"
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                select *
                from meta.daily_signal_task
                {where_sql}
                order by id desc
                limit 1
                """,
                values,
            ).fetchone()
        return self._to_daily_signal_task(row)

    def append_daily_signal_task_log(self, task_id: int, message: str) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                "select logs from meta.daily_signal_task where id = ?",
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.daily_signal_task
                set logs = ?, updated_at = current_timestamp
                where id = ?
                """,
                [self._trim_logs(logs + self._format_log(message)), task_id],
            )

    def update_daily_signal_task_progress(
        self,
        *,
        task_id: int,
        universe_count: int | None = None,
        processed_count: int | None = None,
        signal_count: int | None = None,
    ) -> None:
        assignments = ["updated_at = current_timestamp"]
        values: list[Any] = []
        if universe_count is not None:
            assignments.append("universe_count = ?")
            values.append(universe_count)
        if processed_count is not None:
            assignments.append("processed_count = ?")
            values.append(processed_count)
        if signal_count is not None:
            assignments.append("signal_count = ?")
            values.append(signal_count)
        values.append(task_id)
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                f"update meta.daily_signal_task set {', '.join(assignments)} where id = ?",
                values,
            )

    def finish_daily_signal_task(self, *, task_id: int, status: str, message: str) -> None:
        if status not in {"success", "error"}:
            raise ValueError(f"invalid daily signal task status: {status}")
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                "select logs from meta.daily_signal_task where id = ?",
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.daily_signal_task
                set status = ?,
                    logs = ?,
                    finished_at = current_timestamp,
                    updated_at = current_timestamp
                where id = ?
                """,
                [status, self._trim_logs(logs + self._format_log(message)), task_id],
            )

    def clear_daily_signal_results(self, task_id: int) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                "delete from meta.daily_signal_result where task_id = ?",
                [task_id],
            )

    def insert_daily_signal_results(self, rows: list[list[Any]]) -> None:
        if not rows:
            return
        with self.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                """
                insert into meta.daily_signal_result(
                    task_id, trade_date, strategy_name, code, code_name,
                    universe_json, signal_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_daily_signal_result(self, task_id: int) -> DailySignalResultDTO | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            task_row = connection.execute(
                """
                select trade_date, strategy_name, coalesce(universe_count, 0), coalesce(signal_count, 0)
                from meta.daily_signal_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
            if task_row is None:
                return None
            rows = connection.execute(
                """
                select code, code_name, trade_date, universe_json, signal_json
                from meta.daily_signal_result
                where task_id = ?
                order by code
                """,
                [task_id],
            ).fetchall()
        trade_date, strategy_name, universe_count, signal_count = task_row
        items: list[DailySignalItemDTO] = []
        for code, code_name, row_trade_date, universe_json, signal_json in rows:
            try:
                universe = json.loads(universe_json) if universe_json else {}
            except json.JSONDecodeError:
                universe = {}
            try:
                signal = json.loads(signal_json) if signal_json else None
            except json.JSONDecodeError:
                signal = None
            items.append(
                DailySignalItemDTO(
                    code=str(code),
                    code_name=code_name,
                    trade_date=str(row_trade_date),
                    universe=universe,
                    signal=signal,
                )
            )
        return DailySignalResultDTO(
            trade_date=str(trade_date),
            strategy_name=str(strategy_name),
            universe_count=int(universe_count or 0),
            signal_count=int(signal_count or len(items)),
            signals=items,
        )

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

    def load_signal_selection_rows(
        self,
        *,
        start_date: date,
        end_date: date,
        window: int = 200,
        code_filter: Any | None = None,
        columns: tuple[str, ...] | None = None,
    ) -> Any:
        from app.repositories.tushare_repository import TushareRepository

        TushareRepository().ensure_tables()
        if columns is None:
            columns = self.get_default_signal_columns()
        select_columns = self._signal_selection_columns(columns)
        column_sql = "*" if select_columns is None else ", ".join(select_columns)
        with self.duckdb.connect(read_only=True) as connection:
            if window <= 0:
                frame = connection.execute(
                    f"""
                    select {column_sql}
                    from tushare.stock_daily_technical
                    where code is not null
                      and trade_date between ? and ?
                    order by code, trade_date
                    """,
                    [start_date, end_date],
                ).fetchdf()
            else:
                frame = connection.execute(
                    f"""
                    with src as (
                        select {column_sql}
                        from tushare.stock_daily_technical
                        where code is not null
                    ),
                    codes as (
                        select distinct code
                        from src
                        where trade_date between ? and ?
                    ),
                    ranked_before_keys as (
                        select code,
                               trade_date,
                               row_number() over (
                                   partition by code
                                   order by trade_date desc
                               ) as rn
                        from tushare.stock_daily_technical
                        where code in (select code from codes)
                          and code is not null
                          and trade_date < ?
                    ),
                    before_keys as (
                        select code, trade_date
                        from ranked_before_keys
                        where rn <= ?
                    ),
                    before_window as (
                        select src.*
                        from src
                        join before_keys using (code, trade_date)
                    ),
                    in_range as (
                        select src.*
                        from src
                        join codes using (code)
                        where trade_date between ? and ?
                    )
                    select *
                    from before_window
                    union all
                    select *
                    from in_range
                    order by code, trade_date
                    """,
                    [start_date, end_date, start_date, window, start_date, end_date],
                ).fetchdf()
        frame = self._normalize_signal_frame(frame)
        if frame.empty or code_filter is None:
            return frame
        return frame[frame["code"].apply(lambda value: code_filter(str(value)))].copy()

    def _normalize_signal_frame(self, frame: Any) -> Any:
        if frame.empty:
            return frame
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date
        if "list_date" in frame.columns:
            frame["list_date"] = pd.to_datetime(frame["list_date"], errors="coerce").dt.date
        return frame

    def get_default_signal_columns(self) -> tuple[str, ...]:
        with self.duckdb.connect(read_only=True) as connection:
            available = {
                str(row[0])
                for row in connection.execute("describe tushare.stock_daily_technical").fetchall()
                if row
            }
        missing = [column for column in DEFAULT_SIGNAL_COLUMNS if column not in available]
        if missing:
            raise RuntimeError(f"missing default signal columns: {missing}")
        return DEFAULT_SIGNAL_COLUMNS

    def _signal_selection_columns(self, columns: tuple[str, ...] | None) -> list[str] | None:
        if columns is None:
            return None
        selected = ["trade_date", "code"]
        for column in columns or ():
            if column not in selected:
                selected.append(column)
        return selected

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
        for column in extra_columns:
            if column not in float_columns:
                float_columns.append(column)
        select_columns = ["trade_date", "code", *float_columns, *SIGNAL_BASE_TEXT_COLUMNS]
        column_sql = ", ".join(select_columns)
        with self.duckdb.connect(read_only=True) as connection:
            frame = connection.execute(
                f"""
                with ranked_before_keys as (
                    select code,
                           trade_date,
                           row_number() over (
                               partition by code
                               order by trade_date desc
                           ) as rn
                    from tushare.stock_daily_technical
                    where trade_date < ?
                      and code in (select unnest(?))
                ),
                before_keys as (
                    select code, trade_date
                    from ranked_before_keys
                    where rn <= ?
                ),
                before_window as (
                    select {column_sql}
                    from tushare.stock_daily_technical
                    join before_keys using (code, trade_date)
                ),
                in_range as (
                    select {column_sql}
                    from tushare.stock_daily_technical
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
                for column in float_columns
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
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    def to_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=self._normalize_value)

    def _format_log(self, message: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {message}\n"

    def _trim_logs(self, logs: str) -> str:
        lines = logs.splitlines()
        if len(lines) <= self.MAX_LOG_LINES:
            return logs
        return "\n".join(lines[-self.MAX_LOG_LINES :]) + "\n"

    def _to_daily_signal_task(self, row: tuple[Any, ...] | None) -> DailySignalTaskDTO | None:
        if row is None:
            return None
        (
            task_id,
            status,
            trade_date,
            strategy_name,
            universe_count,
            processed_count,
            signal_count,
            started_at,
            finished_at,
            created_at,
            updated_at,
            logs,
        ) = row
        return DailySignalTaskDTO(
            id=None if task_id is None else int(task_id),
            status=str(status),
            trade_date="" if trade_date is None else str(trade_date),
            strategy_name=str(strategy_name),
            universe_count=None if universe_count is None else int(universe_count),
            processed_count=int(processed_count or 0),
            signal_count=None if signal_count is None else int(signal_count),
            started_at=None if started_at is None else str(started_at),
            finished_at=None if finished_at is None else str(finished_at),
            created_at=None if created_at is None else str(created_at),
            updated_at=None if updated_at is None else str(updated_at),
            logs=logs or "",
        )
