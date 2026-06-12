from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestTaskDTO:
    id: int | None
    status: str
    strategy_name: str
    start_date: str
    end_date: str
    initial_cash: float
    simulation_runs: int
    completed_runs: int
    trading_day_count: int | None
    signal_count: int | None
    final_asset_avg: float | None
    final_asset_min: float | None
    final_asset_max: float | None
    final_return_avg: float | None
    final_return_min: float | None
    final_return_max: float | None
    started_at: str | None
    finished_at: str | None
    created_at: str | None
    updated_at: str | None
    logs: str


@dataclass(frozen=True)
class BacktestStartDTO:
    task: BacktestTaskDTO
    message: str


@dataclass(frozen=True)
class BacktestRequestDTO:
    start_date: str
    end_date: str
    initial_cash: float
    strategy_name: str
