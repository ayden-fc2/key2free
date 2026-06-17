from __future__ import annotations

import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np

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

    def load_portfolio_selection_rows(
        self,
        *,
        start_date: date,
        end_date: date,
        code_filter: Any | None = None,
    ) -> Any:
        from app.repositories.tushare_repository import TushareRepository

        TushareRepository().ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            frame = connection.execute(
                """
                select
                    trade_date,
                    code,
                    name,
                    close,
                    qfq_open,
                    qfq_close,
                    vol,
                    pct_chg,
                    is_st,
                    list_date,
                    eps,
                    total_mv,
                    circ_mv
                from tushare.stock_daily_technical
                where trade_date between ? and ?
                  and code is not null
                order by trade_date, code
                """,
                [start_date, end_date],
            ).fetchdf()
        if not frame.empty:
            frame["trade_date"] = frame["trade_date"].apply(
                lambda value: value.date() if isinstance(value, datetime) else value
            )
            frame["list_date"] = frame["list_date"].apply(
                lambda value: value.date() if isinstance(value, datetime) else value
            )
        if frame.empty or code_filter is None:
            return frame
        return frame[frame["code"].apply(lambda value: code_filter(str(value)))].copy()

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
