from __future__ import annotations

from dataclasses import dataclass

from app.dtos.data_asset_dto import TaskDTO


@dataclass(frozen=True)
class BacktestStartDTO:
    task: TaskDTO
    message: str


@dataclass(frozen=True)
class BacktestRequestDTO:
    start_date: str
    end_date: str
    initial_cash: float
    strategy_name: str
