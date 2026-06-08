from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SignalDecision:
    triggered: bool
    min_stop_loss: float | None = None
    reference_take_profit: float | None = None
    signal_atr30: float | None = None
    ideal_buy_price: float | None = None
    max_watch_days: int | None = None


@dataclass(frozen=True)
class StockDataContext:
    code: str
    trade_date: date
    universe: dict[str, Any]
    bars_1d_qfq: list[dict[str, Any]]
