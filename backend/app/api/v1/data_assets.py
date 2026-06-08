from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.data_asset_service import DataAssetService
from app.services.mart_refresh_service import MartRefreshError

router = APIRouter(prefix="/data-assets", tags=["data-assets"])


@router.get("/stocks/summary")
def get_stock_data_asset_summary() -> dict:
    return asdict(DataAssetService().get_stock_data_asset_summary())


@router.get("/mart/summary")
def get_mart_data_asset_summary() -> dict:
    return asdict(DataAssetService().get_mart_data_asset_summary())


@router.post("/mart/refresh")
def refresh_mart_data_assets() -> dict:
    try:
        return asdict(DataAssetService().refresh_mart_data_assets())
    except MartRefreshError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{exc.dataset_name} mart refresh failed: {exc}",
        ) from exc


@router.post("/stocks/refresh")
def request_stock_data_asset_refresh(
    dataset_names: Optional[str] = Query(default=None),
    target_date: Optional[str] = Query(default=None),
) -> dict:
    return asdict(
        DataAssetService().request_stock_data_asset_refresh(
            target_date=target_date,
            dataset_names=dataset_names,
        )
    )


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
