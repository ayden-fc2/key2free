from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.tushare_asset_service import TushareAssetService

router = APIRouter(prefix="/tushare-assets", tags=["tushare-assets"])


class TushareRefreshRequest(BaseModel):
    end_date: date
    skip_stk_mins_5min: bool = False


@router.get("/watermarks")
def list_watermarks() -> list[dict]:
    return TushareAssetService().list_watermarks()


@router.post("/refresh")
def start_refresh(request: TushareRefreshRequest) -> dict:
    return asdict(
        TushareAssetService().start_refresh(
            end_date=request.end_date,
            skip_stk_mins_5min=request.skip_stk_mins_5min,
        )
    )


@router.post("/refresh-index-dailybasic")
def refresh_index_dailybasic(request: TushareRefreshRequest) -> dict:
    task_id = TushareAssetService().refresh_index_dailybasic_only(end_date=request.end_date)
    return {
        "ok": True,
        "task_id": task_id,
        "message": "tushare index_dailybasic refresh completed",
    }


@router.get("/refresh-task")
def get_refresh_task(task_id: int | None = Query(default=None)) -> dict:
    task = TushareAssetService().get_refresh_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tushare refresh task not found")
    return task
