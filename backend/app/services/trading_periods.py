from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class TradingPeriodClock:
    """Calendar-only trading clock for one open date."""

    trade_date: date
    period: str
    period_key: str
    period_index: int
    open_index: int
    previous_open_date: date | None
    next_open_date: date | None
    period_open_dates: tuple[date, ...]
    open_dates_window: tuple[date, ...]

    @property
    def period_start(self) -> date:
        return self.period_open_dates[0]

    @property
    def period_end(self) -> date:
        return self.period_open_dates[-1]

    @property
    def is_period_start(self) -> bool:
        return self.trade_date == self.period_start

    @property
    def is_period_end(self) -> bool:
        return self.trade_date == self.period_end

    @property
    def period_day_index(self) -> int:
        return self.period_open_dates.index(self.trade_date) + 1

    @property
    def period_day_count(self) -> int:
        return len(self.period_open_dates)

    def is_period_day(self, day_index: int) -> bool:
        return self.period_day_index == day_index

    def to_params(self) -> dict[str, object]:
        return {
            "trade_date": self.trade_date,
            "period": self.period,
            "period_key": self.period_key,
            "period_index": self.period_index,
            "open_index": self.open_index,
            "previous_open_date": self.previous_open_date,
            "next_open_date": self.next_open_date,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "is_period_start": self.is_period_start,
            "is_period_end": self.is_period_end,
            "period_day_index": self.period_day_index,
            "period_day_count": self.period_day_count,
            "period_open_dates": self.period_open_dates,
            "open_dates_window": self.open_dates_window,
        }


def build_weekly_trading_clocks(
    open_dates: Iterable[date],
    *,
    context_radius: int = 5,
) -> dict[date, TradingPeriodClock]:
    """Build ISO-week clocks from open trade dates.

    The input may include dates before/after the backtest range. That is
    intentional: exchange calendars are known ahead of time and let strategies
    identify holiday-shifted period starts/ends without reading future market
    data.
    """
    ordered = sorted(set(open_dates))
    by_week: dict[tuple[int, int], list[date]] = defaultdict(list)
    for item in ordered:
        iso = item.isocalendar()
        by_week[(iso.year, iso.week)].append(item)

    week_index_by_key = {
        key: index
        for index, key in enumerate(sorted(by_week), start=1)
    }
    result: dict[date, TradingPeriodClock] = {}
    for open_index, item in enumerate(ordered):
        iso = item.isocalendar()
        key = (iso.year, iso.week)
        start = max(0, open_index - max(context_radius, 0))
        end = min(len(ordered), open_index + max(context_radius, 0) + 1)
        result[item] = TradingPeriodClock(
            trade_date=item,
            period="W",
            period_key=f"{iso.year}-W{iso.week:02d}",
            period_index=week_index_by_key[key],
            open_index=open_index,
            previous_open_date=ordered[open_index - 1] if open_index > 0 else None,
            next_open_date=ordered[open_index + 1] if open_index + 1 < len(ordered) else None,
            period_open_dates=tuple(by_week[key]),
            open_dates_window=tuple(ordered[start:end]),
        )
    return result


def build_trading_clocks(
    open_dates: Iterable[date],
    *,
    period: str,
    context_radius: int = 5,
) -> dict[date, TradingPeriodClock]:
    if period == "W":
        return build_weekly_trading_clocks(
            open_dates,
            context_radius=context_radius,
        )
    raise ValueError(f"unsupported trading clock period: {period}")


def weekly_period_boundaries(open_dates: Iterable[date]) -> tuple[set[date], set[date]]:
    """Return first and last open day of each ISO week."""
    starts: set[date] = set()
    ends: set[date] = set()
    for clock in build_weekly_trading_clocks(open_dates).values():
        if clock.is_period_start:
            starts.add(clock.trade_date)
        if clock.is_period_end:
            ends.add(clock.trade_date)
    return starts, ends
