from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.services.nas_data_asset_service import (
    NasDataAssetClientError,
    nas_connection_store,
    nas_data_asset_client,
    nas_incremental_sync_service,
)


router = APIRouter(prefix="/nas-data-assets", tags=["nas-data-assets"])


class NasConnectionUpdate(BaseModel):
    scheme: Literal["http", "https"] = "http"
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        normalized = value.strip()
        if "://" in normalized or "/" in normalized:
            raise ValueError("host must contain only an IP address or hostname")
        return normalized


class RemoteConfigUpdate(BaseModel):
    tushare_token: str | None = Field(default=None, min_length=1)
    tushare_http_url: str | None = Field(default=None, min_length=1)
    tushare_mcp_url: str | None = None
    tushare_timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    schedule_enabled: bool | None = None
    schedule_hour: int | None = Field(default=None, ge=0, le=23)
    schedule_minute: int | None = Field(default=None, ge=0, le=59)
    advertised_host: str | None = Field(default=None, min_length=1)
    advertised_port: int | None = Field(default=None, ge=1, le=65535)


class RemoteRefreshRequest(BaseModel):
    end_date: date | None = None
    skip_stk_mins_5min: bool = False


class IncrementalSyncRequest(BaseModel):
    asset_table_names: list[str] | None = None
    include_stk_mins_5min: bool = True


def _nas_call(callable_: Any) -> Any:
    try:
        return callable_()
    except NasDataAssetClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/connection")
def get_connection() -> dict[str, Any]:
    values = nas_connection_store.load()
    return {**values, "base_url": nas_connection_store.base_url()}


@router.put("/connection")
def update_connection(request: NasConnectionUpdate) -> dict[str, Any]:
    values = nas_connection_store.update(request.model_dump())
    health = _nas_call(lambda: nas_data_asset_client.get("/health", timeout=10))
    return {
        **values,
        "base_url": nas_connection_store.base_url(),
        "health": health,
    }


@router.get("/status")
def get_status() -> dict[str, Any]:
    return _nas_call(lambda: nas_data_asset_client.get("/api/v1/status"))


@router.get("/remote-config")
def get_remote_config() -> dict[str, Any]:
    return _nas_call(lambda: nas_data_asset_client.get("/api/v1/config"))


@router.put("/remote-config")
def update_remote_config(request: RemoteConfigUpdate) -> dict[str, Any]:
    body = request.model_dump(exclude_unset=True)
    return _nas_call(lambda: nas_data_asset_client.put("/api/v1/config", body))


@router.get("/watermarks")
def compare_watermarks() -> list[dict[str, Any]]:
    return _nas_call(nas_incremental_sync_service.compare_watermarks)


@router.get("/logs")
def list_remote_logs(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]:
    return _nas_call(lambda: nas_data_asset_client.get(f"/api/v1/logs?limit={limit}"))


@router.post("/refresh")
def start_remote_refresh(request: RemoteRefreshRequest) -> dict[str, Any]:
    body = {
        "end_date": None if request.end_date is None else str(request.end_date),
        "skip_stk_mins_5min": request.skip_stk_mins_5min,
    }
    return _nas_call(lambda: nas_data_asset_client.post("/api/v1/refresh", body))


@router.get("/refresh-task")
def get_remote_refresh_task(task_id: int | None = Query(default=None)) -> dict[str, Any]:
    query = "" if task_id is None else f"?task_id={task_id}"
    return _nas_call(lambda: nas_data_asset_client.get(f"/api/v1/refresh-task{query}"))


@router.post("/sync")
def start_incremental_sync(request: IncrementalSyncRequest) -> dict[str, Any]:
    remote_status = _nas_call(lambda: nas_data_asset_client.get("/api/v1/status"))
    database = remote_status.get("database") or {}
    if not database.get("ready"):
        raise HTTPException(
            status_code=409,
            detail=database.get("reason") or "NAS DuckDB is not ready",
        )
    try:
        return nas_incremental_sync_service.start(
            asset_table_names=request.asset_table_names,
            include_stk_mins_5min=request.include_stk_mins_5min,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sync-task")
def get_incremental_sync_task() -> dict[str, Any]:
    task = nas_incremental_sync_service.get_task()
    if task is None:
        raise HTTPException(status_code=404, detail="NAS sync task not found")
    return task
