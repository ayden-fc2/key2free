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
        )
    except SignalServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(result)


@router.post("/stock-contexts")
def get_stock_data_contexts(request: StockDataContextRequest) -> dict:
    result = signal_service.get_stock_data_contexts(
        codes=request.codes,
    )
    return asdict(result)
