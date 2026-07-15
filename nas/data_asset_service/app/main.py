from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.repositories.duckdb_repository import DuckDBRepository

from .asset_runtime import nas_asset_runtime
from .config_store import service_config_store
from .export_service import asset_export_service
from .operation_log import operation_log_store
from .scheduler import nightly_refresh_scheduler


SERVICE_NAME = "key2free-data-asset-service"
SERVICE_VERSION = "0.2.0"


class ServiceConfigUpdate(BaseModel):
    tushare_token: str | None = Field(default=None, min_length=1)
    tushare_http_url: str | None = Field(default=None, min_length=1)
    tushare_mcp_url: str | None = None
    tushare_timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    schedule_enabled: bool | None = None
    schedule_hour: int | None = Field(default=None, ge=0, le=23)
    schedule_minute: int | None = Field(default=None, ge=0, le=59)
    advertised_host: str | None = Field(default=None, min_length=1)
    advertised_port: int | None = Field(default=None, ge=1, le=65535)


class RefreshRequest(BaseModel):
    end_date: date | None = None
    skip_stk_mins_5min: bool = False


class ExportRequest(BaseModel):
    asset_table_name: str
    start_date: date | None = None
    end_date: date | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    service_config_store.apply_tushare_config()
    stale_count = nas_asset_runtime.finish_stale_tasks()
    operation_log_store.append(
        operation="service_lifecycle",
        status="started",
        source="docker",
        message="NAS data asset service started",
        details={"stale_refresh_tasks_finished": stale_count},
    )
    nightly_refresh_scheduler.start()
    try:
        yield
    finally:
        nightly_refresh_scheduler.stop()
        DuckDBRepository.close_all()
        operation_log_store.append(
            operation="service_lifecycle",
            status="stopped",
            source="docker",
            message="NAS data asset service stopped",
        )


app = FastAPI(
    title="Key2Free Data Asset Service",
    description="NAS-hosted Tushare asset refresh and incremental export service.",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def runtime_status() -> dict[str, Any]:
    return {
        "service": SERVICE_NAME,
        "status": "ok",
        "version": SERVICE_VERSION,
        "sync_implemented": True,
        "database": nas_asset_runtime.database_status(),
        "scheduler": nightly_refresh_scheduler.status(),
        "config": service_config_store.public(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
def root() -> dict[str, Any]:
    return runtime_status()


@app.get("/health")
def health() -> dict[str, Any]:
    return runtime_status()


@app.get("/api/v1/status")
def status() -> dict[str, Any]:
    return runtime_status()


@app.get("/api/v1/config")
def get_config() -> dict[str, Any]:
    return service_config_store.public()


@app.put("/api/v1/config")
def update_config(request: ServiceConfigUpdate) -> dict[str, Any]:
    updates = request.model_dump(exclude_unset=True)
    service_config_store.update(updates)
    configured = service_config_store.apply_tushare_config()
    nightly_refresh_scheduler.notify_config_changed()
    operation_log_store.append(
        operation="service_config",
        status="success",
        source="api",
        message="service configuration hot-updated",
        details={
            "updated_fields": sorted(updates),
            "tushare_client_configured": configured,
        },
    )
    return service_config_store.public()


@app.get("/api/v1/database")
def database_status() -> dict[str, Any]:
    return nas_asset_runtime.database_status()


@app.get("/api/v1/watermarks")
def list_watermarks() -> list[dict[str, Any]]:
    return nas_asset_runtime.list_watermarks()


@app.post("/api/v1/refresh")
def start_refresh(request: RefreshRequest) -> dict[str, Any]:
    end_date = request.end_date or (date.today() - timedelta(days=1))
    result = nas_asset_runtime.start_refresh(
        end_date=end_date,
        source="manual",
        skip_stk_mins_5min=request.skip_stk_mins_5min,
    )
    if not result["ok"] and result["task_id"] is None:
        raise HTTPException(status_code=409, detail=result["message"])
    return result


@app.get("/api/v1/refresh-task")
def get_refresh_task(task_id: int | None = Query(default=None)) -> dict[str, Any]:
    task = nas_asset_runtime.get_refresh_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="refresh task not found")
    return task


@app.get("/api/v1/logs")
def list_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    operation: str | None = Query(default=None),
    log_status: str | None = Query(default=None, alias="status"),
) -> list[dict[str, Any]]:
    return operation_log_store.list(
        limit=limit,
        operation=operation,
        status=log_status,
    )


@app.post("/api/v1/exports")
def create_export(request: ExportRequest) -> dict[str, Any]:
    try:
        return asset_export_service.create_export(
            asset_table_name=request.asset_table_name,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/v1/exports/{export_id}/download")
def download_export(export_id: str) -> FileResponse:
    try:
        metadata, path = asset_export_service.get_export(export_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="export not found") from exc
    filename = f"{metadata['asset_table_name'].replace('.', '__')}_{export_id}.parquet"
    return FileResponse(path, media_type="application/vnd.apache.parquet", filename=filename)
