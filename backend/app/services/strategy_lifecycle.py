from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol


Bar = tuple[float, ...]
"""(qfq_open, qfq_high, qfq_low, qfq_close, vol, pct_chg, prev_ma_10, qfq_pre_close)."""


@dataclass(frozen=True)
class MarketViews:
    """Strategy data view for one trading day.

    `history_by_code` is reserved for the T-1 10-bar wide-table window.
    `today_bars` only carries T-day observable market fields used by order rules.
    """

    today_bars: dict[str, Bar]
    previous_bars: dict[str, Bar] = field(default_factory=dict)
    history_by_code: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyContext:
    trade_date: date
    trade_index: int
    cash: float
    total_asset: float
    holdings: dict[str, Any]
    watch_pool: dict[str, Any]
    trade_records: dict[str, Any]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategySellDecision:
    code: str
    price: float
    quantity: int
    reason: str


@dataclass(frozen=True)
class StrategyBuyDecision:
    code: str
    code_name: str | None
    price: float
    quantity: int
    signal: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyWatchDecision:
    add: list[dict[str, Any]] = field(default_factory=list)
    keep: set[str] = field(default_factory=set)
    remove: set[str] = field(default_factory=set)


class StrategyLifecycle(Protocol):
    """Backtest lifecycle implemented by a strategy.

    select_signals runs after T close. Its view may expose each stock's visible
    daily wide-table window, including T, and default to daily fields only.
    Minute-derived fields are opt-in via strategy registration or strategy-owned
    queries. decide_sells and decide_buys run during T and must only use today's
    observable market fields plus T-1 history.
    """

    def select_signals(
        self,
        *,
        trade_date: date,
        view: Any,
    ) -> list[dict[str, Any]]:
        ...

    def decide_sells(
        self,
        *,
        context: StrategyContext,
        market: MarketViews,
    ) -> list[StrategySellDecision]:
        ...

    def decide_buys(
        self,
        *,
        context: StrategyContext,
        market: MarketViews,
    ) -> list[StrategyBuyDecision]:
        ...

    def update_watch_pool(
        self,
        *,
        context: StrategyContext,
        raw_signals: list[dict[str, Any]],
    ) -> StrategyWatchDecision:
        ...
