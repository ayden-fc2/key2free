from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.signal_service import SignalService, SignalServiceError
from app.services.strategy_registry import list_strategy_names

router = APIRouter(prefix="/signals", tags=["signals"])
signal_service = SignalService()


class DailySignalRequest(BaseModel):
    trade_date: date
    strategy_name: str
    lookback_trade_days: int = 1


class DailySignalTaskQuery(BaseModel):
    task_id: int | None = None
    trade_date: date | None = None
    strategy_name: str | None = None


class StockDataContextRequest(BaseModel):
    codes: list[str]


@router.get("/strategies")
def get_signal_strategies() -> dict[str, list[str]]:
    return {"strategies": list_strategy_names()}


@router.post("/daily")
def get_daily_signals(request: DailySignalRequest) -> dict:
    try:
        result = signal_service.get_daily_signals(
            trade_date=request.trade_date,
            strategy_name=request.strategy_name,
            lookback_trade_days=request.lookback_trade_days,
        )
    except SignalServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(result)


@router.post("/daily-task")
def start_daily_signal_task(request: DailySignalRequest) -> dict:
    try:
        result = signal_service.request_daily_signal_task(
            trade_date=request.trade_date,
            strategy_name=request.strategy_name,
            lookback_trade_days=request.lookback_trade_days,
        )
    except SignalServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(result)


@router.post("/daily-task/query")
def get_daily_signal_task(request: DailySignalTaskQuery) -> dict:
    task = signal_service.get_daily_signal_task(
        task_id=request.task_id,
        trade_date=request.trade_date,
        strategy_name=request.strategy_name,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="daily signal task not found")
    return asdict(task)


@router.get("/daily-task/{task_id}/result")
def get_daily_signal_task_result(task_id: int) -> dict:
    result = signal_service.get_daily_signal_task_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="daily signal result not found")
    return asdict(result)


@router.post("/stock-contexts")
def get_stock_data_contexts(request: StockDataContextRequest) -> dict:
    result = signal_service.get_stock_data_contexts(
        codes=request.codes,
    )
    return asdict(result)
