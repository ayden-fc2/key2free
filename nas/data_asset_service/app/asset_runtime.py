from __future__ import annotations

import os
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from app.repositories.duckdb_repository import DuckDBRepository
from app.services.tushare_asset_service import TushareAssetService

from .config_store import service_config_store
from .operation_log import operation_log_store


class NasAssetRuntime:
    def __init__(self) -> None:
        self.db_path = Path(os.getenv("DUCKDB_PATH", "/app/data/data.duckdb"))
        self._monitor_lock = threading.Lock()
        self._monitored_task_ids: set[int] = set()

    def database_status(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {
                "ready": False,
                "path": str(self.db_path),
                "size_bytes": 0,
                "reason": "DuckDB file has not been uploaded",
            }
        size_bytes = self.db_path.stat().st_size
        try:
            with DuckDBRepository(self.db_path).connect(read_only=True) as connection:
                table_count = int(
                    connection.execute(
                        """
                        select count(*)
                        from information_schema.tables
                        where table_schema = 'tushare'
                        """
                    ).fetchone()[0]
                )
                trade_cal_count = 0
                if table_count > 0:
                    has_trade_cal = connection.execute(
                        """
                        select count(*)
                        from information_schema.tables
                        where table_schema = 'tushare' and table_name = 'trade_cal'
                        """
                    ).fetchone()[0]
                    if has_trade_cal:
                        trade_cal_count = int(
                            connection.execute("select count(*) from tushare.trade_cal").fetchone()[0]
                        )
            ready = table_count > 0 and trade_cal_count > 0
            return {
                "ready": ready,
                "path": str(self.db_path),
                "size_bytes": size_bytes,
                "table_count": table_count,
                "trade_cal_count": trade_cal_count,
                "reason": None if ready else "DuckDB does not contain initialized Tushare assets",
            }
        except Exception as exc:
            return {
                "ready": False,
                "path": str(self.db_path),
                "size_bytes": size_bytes,
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def list_watermarks(self) -> list[dict[str, Any]]:
        if not self.database_status()["ready"]:
            return []
        return TushareAssetService().list_watermarks()

    def get_refresh_task(self, task_id: int | None = None) -> dict[str, Any] | None:
        if not self.database_status()["ready"]:
            return None
        return TushareAssetService().get_refresh_task(task_id)

    def start_refresh(
        self,
        *,
        end_date: date,
        source: str,
        skip_stk_mins_5min: bool = False,
    ) -> dict[str, Any]:
        database = self.database_status()
        if not database["ready"]:
            operation_log_store.append(
                operation="asset_refresh",
                status="skipped",
                source=source,
                message=database["reason"],
                details={"end_date": str(end_date)},
            )
            return {"ok": False, "task_id": None, "message": database["reason"]}
        if not service_config_store.apply_tushare_config():
            message = "Tushare token or proxy URL is not configured"
            operation_log_store.append(
                operation="asset_refresh",
                status="skipped",
                source=source,
                message=message,
                details={"end_date": str(end_date)},
            )
            return {"ok": False, "task_id": None, "message": message}

        result = TushareAssetService().start_refresh(
            end_date=end_date,
            skip_stk_mins_5min=skip_stk_mins_5min,
        )
        operation_log_store.append(
            operation="asset_refresh",
            status="started" if result.ok else "rejected",
            source=source,
            message=result.message,
            details={
                "task_id": result.task_id,
                "end_date": str(end_date),
                "skip_stk_mins_5min": skip_stk_mins_5min,
            },
        )
        if result.ok and result.task_id is not None:
            self._start_monitor(result.task_id, source)
        return {"ok": result.ok, "task_id": result.task_id, "message": result.message}

    def finish_stale_tasks(self) -> int:
        if not self.database_status()["ready"]:
            return 0
        # A refresh worker only exists inside this service process. On a fresh
        # container start every running task is stale, even if Linux reused its PID.
        return TushareAssetService().finish_running_tasks(
            "NAS service startup found a stale running refresh task and marked it as error.",
        )

    def _start_monitor(self, task_id: int, source: str) -> None:
        with self._monitor_lock:
            if task_id in self._monitored_task_ids:
                return
            self._monitored_task_ids.add(task_id)
        threading.Thread(
            target=self._monitor_refresh,
            args=(task_id, source),
            name=f"nas-refresh-monitor-{task_id}",
            daemon=True,
        ).start()

    def _monitor_refresh(self, task_id: int, source: str) -> None:
        try:
            while True:
                task = self.get_refresh_task(task_id)
                if task is None:
                    operation_log_store.append(
                        operation="asset_refresh",
                        status="error",
                        source=source,
                        message="refresh task disappeared",
                        details={"task_id": task_id},
                    )
                    return
                if task["status"] != "running":
                    operation_log_store.append(
                        operation="asset_refresh",
                        status=task["status"],
                        source=source,
                        message=f"refresh task {task['status']}",
                        details={
                            "task_id": task_id,
                            "finished_at": task.get("finished_at"),
                            "current_asset_table_name": task.get("current_asset_table_name"),
                            "current_watermark": task.get("current_watermark"),
                            "task_log_tail": str(task.get("logs") or "")[-4000:],
                        },
                    )
                    return
                time.sleep(5)
        finally:
            with self._monitor_lock:
                self._monitored_task_ids.discard(task_id)


nas_asset_runtime = NasAssetRuntime()
