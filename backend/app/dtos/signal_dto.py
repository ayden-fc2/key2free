from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DailySignalRequestDTO:
    trade_date: str
    strategy_name: str


@dataclass(frozen=True)
class DailySignalItemDTO:
    code: str
    code_name: str | None
    trade_date: str
    universe: dict[str, Any]


@dataclass(frozen=True)
class DailySignalResultDTO:
    trade_date: str
    strategy_name: str
    universe_count: int
    signal_count: int
    signals: list[DailySignalItemDTO]
