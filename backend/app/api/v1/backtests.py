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
def list_backtest_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    latest_only: bool = Query(default=True),
) -> list[dict]:
    return [
        asdict(task)
        for task in BacktestService().list_backtest_tasks(
            limit=limit,
            latest_per_strategy=latest_only,
        )
    ]


@router.get("/detail")
def get_backtest_detail(
    task_id: int = Query(...),
    run_no: int = Query(default=1, ge=1),
    include_curves: bool = Query(default=True),
) -> dict:
    try:
        return BacktestService().repository.get_task_detail(
            task_id=task_id,
            run_no=run_no,
            include_curves=include_curves,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
