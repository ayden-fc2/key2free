from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_sql import TUSHARE_BAR_1D_QFQ_SQL, TUSHARE_UNIVERSE_DAILY_SQL


class SignalRepository:
    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()
        self._bar_1d_qfq_window_cache: dict[str, tuple[list[date], list[dict[str, Any]]]] = {}
        self._bar_1d_qfq_window_cache_max_date: date | None = None
        self._bar_1d_qfq_window_cache_limit: int | None = None
        self._bar_1d_qfq_window_cache_db_mtime_ns: int | None = None

    _BAR_1D_QFQ_CACHE_EXTRA_ROWS = 256

    _BAR_1D_QFQ_SIGNAL_COLUMNS = """
        trade_date,
        code,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        turn,
        tradestatus,
        pct_chg,
        is_st
    """

    def get_universe_daily(self, trade_date: date) -> list[dict[str, Any]]:
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select *
                from ({TUSHARE_UNIVERSE_DAILY_SQL}) universe
                where trade_date = ?
                order by code
                """,
                [trade_date],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return [self._normalize_row(columns, row) for row in rows]

    def get_universe_daily_range(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[date, dict[str, dict[str, Any]]]:
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select *
                from ({TUSHARE_UNIVERSE_DAILY_SQL}) universe
                where trade_date between ? and ?
                order by trade_date, code
                """,
                [start_date, end_date],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]

        grouped: dict[date, dict[str, dict[str, Any]]] = {}
        for row in rows:
            item = self._normalize_row(columns, row)
            trade_date_value = row[0]
            code = item.get("code")
            if not isinstance(trade_date_value, date) or not isinstance(code, str):
                continue
            grouped.setdefault(trade_date_value, {})[code] = item
        return grouped

    def get_universe_codes_range(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                select distinct code
                from ({TUSHARE_UNIVERSE_DAILY_SQL}) universe
                where trade_date between ? and ?
                  and code is not null
                order by code
                """,
                [start_date, end_date],
            ).fetchall()
        return [str(row[0]) for row in rows if row and row[0] is not None]

    def get_universe_daily_range_by_codes(
        self,
        *,
        start_date: date,
        end_date: date,
        codes: list[str],
    ) -> dict[date, dict[str, dict[str, Any]]]:
        if not codes:
            return {}

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select *
                from ({TUSHARE_UNIVERSE_DAILY_SQL}) universe
                where trade_date between ? and ?
                  and code in (select unnest(?))
                order by trade_date, code
                """,
                [start_date, end_date, codes],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]

        grouped: dict[date, dict[str, dict[str, Any]]] = {}
        for row in rows:
            item = self._normalize_row(columns, row)
            trade_date_value = row[0]
            code = item.get("code")
            if not isinstance(trade_date_value, date) or not isinstance(code, str):
                continue
            grouped.setdefault(trade_date_value, {})[code] = item
        return grouped

    def get_universe_daily_by_codes(
        self,
        *,
        trade_date: date,
        codes: list[str],
    ) -> list[dict[str, Any]]:
        if not codes:
            return []

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select *
                from ({TUSHARE_UNIVERSE_DAILY_SQL}) universe
                where trade_date = ?
                  and code in (select unnest(?))
                order by code
                """,
                [trade_date, codes],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return [self._normalize_row(columns, row) for row in rows]

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
                f"""
                select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
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

    def get_bar_1d_qfq_history_for_signal_range(
        self,
        *,
        codes: list[str],
        start_date: date,
        end_date: date,
        limit_before_start: int | None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not codes:
            return {}

        with self.duckdb.connect(read_only=True) as connection:
            if limit_before_start is None:
                result = connection.execute(
                    f"""
                    select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                    from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                    where trade_date <= ?
                      and code in (select unnest(?))
                    order by code, trade_date
                    """,
                    [end_date, codes],
                )
            else:
                result = connection.execute(
                    f"""
                    with ranked_before as (
                        select {self._BAR_1D_QFQ_SIGNAL_COLUMNS},
                               row_number() over (
                                   partition by code
                                   order by trade_date desc
                               ) as rn
                        from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                        where trade_date < ?
                          and code in (select unnest(?))
                    ),
                    limited_before as (
                        select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                        from ranked_before
                        where rn <= ?
                    ),
                    in_range as (
                        select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                        from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                        where trade_date between ? and ?
                          and code in (select unnest(?))
                    )
                    select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                    from (
                        select * from limited_before
                        union all
                        select * from in_range
                    )
                    order by code, trade_date
                    """,
                    [start_date, codes, limit_before_start, start_date, end_date, codes],
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
        limit_per_code: int | None = None,
    ) -> Iterator[tuple[str, list[dict[str, Any]]]]:
        if not codes:
            return
        if limit_per_code is not None:
            yield from self._iter_cached_bar_1d_qfq_history_groups(
                codes=codes,
                trade_date=trade_date,
                limit_per_code=limit_per_code,
            )
            return

        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
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

    def _iter_cached_bar_1d_qfq_history_groups(
        self,
        *,
        codes: list[str],
        trade_date: date,
        limit_per_code: int,
    ) -> Iterator[tuple[str, list[dict[str, Any]]]]:
        self._clear_bar_1d_qfq_cache_if_database_changed()
        if self._bar_1d_qfq_window_cache_limit != limit_per_code:
            self._clear_bar_1d_qfq_cache()
            self._bar_1d_qfq_window_cache_limit = limit_per_code

        ordered_codes = sorted(dict.fromkeys(codes))
        if (
            self._bar_1d_qfq_window_cache_max_date is not None
            and trade_date < self._bar_1d_qfq_window_cache_max_date
        ):
            self._clear_bar_1d_qfq_cache()

        missing_codes = [
            code
            for code in ordered_codes
            if code not in self._bar_1d_qfq_window_cache
        ]
        if missing_codes:
            self._replace_bar_1d_qfq_cache_groups(
                self._load_limited_bar_1d_qfq_history_groups(
                    codes=missing_codes,
                    trade_date=trade_date,
                    limit_per_code=limit_per_code,
                )
            )

        stale_codes_by_start_date: dict[date, list[str]] = {}
        for code in ordered_codes:
            if code in missing_codes:
                continue
            cached = self._bar_1d_qfq_window_cache.get(code)
            if cached is None:
                continue
            dates, _rows = cached
            if dates and dates[-1] < trade_date:
                stale_codes_by_start_date.setdefault(dates[-1], []).append(code)
        for start_date, stale_codes in stale_codes_by_start_date.items():
            self._append_bar_1d_qfq_cache_groups(
                self._load_incremental_bar_1d_qfq_history_groups(
                    codes=stale_codes,
                    start_exclusive=start_date,
                    end_inclusive=trade_date,
                )
            )
        self._bar_1d_qfq_window_cache_max_date = max(
            date_value
            for date_value in (
                self._bar_1d_qfq_window_cache_max_date,
                trade_date,
            )
            if date_value is not None
        )

        for code in ordered_codes:
            cached = self._bar_1d_qfq_window_cache.get(code)
            if cached is None:
                continue
            dates, rows = cached
            end_index = bisect_right(dates, trade_date)
            start_index = max(0, end_index - limit_per_code)
            yield code, rows[start_index:end_index]

    def _load_limited_bar_1d_qfq_history_groups(
        self,
        *,
        codes: list[str],
        trade_date: date,
        limit_per_code: int,
    ) -> dict[str, tuple[list[date], list[dict[str, Any]]]]:
        if not codes:
            return {}
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                with ranked as (
                    select {self._BAR_1D_QFQ_SIGNAL_COLUMNS},
                           row_number() over (
                               partition by code
                               order by trade_date desc
                           ) as rn
                    from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                    where trade_date <= ?
                      and code in (select unnest(?))
                )
                select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                from ranked
                where rn <= ?
                order by code, trade_date
                """,
                [trade_date, codes, limit_per_code],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return self._group_bar_rows_for_cache(columns, rows)

    def _load_incremental_bar_1d_qfq_history_groups(
        self,
        *,
        codes: list[str],
        start_exclusive: date,
        end_inclusive: date,
    ) -> dict[str, tuple[list[date], list[dict[str, Any]]]]:
        if not codes:
            return {}
        with self.duckdb.connect(read_only=True) as connection:
            result = connection.execute(
                f"""
                select {self._BAR_1D_QFQ_SIGNAL_COLUMNS}
                from ({TUSHARE_BAR_1D_QFQ_SQL}) bar
                where trade_date > ?
                  and trade_date <= ?
                  and code in (select unnest(?))
                order by code, trade_date
                """,
                [start_exclusive, end_inclusive, codes],
            )
            rows = result.fetchall()
            columns = [item[0] for item in result.description]
        return self._group_bar_rows_for_cache(columns, rows)

    def _group_bar_rows_for_cache(
        self,
        columns: list[str],
        rows: list[tuple[Any, ...]],
    ) -> dict[str, tuple[list[date], list[dict[str, Any]]]]:
        groups: dict[str, tuple[list[date], list[dict[str, Any]]]] = {}
        for row in rows:
            item = self._normalize_row(columns, row)
            code = item.get("code")
            trade_date_value = row[0]
            if not isinstance(code, str) or not isinstance(trade_date_value, date):
                continue
            dates, items = groups.setdefault(code, ([], []))
            dates.append(trade_date_value)
            items.append(item)
        return groups

    def _replace_bar_1d_qfq_cache_groups(
        self,
        groups: dict[str, tuple[list[date], list[dict[str, Any]]]],
    ) -> None:
        for code, group in groups.items():
            self._bar_1d_qfq_window_cache[code] = self._trim_bar_cache_group(group)

    def _append_bar_1d_qfq_cache_groups(
        self,
        groups: dict[str, tuple[list[date], list[dict[str, Any]]]],
    ) -> None:
        for code, (new_dates, new_rows) in groups.items():
            cached = self._bar_1d_qfq_window_cache.get(code)
            if cached is None:
                self._bar_1d_qfq_window_cache[code] = self._trim_bar_cache_group((new_dates, new_rows))
                continue
            dates, rows = cached
            dates.extend(new_dates)
            rows.extend(new_rows)
            self._bar_1d_qfq_window_cache[code] = self._trim_bar_cache_group((dates, rows))

    def _trim_bar_cache_group(
        self,
        group: tuple[list[date], list[dict[str, Any]]],
    ) -> tuple[list[date], list[dict[str, Any]]]:
        dates, rows = group
        cache_limit = (self._bar_1d_qfq_window_cache_limit or 0) + self._BAR_1D_QFQ_CACHE_EXTRA_ROWS
        if cache_limit <= 0 or len(rows) <= cache_limit:
            return dates, rows
        return dates[-cache_limit:], rows[-cache_limit:]

    def _clear_bar_1d_qfq_cache_if_database_changed(self) -> None:
        try:
            mtime_ns = self.duckdb.db_path.stat().st_mtime_ns
        except OSError:
            self._clear_bar_1d_qfq_cache()
            self._bar_1d_qfq_window_cache_db_mtime_ns = None
            return
        if self._bar_1d_qfq_window_cache_db_mtime_ns is None:
            self._bar_1d_qfq_window_cache_db_mtime_ns = mtime_ns
            return
        if self._bar_1d_qfq_window_cache_db_mtime_ns != mtime_ns:
            self._clear_bar_1d_qfq_cache()
            self._bar_1d_qfq_window_cache_db_mtime_ns = mtime_ns

    def _clear_bar_1d_qfq_cache(self) -> None:
        self._bar_1d_qfq_window_cache.clear()
        self._bar_1d_qfq_window_cache_max_date = None

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
