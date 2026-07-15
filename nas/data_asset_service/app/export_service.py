from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_repository import TUSHARE_ASSET_TABLE_NAMES

from .asset_runtime import nas_asset_runtime
from .operation_log import operation_log_store


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


class AssetExportService:
    def __init__(self) -> None:
        export_root = os.getenv("EXPORT_ROOT", "/app/data/exports")
        self.export_root = Path(export_root)

    def create_export(
        self,
        *,
        asset_table_name: str,
        start_date: date | None,
        end_date: date | None,
    ) -> dict[str, Any]:
        if asset_table_name not in TUSHARE_ASSET_TABLE_NAMES:
            raise ValueError("unsupported asset table")
        database = nas_asset_runtime.database_status()
        if not database["ready"]:
            raise RuntimeError(database["reason"])

        date_column = ASSET_DATE_COLUMNS[asset_table_name]
        if date_column is not None:
            if start_date is None or end_date is None:
                raise ValueError("start_date and end_date are required for dated assets")
            if end_date < start_date:
                raise ValueError("end_date must not be earlier than start_date")
            maximum_days = 7 if asset_table_name == "tushare.stk_mins_5min" else 120
            if (end_date - start_date).days + 1 > maximum_days:
                raise ValueError(f"date range exceeds {maximum_days} days")

        self._cleanup_expired()
        self.export_root.mkdir(parents=True, exist_ok=True)
        export_id = uuid4().hex
        parquet_path = self.export_root / f"{export_id}.parquet"
        metadata_path = self.export_root / f"{export_id}.json"
        where_sql = ""
        if date_column is not None:
            where_sql = (
                f"where {date_column} >= date '{start_date.isoformat()}' "
                f"and {date_column} <= date '{end_date.isoformat()}'"
            )
        parquet_literal = str(parquet_path).replace("'", "''")
        with DuckDBRepository().connect(read_only=True) as connection:
            row_count = int(
                connection.execute(
                    f"select count(*) from {asset_table_name} {where_sql}"
                ).fetchone()[0]
            )
            schema_rows = connection.execute(
                f"describe select * from {asset_table_name}"
            ).fetchall()
            connection.execute(
                f"""
                copy (
                    select * from {asset_table_name} {where_sql}
                ) to '{parquet_literal}' (format parquet, compression zstd)
                """
            )
        checksum = self._sha256(parquet_path)
        metadata = {
            "export_id": export_id,
            "asset_table_name": asset_table_name,
            "date_column": date_column,
            "start_date": None if start_date is None else str(start_date),
            "end_date": None if end_date is None else str(end_date),
            "row_count": row_count,
            "size_bytes": parquet_path.stat().st_size,
            "sha256": checksum,
            "columns": [
                {"name": row[0], "type": row[1]}
                for row in schema_rows
            ],
            "download_path": f"/api/v1/exports/{export_id}/download",
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        operation_log_store.append(
            operation="asset_export",
            status="success",
            source="api",
            message=f"exported {asset_table_name} rows={row_count}",
            details={key: value for key, value in metadata.items() if key != "columns"},
        )
        return metadata

    def get_export(self, export_id: str) -> tuple[dict[str, Any], Path]:
        if len(export_id) != 32 or not all(character in "0123456789abcdef" for character in export_id):
            raise ValueError("invalid export id")
        metadata_path = self.export_root / f"{export_id}.json"
        parquet_path = self.export_root / f"{export_id}.parquet"
        if not metadata_path.exists() or not parquet_path.exists():
            raise FileNotFoundError(export_id)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return metadata, parquet_path

    def _cleanup_expired(self) -> None:
        if not self.export_root.exists():
            return
        cutoff = time.time() - int(os.getenv("EXPORT_RETENTION_SECONDS", "86400"))
        for path in self.export_root.iterdir():
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


asset_export_service = AssetExportService()
