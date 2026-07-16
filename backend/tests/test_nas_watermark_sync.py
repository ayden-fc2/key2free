from __future__ import annotations

import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_repository import TushareRepository
from app.services.nas_data_asset_service import NasIncrementalSyncService


class _WatermarkClient:
    def __init__(self, watermark: dict[str, Any]) -> None:
        self.watermark = watermark
        self.export_requests = 0

    def get(self, path: str) -> list[dict[str, Any]]:
        if path != "/api/v1/watermarks":
            raise AssertionError(f"unexpected GET {path}")
        return [dict(self.watermark)]

    def post(self, path: str, body: dict[str, Any], *, timeout: int = 60) -> Any:
        self.export_requests += 1
        raise AssertionError(f"metadata-only sync must not POST {path}")


class NasWatermarkSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository = TushareRepository()
        self.repository.duckdb = DuckDBRepository(self.root / "data.duckdb")
        self.asset_table_name = "tushare.stk_mins_5min"

    def tearDown(self) -> None:
        DuckDBRepository.close_all()
        self.temp_dir.cleanup()

    def test_repository_replaces_complete_issue_snapshot(self) -> None:
        self.repository.synchronize_watermark(
            self.asset_table_name,
            earliest_trusted_watermark=date(2016, 12, 6),
            trusted_watermark=date(2026, 7, 15),
            issue_count=61,
            last_issue_at=datetime(2026, 7, 16, 2, 54, 20),
            last_issue_scope="20260714",
            last_issue_message="partial coverage 5197/5198",
            issue_log="first issue\nlatest issue\n",
        )

        row = self._watermark()

        self.assertEqual(row["trusted_watermark"], "2026-07-15")
        self.assertEqual(row["issue_count"], 61)
        self.assertEqual(row["last_issue_at"], "2026-07-16 02:54:20")
        self.assertEqual(row["last_issue_scope"], "20260714")
        self.assertEqual(row["last_issue_message"], "partial coverage 5197/5198")
        self.assertEqual(row["issue_log"], "first issue\nlatest issue\n")

    def test_current_data_watermark_still_synchronizes_issue_metadata(self) -> None:
        self.repository.synchronize_watermark(
            self.asset_table_name,
            earliest_trusted_watermark=date(2016, 12, 6),
            trusted_watermark=date(2026, 7, 15),
            issue_count=60,
            last_issue_at=datetime(2026, 7, 15, 2, 52, 10),
            last_issue_scope="20260713",
            last_issue_message="old issue",
            issue_log="old issue\n",
        )
        client = _WatermarkClient(
            {
                "asset_table_name": self.asset_table_name,
                "earliest_trusted_watermark": "2016-12-06",
                "trusted_watermark": "2026-07-15",
                "issue_count": 61,
                "last_issue_at": "2026-07-16 02:54:20",
                "last_issue_scope": "20260714",
                "last_issue_message": "partial coverage 5197/5198",
                "issue_log": "old issue\nlatest issue\n",
            }
        )
        service = NasIncrementalSyncService(client)  # type: ignore[arg-type]
        service.repository = self.repository
        service.incoming_root = self.root / "incoming"
        service.applied_root = self.root / "applied"

        comparison = service.compare_watermarks()[0]
        self.assertFalse(comparison["pending"])
        self.assertTrue(comparison["metadata_pending"])

        task = service.start(asset_table_names=[self.asset_table_name])
        deadline = time.monotonic() + 5
        while task["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
            task = service.get_task() or task

        self.assertEqual(task["status"], "success", task["logs"])
        self.assertEqual(client.export_requests, 0)
        self.assertIn("NAS issue metadata synchronized", task["logs"])
        row = self._watermark()
        self.assertEqual(row["issue_count"], 61)
        self.assertEqual(row["last_issue_scope"], "20260714")
        self.assertEqual(row["last_issue_message"], "partial coverage 5197/5198")
        self.assertEqual(row["issue_log"], "old issue\nlatest issue\n")
        self.assertFalse(service.compare_watermarks()[0]["metadata_pending"])

    def _watermark(self) -> dict[str, Any]:
        return next(
            row
            for row in self.repository.get_watermarks()
            if row["asset_table_name"] == self.asset_table_name
        )


if __name__ == "__main__":
    unittest.main()
