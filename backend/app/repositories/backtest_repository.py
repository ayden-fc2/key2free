from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.repositories.duckdb_repository import DuckDBRepository


class BacktestRepository:
    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def ensure_tables(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute("create schema if not exists meta")
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
                select calendar_date
                from source.trade_calendar
                where calendar_date between ? and ?
                  and is_trading_day = 1
                order by calendar_date
                """,
                [start_date, end_date],
            ).fetchall()
        return [row[0] for row in rows if isinstance(row[0], date)]

    def get_bar_map(self, *, trade_date: date, codes: list[str]) -> dict[str, dict[str, Any]]:
        if not codes:
            return {}
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                """
                select trade_date, code, open, high, low, close, volume, tradestatus
                from mart.bar_1d_qfq
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
