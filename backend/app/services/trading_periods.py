from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable


def weekly_period_boundaries(open_dates: Iterable[date]) -> tuple[set[date], set[date]]:
    """Return first and last open dates for each ISO trading week."""
    dates_by_week: dict[tuple[int, int], list[date]] = defaultdict(list)
    for trade_date in sorted(set(open_dates)):
        iso_year, iso_week, _ = trade_date.isocalendar()
        dates_by_week[(iso_year, iso_week)].append(trade_date)

    period_starts: set[date] = set()
    period_ends: set[date] = set()
    for week_dates in dates_by_week.values():
        if not week_dates:
            continue
        ordered = sorted(week_dates)
        period_starts.add(ordered[0])
        period_ends.add(ordered[-1])
    return period_starts, period_ends
