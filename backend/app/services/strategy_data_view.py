from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

import pandas as pd

from app.entities.stock_data_context import StockDailyFrame


@dataclass(frozen=True)
class SignalDataView:
    """Read-only strategy signal view for one T date.

    Signal selection runs after T close, so this view may expose records whose
    trade_date is <= T, including the full T daily row. Future rows are rejected
    at access time even if a caller accidentally built the view from a wider
    source frame.
    """

    trade_date: date
    source: Any
    max_window: int = 200
    index_source: Any | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "_visible_rows", None)
        object.__setattr__(self, "_cross_section_rows", None)

    def cross_section(self, columns: Iterable[str] | None = None) -> Any:
        """Return the T-day full-market cross-section."""
        base = self._cross_section_base()
        frame = self._columns(base, columns)
        self._assert_no_future(frame, include_trade_date=True)
        return frame.copy()

    def to_frame(
        self,
        columns: Iterable[str] | None = None,
        *,
        window: int | None = None,
        codes: Iterable[str] | None = None,
    ) -> Any:
        """Return visible records capped to the latest `window` records per stock."""
        resolved_window = self._resolve_window(window)
        if resolved_window <= 0:
            frame = self.cross_section(columns=columns)
        else:
            frame = self._visible_base()
            if codes is not None:
                code_set = {str(code) for code in codes}
                frame = frame[frame["code"].astype(str).isin(code_set)]
            frame = self._tail_by_code(frame, resolved_window)
            frame = self._columns(frame, columns)
        self._assert_no_future(frame, include_trade_date=True)
        return frame.copy()

    def history_by_stock(
        self,
        *,
        columns: Iterable[str] | None = None,
        window: int | None = None,
        codes: Iterable[str] | None = None,
    ) -> dict[str, StockDailyFrame]:
        """Return per-stock columnar windows visible to the signal function."""
        frame = self.to_frame(columns=columns, window=window, codes=codes)
        result: dict[str, StockDailyFrame] = {}
        if frame.empty:
            return result
        for code, group in frame.groupby("code", sort=False):
            result[str(code)] = self._to_stock_frame(str(code), group)
        return result

    def iter_stock_history(
        self,
        *,
        columns: Iterable[str] | None = None,
        window: int | None = None,
        codes: Iterable[str] | None = None,
    ) -> Iterable[tuple[str, StockDailyFrame]]:
        """Yield per-stock windows one at a time."""
        resolved_window = self._resolve_window(window)
        frame = self._visible_base()
        if codes is not None:
            code_set = {str(code) for code in codes}
            frame = frame[frame["code"].astype(str).isin(code_set)]
        frame = self._columns(frame, columns)
        self._assert_no_future(frame, include_trade_date=True)
        if frame.empty:
            return
        for code, group in frame.groupby("code", sort=False):
            yield str(code), self._to_stock_frame(
                str(code),
                group.sort_values("trade_date").tail(resolved_window),
            )

    def index_history(
        self,
        ts_code: str,
        *,
        columns: Iterable[str] | None = None,
        window: int | None = None,
    ) -> Any:
        """Return index daily rows visible to the signal function.

        Kept as a compatibility alias for index_daily_history().
        """
        return self.index_daily_history(ts_code, columns=columns, window=window)

    def index_daily_history(
        self,
        ts_code: str,
        *,
        columns: Iterable[str] | None = None,
        window: int | None = None,
    ) -> Any:
        """Return index OHLCV rows visible to the signal function."""
        return self._index_asset_history(
            ts_code,
            asset="daily",
            columns=columns,
            window=window,
        )

    def index_dailybasic_history(
        self,
        ts_code: str,
        *,
        columns: Iterable[str] | None = None,
        window: int | None = None,
    ) -> Any:
        """Return index daily-basic rows visible to the signal function."""
        return self._index_asset_history(
            ts_code,
            asset="dailybasic",
            columns=columns,
            window=window,
        )

    def _index_asset_history(
        self,
        ts_code: str,
        *,
        asset: str,
        columns: Iterable[str] | None,
        window: int | None,
    ) -> Any:
        if self.index_source is None:
            return pd.DataFrame(columns=["trade_date", "ts_code", "asset"])
        frame = self.index_source
        trade_dates = self._trade_dates(frame)
        asset_values = frame["asset"].astype(str) if "asset" in frame.columns else pd.Series("", index=frame.index)
        frame = frame[
            (frame["ts_code"].astype(str) == str(ts_code))
            & (asset_values == asset)
            & (trade_dates <= self.trade_date)
        ]
        if window is not None:
            resolved_window = self._resolve_index_window(window)
        else:
            resolved_window = 0
        if resolved_window > 0:
            frame = frame.sort_values("trade_date").tail(resolved_window)
        frame = self._index_columns(frame, columns)
        self._assert_no_future(frame, include_trade_date=True)
        return frame.copy()

    def _visible_base(self) -> Any:
        cached = getattr(self, "_visible_rows")
        if cached is None:
            trade_dates = self._trade_dates(self.source)
            cached = self.source[trade_dates <= self.trade_date]
            object.__setattr__(self, "_visible_rows", cached)
        return cached

    def _cross_section_base(self) -> Any:
        cached = getattr(self, "_cross_section_rows")
        if cached is None:
            trade_dates = self._trade_dates(self.source)
            cached = self.source[trade_dates == self.trade_date]
            object.__setattr__(self, "_cross_section_rows", cached)
        return cached

    def _resolve_window(self, window: int | None) -> int:
        if window is None:
            return self.max_window
        if window < 0:
            raise ValueError("signal history window must be >= 0")
        return min(int(window), self.max_window)

    def _resolve_index_window(self, window: int) -> int:
        if window < 0:
            raise ValueError("signal index history window must be >= 0")
        return int(window)

    def _columns(self, frame: Any, columns: Iterable[str] | None) -> Any:
        if columns is None:
            return frame
        selected = ["trade_date", "code"]
        for column in columns:
            if column not in selected:
                selected.append(column)
        existing = [column for column in selected if column in frame.columns]
        return frame[existing]

    def _index_columns(self, frame: Any, columns: Iterable[str] | None) -> Any:
        if columns is None:
            return frame
        selected = ["trade_date", "ts_code"]
        for column in columns:
            if column not in selected:
                selected.append(column)
        existing = [column for column in selected if column in frame.columns]
        return frame[existing]

    def _trade_dates(self, frame: Any) -> Any:
        if frame.empty:
            return pd.Series([], index=frame.index, dtype=object)
        if "trade_date" not in frame.columns:
            return pd.Series([], index=frame.index, dtype=object)
        return pd.to_datetime(
            frame["trade_date"],
            errors="coerce",
        ).dt.date

    def _tail_by_code(self, frame: Any, window: int) -> Any:
        if frame.empty:
            return frame
        return (
            frame.sort_values(["code", "trade_date"])
            .groupby("code", group_keys=False, sort=False)
            .tail(window)
        )

    def _assert_no_future(self, frame: Any, *, include_trade_date: bool) -> None:
        if frame.empty:
            return
        max_date = self._as_date(frame["trade_date"].max())
        if max_date is None:
            return
        if include_trade_date:
            if max_date > self.trade_date:
                raise ValueError(f"signal view includes future date {max_date} after {self.trade_date}")
        elif max_date >= self.trade_date:
            raise ValueError(f"trade view includes {max_date} at or after {self.trade_date}")

    def _as_date(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            return None
        return timestamp.date()

    def _to_stock_frame(self, code: str, group: Any) -> StockDailyFrame:
        ordered = group.sort_values("trade_date")
        trade_dates = list(ordered["trade_date"])
        columns = {
            column: ordered[column].to_numpy()
            for column in ordered.columns
            if column not in {"trade_date", "code"}
        }
        return StockDailyFrame(
            code=code,
            trade_dates=trade_dates,
            columns=columns,
        )
