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

    def _visible_base(self) -> Any:
        cached = getattr(self, "_visible_rows")
        if cached is None:
            cached = self.source[self.source["trade_date"] <= self.trade_date]
            object.__setattr__(self, "_visible_rows", cached)
        return cached

    def _cross_section_base(self) -> Any:
        cached = getattr(self, "_cross_section_rows")
        if cached is None:
            cached = self.source[self.source["trade_date"] == self.trade_date]
            object.__setattr__(self, "_cross_section_rows", cached)
        return cached

    def _resolve_window(self, window: int | None) -> int:
        if window is None:
            return self.max_window
        if window < 0:
            raise ValueError("signal history window must be >= 0")
        return min(int(window), self.max_window)

    def _columns(self, frame: Any, columns: Iterable[str] | None) -> Any:
        if columns is None:
            return frame
        selected = ["trade_date", "code"]
        for column in columns:
            if column not in selected:
                selected.append(column)
        existing = [column for column in selected if column in frame.columns]
        return frame[existing]

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
        max_date = frame["trade_date"].max()
        if include_trade_date:
            if max_date > self.trade_date:
                raise ValueError(f"signal view includes future date {max_date} after {self.trade_date}")
        elif max_date >= self.trade_date:
            raise ValueError(f"trade view includes {max_date} at or after {self.trade_date}")

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
