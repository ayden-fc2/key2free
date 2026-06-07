from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.data_asset_service import DataAssetService

router = APIRouter(prefix="/data-assets", tags=["data-assets"])


@router.get("/stocks/summary")
def get_stock_data_asset_summary() -> dict:
    return asdict(DataAssetService().get_stock_data_asset_summary())


@router.post("/stocks/refresh")
def request_stock_data_asset_refresh() -> dict:
    return asdict(DataAssetService().request_stock_data_asset_refresh())


@router.get("/source-update-task")
def get_source_update_task(task_id: Optional[int] = Query(default=None)) -> dict:
    task = DataAssetService().get_source_update_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="source_update task not found")
    return asdict(task)


@router.post("/source-update-task/stop")
def stop_source_update_task(
    task_id: Optional[int] = Query(default=None),
) -> dict:
    task = DataAssetService().stop_source_update_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="source_update task not found")
    return asdict(task)
