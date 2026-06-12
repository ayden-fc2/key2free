from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.dtos.backtest_dto import BacktestTaskDTO
from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_sql import TUSHARE_BAR_1D_QFQ_SQL


class BacktestRepository:
    MAX_LOG_LINES = 2000

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def ensure_tables(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute("create schema if not exists meta")
            connection.execute("create sequence if not exists meta.backtest_task_id_seq")
            connection.execute(
                """
                create table if not exists meta.backtest_task (
                    id bigint primary key default nextval('meta.backtest_task_id_seq'),
                    status varchar not null,
                    strategy_name varchar not null,
                    start_date date not null,
                    end_date date not null,
                    initial_cash double not null,
                    simulation_runs bigint not null,
                    completed_runs bigint not null default 0,
                    trading_day_count bigint,
                    signal_count bigint,
                    final_asset_avg double,
                    final_asset_min double,
                    final_asset_max double,
                    final_return_avg double,
                    final_return_min double,
                    final_return_max double,
                    started_at timestamp,
                    finished_at timestamp,
                    created_at timestamp not null default current_timestamp,
                    updated_at timestamp not null default current_timestamp,
                    logs varchar not null default ''
                )
                """
            )
            for statement in (
                "alter table meta.backtest_task add column if not exists completed_runs bigint default 0",
                "alter table meta.backtest_task add column if not exists trading_day_count bigint",
                "alter table meta.backtest_task add column if not exists signal_count bigint",
                "alter table meta.backtest_task add column if not exists final_asset_avg double",
                "alter table meta.backtest_task add column if not exists final_asset_min double",
                "alter table meta.backtest_task add column if not exists final_asset_max double",
                "alter table meta.backtest_task add column if not exists final_return_avg double",
                "alter table meta.backtest_task add column if not exists final_return_min double",
                "alter table meta.backtest_task add column if not exists final_return_max double",
                "alter table meta.backtest_task add column if not exists started_at timestamp",
                "alter table meta.backtest_task add column if not exists finished_at timestamp",
                "alter table meta.backtest_task add column if not exists logs varchar default ''",
            ):
                connection.execute(statement)
            connection.execute(
                """
                create table if not exists meta.backtest_signal (
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
            connection.execute(
                """
                create table if not exists meta.backtest_buy_order (
                    task_id bigint not null,
                    run_no bigint not null default 1,
                    trade_date date not null,
                    code varchar not null,
                    code_name varchar,
                    buy_price double not null,
                    quantity bigint not null,
                    amount double not null,
                    fee double not null,
                    cash_after double not null,
                    signal_json varchar,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                "alter table meta.backtest_signal add column if not exists universe_json varchar"
            )
            connection.execute(
                "alter table meta.backtest_buy_order add column if not exists run_no bigint default 1"
            )
            connection.execute(
                """
                create table if not exists meta.backtest_sell_order (
                    task_id bigint not null,
                    run_no bigint not null default 1,
                    trade_date date not null,
                    code varchar not null,
                    code_name varchar,
                    sell_price double not null,
                    quantity bigint not null,
                    amount double not null,
                    fee double not null,
                    cash_after double not null,
                    buy_date date,
                    buy_price double,
                    pnl double,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                "alter table meta.backtest_sell_order add column if not exists run_no bigint default 1"
            )
            connection.execute(
                """
                create table if not exists meta.backtest_daily_snapshot (
                    task_id bigint not null,
                    run_no bigint not null default 1,
                    trade_date date not null,
                    total_asset double not null,
                    cash double not null,
                    holding_market_value double not null,
                    holding_count bigint not null,
                    watch_count bigint not null,
                    holding_json varchar not null,
                    watch_json varchar not null,
                    created_at timestamp not null default current_timestamp
                )
                """
            )
            connection.execute(
                "alter table meta.backtest_daily_snapshot add column if not exists run_no bigint default 1"
            )
            self._migrate_my_task_backtests(connection)

    def create_task(
        self,
        *,
        strategy_name: str,
        start_date: date,
        end_date: date,
        initial_cash: float,
        simulation_runs: int,
        initial_log: str,
    ) -> BacktestTaskDTO:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                """
                insert into meta.backtest_task(
                    status, strategy_name, start_date, end_date, initial_cash,
                    simulation_runs, completed_runs, started_at, logs
                )
                values ('running', ?, ?, ?, ?, ?, 0, current_timestamp, ?)
                returning *
                """,
                [
                    strategy_name,
                    start_date,
                    end_date,
                    initial_cash,
                    simulation_runs,
                    self._format_log(initial_log),
                ],
            ).fetchone()
        task = self._to_backtest_task(row)
        if task is None:
            raise RuntimeError("failed to create backtest task")
        return task

    def append_task_log(self, task_id: int, message: str) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                "select logs from meta.backtest_task where id = ?",
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.backtest_task
                set logs = ?, updated_at = current_timestamp
                where id = ?
                """,
                [self._trim_logs(logs + self._format_log(message)), task_id],
            )

    def update_task_progress(
        self,
        *,
        task_id: int,
        completed_runs: int | None = None,
        trading_day_count: int | None = None,
        signal_count: int | None = None,
    ) -> None:
        assignments = ["updated_at = current_timestamp"]
        values: list[Any] = []
        if completed_runs is not None:
            assignments.append("completed_runs = ?")
            values.append(completed_runs)
        if trading_day_count is not None:
            assignments.append("trading_day_count = ?")
            values.append(trading_day_count)
        if signal_count is not None:
            assignments.append("signal_count = ?")
            values.append(signal_count)
        values.append(task_id)
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                f"update meta.backtest_task set {', '.join(assignments)} where id = ?",
                values,
            )

    def finish_task(
        self,
        *,
        task_id: int,
        status: str,
        message: str,
        completed_runs: int | None = None,
        final_assets: list[float] | None = None,
        initial_cash: float | None = None,
    ) -> None:
        if status not in {"success", "error"}:
            raise ValueError(f"invalid backtest task status: {status}")
        final_asset_avg = final_asset_min = final_asset_max = None
        final_return_avg = final_return_min = final_return_max = None
        if final_assets:
            final_asset_avg = sum(final_assets) / len(final_assets)
            final_asset_min = min(final_assets)
            final_asset_max = max(final_assets)
            if initial_cash is not None and initial_cash > 0:
                returns = [(value - initial_cash) / initial_cash for value in final_assets]
                final_return_avg = sum(returns) / len(returns)
                final_return_min = min(returns)
                final_return_max = max(returns)

        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                "select logs from meta.backtest_task where id = ?",
                [task_id],
            ).fetchone()
            logs = "" if row is None else row[0] or ""
            connection.execute(
                """
                update meta.backtest_task
                set status = ?,
                    completed_runs = coalesce(?, completed_runs),
                    final_asset_avg = coalesce(?, final_asset_avg),
                    final_asset_min = coalesce(?, final_asset_min),
                    final_asset_max = coalesce(?, final_asset_max),
                    final_return_avg = coalesce(?, final_return_avg),
                    final_return_min = coalesce(?, final_return_min),
                    final_return_max = coalesce(?, final_return_max),
                    logs = ?,
                    finished_at = current_timestamp,
                    updated_at = current_timestamp
                where id = ?
                """,
                [
                    status,
                    completed_runs,
                    final_asset_avg,
                    final_asset_min,
                    final_asset_max,
                    final_return_avg,
                    final_return_min,
                    final_return_max,
                    self._trim_logs(logs + self._format_log(message)),
                    task_id,
                ],
            )

    def finish_running_tasks(self, message: str) -> int:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            rows = connection.execute(
                """
                select id, logs
                from meta.backtest_task
                where status = 'running'
                order by id
                """
            ).fetchall()
            for task_id, logs in rows:
                connection.execute(
                    """
                    update meta.backtest_task
                    set status = 'error',
                        logs = ?,
                        finished_at = current_timestamp,
                        updated_at = current_timestamp
                    where id = ?
                    """,
                    [
                        self._trim_logs((logs or "") + self._format_log(message)),
                        task_id,
                    ],
                )
        return len(rows)

    def get_task(self, task_id: int) -> BacktestTaskDTO | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select *
                from meta.backtest_task
                where id = ?
                """,
                [task_id],
            ).fetchone()
        return self._to_backtest_task(row)

    def get_latest_task(self) -> BacktestTaskDTO | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select *
                from meta.backtest_task
                order by id desc
                limit 1
                """
            ).fetchone()
        return self._to_backtest_task(row)

    def list_tasks(self, limit: int = 100) -> list[BacktestTaskDTO]:
        self.ensure_tables()
        normalized_limit = max(1, min(limit, 500))
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select *
                from meta.backtest_task
                order by id desc
                limit ?
                """,
                [normalized_limit],
            ).fetchall()
        return [task for row in rows for task in [self._to_backtest_task(row)] if task is not None]

    def clear_task_rows(self, task_id: int) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            for table in (
                "meta.backtest_signal",
                "meta.backtest_buy_order",
                "meta.backtest_sell_order",
                "meta.backtest_daily_snapshot",
            ):
                connection.execute(f"delete from {table} where task_id = ?", [task_id])

    def get_trading_dates(self, *, start_date: date, end_date: date) -> list[date]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select cal_date
                from tushare.trade_cal
                where cal_date between ? and ?
                  and is_open = 1
                order by cal_date
                """,
                [start_date, end_date],
            ).fetchall()
        return [row[0] for row in rows if isinstance(row[0], date)]

    def get_bar_map(self, *, trade_date: date, codes: list[str]) -> dict[str, dict[str, Any]]:
        if not codes:
            return {}
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select trade_date, code, open, high, low, close, volume, tradestatus
                from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                where trade_date = ?
                  and code in (select unnest(?))
                """,
                [trade_date, codes],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return {
            row[1]: self._normalize_row(columns, row)
            for row in rows
            if isinstance(row[1], str)
        }

    def insert_signals(
        self,
        *,
        task_id: int,
        trade_date: date,
        strategy_name: str,
        signals: list[dict[str, Any]],
    ) -> None:
        if not signals:
            return
        rows = [
            [
                task_id,
                trade_date,
                strategy_name,
                item["code"],
                item.get("code_name"),
                self._to_json(item.get("universe") or {}),
                self._to_json(item.get("signal") or {"triggered": True}),
            ]
            for item in signals
        ]
        with self.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                """
                insert into meta.backtest_signal(
                    task_id, trade_date, strategy_name, code, code_name,
                    universe_json, signal_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def insert_buy_order(self, **kwargs: Any) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                insert into meta.backtest_buy_order(
                    task_id, run_no, trade_date, code, code_name, buy_price, quantity,
                    amount, fee, cash_after, signal_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    kwargs["task_id"],
                    kwargs["run_no"],
                    kwargs["trade_date"],
                    kwargs["code"],
                    kwargs.get("code_name"),
                    kwargs["buy_price"],
                    kwargs["quantity"],
                    kwargs["amount"],
                    kwargs["fee"],
                    kwargs["cash_after"],
                    self._to_json(kwargs.get("signal") or {}),
                ],
            )

    def insert_sell_order(self, **kwargs: Any) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                insert into meta.backtest_sell_order(
                    task_id, run_no, trade_date, code, code_name, sell_price, quantity,
                    amount, fee, cash_after, buy_date, buy_price, pnl
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    kwargs["task_id"],
                    kwargs["run_no"],
                    kwargs["trade_date"],
                    kwargs["code"],
                    kwargs.get("code_name"),
                    kwargs["sell_price"],
                    kwargs["quantity"],
                    kwargs["amount"],
                    kwargs["fee"],
                    kwargs["cash_after"],
                    kwargs.get("buy_date"),
                    kwargs.get("buy_price"),
                    kwargs.get("pnl"),
                ],
            )

    def insert_daily_snapshot(self, **kwargs: Any) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                insert into meta.backtest_daily_snapshot(
                    task_id, run_no, trade_date, total_asset, cash, holding_market_value,
                    holding_count, watch_count, holding_json, watch_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    kwargs["task_id"],
                    kwargs["run_no"],
                    kwargs["trade_date"],
                    kwargs["total_asset"],
                    kwargs["cash"],
                    kwargs["holding_market_value"],
                    kwargs["holding_count"],
                    kwargs["watch_count"],
                    self._to_json(kwargs.get("holdings") or []),
                    self._to_json(kwargs.get("watch_items") or []),
                ],
            )

    def _to_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=self._normalize_value)

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
        return value

    def _migrate_my_task_backtests(self, connection: Any) -> None:
        my_task_exists = connection.execute(
            """
            select count(*)
            from information_schema.tables
            where table_schema = 'meta' and table_name = 'my_task'
            """
        ).fetchone()[0]
        if int(my_task_exists or 0) == 0:
            return
        rows = connection.execute(
            """
            select id, logs, status, created_at, updated_at
            from meta.my_task
            where type = 'backtest'
              and id not in (select id from meta.backtest_task)
            order by id
            """
        ).fetchall()
        for task_id, logs, status, created_at, updated_at in rows:
            parsed = self._parse_backtest_task_logs(logs or "")
            connection.execute(
                """
                insert into meta.backtest_task(
                    id, status, strategy_name, start_date, end_date, initial_cash,
                    simulation_runs, completed_runs, started_at, finished_at,
                    created_at, updated_at, logs
                )
                values (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                [
                    task_id,
                    status or "error",
                    parsed["strategy_name"],
                    parsed["start_date"],
                    parsed["end_date"],
                    parsed["initial_cash"],
                    parsed["simulation_runs"],
                    created_at,
                    None if status == "running" else updated_at,
                    created_at,
                    updated_at,
                    logs or "",
                ],
            )

    def _parse_backtest_task_logs(self, logs: str) -> dict[str, Any]:
        import re

        strategy_match = re.search(r"strategy=([^,\]\s]+)", logs)
        range_match = re.search(r"range=(\d{4}-\d{2}-\d{2})->(\d{4}-\d{2}-\d{2})", logs)
        cash_match = re.search(r"initial_cash=([0-9.]+)", logs)
        runs_match = re.search(r"simulation_runs=(\d+)", logs)
        return {
            "strategy_name": strategy_match.group(1) if strategy_match else "unknown",
            "start_date": date.fromisoformat(range_match.group(1)) if range_match else date(1970, 1, 1),
            "end_date": date.fromisoformat(range_match.group(2)) if range_match else date(1970, 1, 1),
            "initial_cash": float(cash_match.group(1)) if cash_match else 0.0,
            "simulation_runs": int(runs_match.group(1)) if runs_match else 0,
        }

    def _format_log(self, message: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {message}\n"

    def _trim_logs(self, logs: str) -> str:
        lines = logs.splitlines()
        if len(lines) <= self.MAX_LOG_LINES:
            return logs
        return "\n".join(lines[-self.MAX_LOG_LINES :]) + "\n"

    def _to_backtest_task(self, row: tuple | None) -> BacktestTaskDTO | None:
        if row is None:
            return None
        (
            task_id,
            status,
            strategy_name,
            start_date,
            end_date,
            initial_cash,
            simulation_runs,
            completed_runs,
            trading_day_count,
            signal_count,
            final_asset_avg,
            final_asset_min,
            final_asset_max,
            final_return_avg,
            final_return_min,
            final_return_max,
            started_at,
            finished_at,
            created_at,
            updated_at,
            logs,
        ) = row
        return BacktestTaskDTO(
            id=None if task_id is None else int(task_id),
            status=status,
            strategy_name=strategy_name,
            start_date="" if start_date is None else str(start_date),
            end_date="" if end_date is None else str(end_date),
            initial_cash=float(initial_cash or 0),
            simulation_runs=int(simulation_runs or 0),
            completed_runs=int(completed_runs or 0),
            trading_day_count=None if trading_day_count is None else int(trading_day_count),
            signal_count=None if signal_count is None else int(signal_count),
            final_asset_avg=None if final_asset_avg is None else float(final_asset_avg),
            final_asset_min=None if final_asset_min is None else float(final_asset_min),
            final_asset_max=None if final_asset_max is None else float(final_asset_max),
            final_return_avg=None if final_return_avg is None else float(final_return_avg),
            final_return_min=None if final_return_min is None else float(final_return_min),
            final_return_max=None if final_return_max is None else float(final_return_max),
            started_at=None if started_at is None else str(started_at),
            finished_at=None if finished_at is None else str(finished_at),
            created_at=None if created_at is None else str(created_at),
            updated_at=None if updated_at is None else str(updated_at),
            logs=logs or "",
        )
