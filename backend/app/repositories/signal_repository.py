from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.repositories.duckdb_repository import DuckDBRepository


class SignalRepository:
    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def get_universe_daily(self, trade_date: date) -> list[dict[str, Any]]:
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                """
                select *
                from mart.universe_daily
                where trade_date = ?
                order by code
                """,
                [trade_date],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return [self._normalize_row(columns, row) for row in rows]

    def get_bar_1d_qfq_history(
        self,
        *,
        codes: list[str],
        trade_date: date,
    ) -> dict[str, list[dict[str, Any]]]:
        if not codes:
            return {}

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                """
                select *
                from mart.bar_1d_qfq
                where trade_date <= ?
                  and code in (select unnest(?))
                order by code, trade_date
                """,
                [trade_date, codes],
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

    def iter_bar_1d_qfq_history_groups(
        self,
        *,
        codes: list[str],
        trade_date: date,
    ) -> Iterator[tuple[str, list[dict[str, Any]]]]:
        if not codes:
            return

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                """
                select *
                from mart.bar_1d_qfq
                where trade_date <= ?
                  and code in (select unnest(?))
                order by code, trade_date
                """,
                [trade_date, codes],
            )
            columns = [item[0] for item in result.description]
            current_code: str | None = None
            current_bars: list[dict[str, Any]] = []

            while True:
                rows = result.fetchmany(10000)
                if not rows:
                    break
                for row in rows:
                    item = self._normalize_row(columns, row)
                    code = item.get("code")
                    if not isinstance(code, str):
                        continue
                    if current_code is None:
                        current_code = code
                    elif code != current_code:
                        yield current_code, current_bars
                        current_code = code
                        current_bars = []
                    current_bars.append(item)

            if current_code is not None:
                yield current_code, current_bars

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
