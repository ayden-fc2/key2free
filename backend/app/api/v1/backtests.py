from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    start_date: date
    end_date: date
    initial_cash: float
    strategy_name: str


@router.post("/run")
def run_backtest(request: BacktestRequest) -> dict:
    try:
        return asdict(
            BacktestService().request_backtest(
                start_date=request.start_date,
                end_date=request.end_date,
                initial_cash=request.initial_cash,
                strategy_name=request.strategy_name,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/task")
def get_backtest_task(task_id: int | None = Query(default=None)) -> dict:
    task = BacktestService().get_backtest_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="backtest task not found")
    return asdict(task)


@router.get("/tasks")
def list_backtest_tasks(limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:
    return [asdict(task) for task in BacktestService().list_backtest_tasks(limit=limit)]
