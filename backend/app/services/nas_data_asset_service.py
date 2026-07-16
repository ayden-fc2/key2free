from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_repository import TUSHARE_ASSET_TABLE_NAMES, TushareRepository


ASSET_DATE_COLUMNS: dict[str, str | None] = {
    "tushare.trade_cal": "cal_date",
    "tushare.index_basic": None,
    "tushare.index_daily": "trade_date",
    "tushare.index_dailybasic": "trade_date",
    "tushare.bak_basic": "trade_date",
    "tushare.adj_factor": "trade_date",
    "tushare.daily": "trade_date",
    "tushare.daily_basic": "trade_date",
    "tushare.stk_mins_5min": "trade_date",
    "tushare.stock_daily_technical": "trade_date",
}


class NasDataAssetClientError(RuntimeError):
    pass


class NasConnectionStore:
    def __init__(self, path: Path | None = None) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self.path = path or root_dir / "data" / "nas_sync" / "nas_connection.json"
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        values = {
            "scheme": os.getenv("NAS_DATA_ASSET_SCHEME", "http"),
            "host": os.getenv("NAS_DATA_ASSET_HOST", "192.168.1.62"),
            "port": int(os.getenv("NAS_DATA_ASSET_PORT", "18080")),
        }
        with self._lock:
            if self.path.exists():
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    values.update(stored)
        return values

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.load()
            current.update(values)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(current, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
            return current

    def base_url(self) -> str:
        values = self.load()
        return f"{values['scheme']}://{values['host']}:{int(values['port'])}"


class NasDataAssetClient:
    def __init__(self, connection_store: NasConnectionStore) -> None:
        self.connection_store = connection_store

    def get(self, path: str, *, timeout: int = 30) -> Any:
        return self._request("GET", path, timeout=timeout)

    def post(self, path: str, body: dict[str, Any], *, timeout: int = 60) -> Any:
        return self._request("POST", path, body=body, timeout=timeout)

    def put(self, path: str, body: dict[str, Any], *, timeout: int = 30) -> Any:
        return self._request("PUT", path, body=body, timeout=timeout)

    def download(self, path: str, destination: Path, *, expected_sha256: str) -> None:
        url = self._url(path)
        request = urllib.request.Request(url=url, method="GET")
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(request, timeout=600) as response, destination.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            destination.unlink(missing_ok=True)
            raise NasDataAssetClientError(f"NAS export download failed: {exc}") from exc
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            destination.unlink(missing_ok=True)
            raise NasDataAssetClientError(
                f"NAS export checksum mismatch: expected={expected_sha256}, actual={actual_sha256}"
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: int,
    ) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {} if body is None else {"Content-Type": "application/json"}
        request = urllib.request.Request(
            url=self._url(path),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise NasDataAssetClientError(f"NAS HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise NasDataAssetClientError(f"NAS connection failed: {exc}") from exc

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.connection_store.base_url()}{path}"


class NasIncrementalSyncService:
    _lock = threading.RLock()
    _task: dict[str, Any] | None = None
    _thread: threading.Thread | None = None

    def __init__(self, client: NasDataAssetClient) -> None:
        self.client = client
        root_dir = Path(__file__).resolve().parents[3]
        self.incoming_root = root_dir / "data" / "nas_sync" / "incoming"
        self.applied_root = root_dir / "data" / "nas_sync" / "applied"
        self.repository = TushareRepository()

    def start(
        self,
        *,
        asset_table_names: list[str] | None = None,
        include_stk_mins_5min: bool = True,
    ) -> dict[str, Any]:
        selected = list(asset_table_names or TUSHARE_ASSET_TABLE_NAMES)
        unsupported = sorted(set(selected) - set(TUSHARE_ASSET_TABLE_NAMES))
        if unsupported:
            raise ValueError(f"unsupported assets: {', '.join(unsupported)}")
        if not include_stk_mins_5min:
            selected = [name for name in selected if name != "tushare.stk_mins_5min"]
        selected = [name for name in TUSHARE_ASSET_TABLE_NAMES if name in selected]

        with self._lock:
            if self._task is not None and self._task["status"] == "running":
                return dict(self._task)
            task_id = uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            self._task = {
                "id": task_id,
                "status": "running",
                "started_at": now,
                "updated_at": now,
                "finished_at": None,
                "current_asset_table_name": None,
                "completed_asset_count": 0,
                "total_asset_count": len(selected),
                "downloaded_bytes": 0,
                "imported_rows": 0,
                "logs": "",
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(task_id, selected),
                name=f"nas-incremental-sync-{task_id[:8]}",
                daemon=True,
            )
            self._thread.start()
            return dict(self._task)

    def get_task(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._task is None else dict(self._task)

    def compare_watermarks(self) -> list[dict[str, Any]]:
        remote_rows = self.client.get("/api/v1/watermarks")
        self.repository.ensure_tables()
        local_by_name = {
            row["asset_table_name"]: row
            for row in self.repository.get_watermarks()
        }
        rows = []
        for remote in remote_rows:
            name = remote["asset_table_name"]
            local = local_by_name.get(name, {})
            local_watermark = local.get("trusted_watermark")
            remote_watermark = remote.get("trusted_watermark")
            local_issue_count = int(local.get("issue_count") or 0)
            remote_issue_count = int(remote.get("issue_count") or 0)
            metadata_pending = any(
                (
                    local_issue_count != remote_issue_count,
                    local.get("last_issue_at") != remote.get("last_issue_at"),
                    local.get("last_issue_scope") != remote.get("last_issue_scope"),
                    local.get("last_issue_message") != remote.get("last_issue_message"),
                    (local.get("issue_log") or "") != (remote.get("issue_log") or ""),
                )
            )
            rows.append(
                {
                    "asset_table_name": name,
                    "local_earliest_trusted_watermark": local.get("earliest_trusted_watermark"),
                    "local_trusted_watermark": local_watermark,
                    "nas_earliest_trusted_watermark": remote.get("earliest_trusted_watermark"),
                    "nas_trusted_watermark": remote_watermark,
                    "pending": bool(
                        remote_watermark
                        and (local_watermark is None or local_watermark < remote_watermark)
                    ),
                    "metadata_pending": metadata_pending,
                    "local_issue_count": local_issue_count,
                    "local_last_issue_at": local.get("last_issue_at"),
                    "local_last_issue_scope": local.get("last_issue_scope"),
                    "local_last_issue_message": local.get("last_issue_message"),
                    "local_issue_log": local.get("issue_log") or "",
                    "nas_issue_count": remote_issue_count,
                    "nas_last_issue_at": remote.get("last_issue_at"),
                    "nas_last_issue_scope": remote.get("last_issue_scope"),
                    "nas_last_issue_message": remote.get("last_issue_message"),
                    "nas_issue_log": remote.get("issue_log") or "",
                }
            )
        return rows

    def _run(self, task_id: str, selected: list[str]) -> None:
        task_root = self.incoming_root / task_id
        task_root.mkdir(parents=True, exist_ok=True)
        try:
            comparisons = {
                row["asset_table_name"]: row
                for row in self.compare_watermarks()
            }
            for asset_table_name in selected:
                comparison = comparisons.get(asset_table_name)
                self._set_current_asset(asset_table_name)
                if comparison is None or not comparison["nas_trusted_watermark"]:
                    self._append_log(f"{asset_table_name}: NAS watermark is not ready; skipped")
                    self._complete_asset()
                    continue
                if not comparison["pending"] and ASSET_DATE_COLUMNS[asset_table_name] is not None:
                    self._synchronize_watermark_metadata(asset_table_name, comparison)
                    self._append_log(
                        f"{asset_table_name}: local data watermark already current; "
                        "NAS issue metadata synchronized"
                    )
                    self._complete_asset()
                    continue
                self._sync_asset(asset_table_name, comparison, task_root)
                self._synchronize_watermark_metadata(asset_table_name, comparison)
                self._complete_asset()
            self._finish("success")
        except Exception as exc:
            self._append_log(f"sync failed: {type(exc).__name__}: {exc}")
            self._finish("error")
        finally:
            for path in task_root.glob("*.parquet"):
                path.unlink(missing_ok=True)
            try:
                task_root.rmdir()
            except OSError:
                pass

    def _sync_asset(
        self,
        asset_table_name: str,
        comparison: dict[str, Any],
        task_root: Path,
    ) -> None:
        date_column = ASSET_DATE_COLUMNS[asset_table_name]
        if date_column is None:
            self._sync_slice(asset_table_name, None, None, task_root)
            remote_watermark = self._parse_date(comparison["nas_trusted_watermark"])
            self.repository.update_watermark(
                asset_table_name,
                remote_watermark,
                earliest_trusted_watermark=self._parse_date(
                    comparison["nas_earliest_trusted_watermark"]
                ),
            )
            return

        remote_end = self._parse_date(comparison["nas_trusted_watermark"])
        local_watermark = comparison["local_trusted_watermark"]
        remote_earliest = self._parse_date(comparison["nas_earliest_trusted_watermark"])
        start_date = (
            self._parse_date(local_watermark) + timedelta(days=1)
            if local_watermark
            else remote_earliest
        )
        chunk_days = 7 if asset_table_name == "tushare.stk_mins_5min" else 120
        cursor = start_date
        while cursor <= remote_end:
            chunk_end = min(remote_end, cursor + timedelta(days=chunk_days - 1))
            imported_rows, maximum_date = self._sync_slice(
                asset_table_name,
                cursor,
                chunk_end,
                task_root,
            )
            if imported_rows > 0 and maximum_date is not None:
                self.repository.update_watermark(
                    asset_table_name,
                    maximum_date,
                    earliest_trusted_watermark=remote_earliest,
                )
            cursor = chunk_end + timedelta(days=1)

    def _synchronize_watermark_metadata(
        self,
        asset_table_name: str,
        comparison: dict[str, Any],
    ) -> None:
        self.repository.synchronize_watermark(
            asset_table_name,
            earliest_trusted_watermark=self._parse_date(
                comparison["nas_earliest_trusted_watermark"]
            ),
            trusted_watermark=self._parse_date(comparison["nas_trusted_watermark"]),
            issue_count=int(comparison.get("nas_issue_count") or 0),
            last_issue_at=self._parse_datetime(comparison.get("nas_last_issue_at")),
            last_issue_scope=comparison.get("nas_last_issue_scope"),
            last_issue_message=comparison.get("nas_last_issue_message"),
            issue_log=comparison.get("nas_issue_log") or "",
        )

    def _sync_slice(
        self,
        asset_table_name: str,
        start_date: date | None,
        end_date: date | None,
        task_root: Path,
    ) -> tuple[int, date | None]:
        request_body = {
            "asset_table_name": asset_table_name,
            "start_date": None if start_date is None else str(start_date),
            "end_date": None if end_date is None else str(end_date),
        }
        metadata = self.client.post("/api/v1/exports", request_body, timeout=600)
        if metadata["date_column"] is None and int(metadata["row_count"]) <= 0:
            raise RuntimeError(f"refusing to replace static asset {asset_table_name} with an empty export")
        parquet_path = task_root / f"{metadata['export_id']}.parquet"
        self.client.download(
            metadata["download_path"],
            parquet_path,
            expected_sha256=metadata["sha256"],
        )
        self._increment("downloaded_bytes", int(metadata["size_bytes"]))
        imported_rows, maximum_date = self._import_slice(
            asset_table_name=asset_table_name,
            date_column=metadata["date_column"],
            start_date=start_date,
            end_date=end_date,
            parquet_path=parquet_path,
        )
        self._increment("imported_rows", imported_rows)
        self._write_manifest(metadata, imported_rows, maximum_date)
        self._append_log(
            f"{asset_table_name} {start_date or 'full'}->{end_date or 'full'} "
            f"rows={imported_rows} bytes={metadata['size_bytes']}"
        )
        parquet_path.unlink(missing_ok=True)
        return imported_rows, maximum_date

    def _import_slice(
        self,
        *,
        asset_table_name: str,
        date_column: str | None,
        start_date: date | None,
        end_date: date | None,
        parquet_path: Path,
    ) -> tuple[int, date | None]:
        self.repository.ensure_tables()
        with DuckDBRepository().connect(read_only=False) as connection:
            target_columns = {
                row[0]
                for row in connection.execute(f"describe select * from {asset_table_name}").fetchall()
            }
            source_columns = {
                row[0]
                for row in connection.execute(
                    "describe select * from read_parquet(?)",
                    [str(parquet_path)],
                ).fetchall()
            }
            if target_columns != source_columns:
                missing = sorted(target_columns - source_columns)
                extra = sorted(source_columns - target_columns)
                raise RuntimeError(
                    f"schema mismatch for {asset_table_name}: missing={missing}, extra={extra}"
                )
            source_count = int(
                connection.execute(
                    "select count(*) from read_parquet(?)",
                    [str(parquet_path)],
                ).fetchone()[0]
            )
            maximum_date = None
            if date_column is not None and source_count > 0:
                maximum_date = connection.execute(
                    f"select max({date_column}) from read_parquet(?)",
                    [str(parquet_path)],
                ).fetchone()[0]
            connection.execute("begin transaction")
            try:
                if date_column is None:
                    connection.execute(f"delete from {asset_table_name}")
                else:
                    connection.execute(
                        f"delete from {asset_table_name} where {date_column} >= ? and {date_column} <= ?",
                        [start_date, end_date],
                    )
                connection.execute(
                    f"insert into {asset_table_name} by name select * from read_parquet(?)",
                    [str(parquet_path)],
                )
                connection.execute("commit")
            except Exception:
                connection.execute("rollback")
                raise
        return source_count, maximum_date

    def _write_manifest(
        self,
        metadata: dict[str, Any],
        imported_rows: int,
        maximum_date: date | None,
    ) -> None:
        self.applied_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            **metadata,
            "imported_rows": imported_rows,
            "maximum_imported_date": None if maximum_date is None else str(maximum_date),
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.applied_root / f"{metadata['export_id']}.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _set_current_asset(self, asset_table_name: str) -> None:
        with self._lock:
            if self._task is not None:
                self._task["current_asset_table_name"] = asset_table_name
                self._task["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _complete_asset(self) -> None:
        self._increment("completed_asset_count", 1)

    def _increment(self, field: str, value: int) -> None:
        with self._lock:
            if self._task is not None:
                self._task[field] = int(self._task[field]) + value
                self._task["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            if self._task is not None:
                self._task["logs"] += f"[{timestamp}] {message}\n"
                self._task["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _finish(self, status: str) -> None:
        with self._lock:
            if self._task is not None:
                now = datetime.now(timezone.utc).isoformat()
                self._task["status"] = status
                self._task["updated_at"] = now
                self._task["finished_at"] = now

    @staticmethod
    def _parse_date(value: str | date | None) -> date:
        if isinstance(value, date):
            return value
        if not value:
            raise ValueError("watermark date is missing")
        return date.fromisoformat(str(value))

    @staticmethod
    def _parse_datetime(value: str | datetime | None) -> datetime | None:
        if isinstance(value, datetime) or value is None:
            return value
        normalized = str(value).strip().replace("Z", "+00:00")
        return None if not normalized else datetime.fromisoformat(normalized)


nas_connection_store = NasConnectionStore()
nas_data_asset_client = NasDataAssetClient(nas_connection_store)
nas_incremental_sync_service = NasIncrementalSyncService(nas_data_asset_client)
