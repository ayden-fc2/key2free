from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DailySignalRequestDTO:
    trade_date: str
    strategy_name: str


@dataclass(frozen=True)
class StockDataContextDTO:
    code: str
    trade_date: str
    universe: dict[str, Any]
    bars_1d_qfq: list[dict[str, Any]]


@dataclass(frozen=True)
class DailySignalItemDTO:
    code: str
    code_name: str | None
    trade_date: str
    universe: dict[str, Any]
    signal: dict[str, Any] | None = None


@dataclass(frozen=True)
class DailySignalResultDTO:
    trade_date: str
    strategy_name: str
    universe_count: int
    signal_count: int
    signals: list[DailySignalItemDTO]


@dataclass(frozen=True)
class DailySignalTaskDTO:
    id: int | None
    status: str
    trade_date: str
    strategy_name: str
    universe_count: int | None
    processed_count: int
    signal_count: int | None
    started_at: str | None
    finished_at: str | None
    created_at: str | None
    updated_at: str | None
    logs: str


@dataclass(frozen=True)
class DailySignalTaskStartDTO:
    task: DailySignalTaskDTO
    message: str


@dataclass(frozen=True)
class StockDataContextResultDTO:
    contexts: list[StockDataContextDTO]
