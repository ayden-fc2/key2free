from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.repositories.duckdb_repository import DuckDBRepository
from app.repositories.tushare_repository import TushareRepository


class StockDailyTechnicalRebuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "data.duckdb"
        self.repository = TushareRepository()
        self.repository.duckdb = DuckDBRepository(self.db_path)
        self.repository.ensure_tables()

    def tearDown(self) -> None:
        DuckDBRepository.close_all()
        self.temp_dir.cleanup()

    def test_failed_staged_build_preserves_live_table(self) -> None:
        self._seed_daily([("000001.SZ", date(2017, 6, 1))])
        self._seed_live_row("OLD.SZ", date(2017, 6, 1))

        with (
            patch.object(
                self.repository,
                "_stock_daily_technical_columns",
                return_value=["ts_code", "code", "trade_date"],
            ),
            patch.object(
                self.repository,
                "_load_stock_daily_technical_base",
                side_effect=RuntimeError("calculation failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "calculation failed"):
                self.repository.rebuild_stock_daily_technical(
                    target_watermark=date(2017, 6, 1),
                )

        self.assertEqual(self._live_keys(), [("OLD.SZ", date(2017, 6, 1))])

    def test_validated_shards_replace_live_table_transactionally(self) -> None:
        target_watermark = date(2017, 6, 2)
        self._seed_daily(
            [
                ("000001.SZ", date(2017, 6, 1)),
                ("600000.SH", target_watermark),
            ]
        )
        self._seed_live_row("OLD.SZ", date(2017, 6, 1))

        def load_frame(*, connection, target_watermark, ts_codes):
            del connection, target_watermark
            rows = []
            for ts_code in ts_codes:
                trade_day = date(2017, 6, 1) if ts_code == "000001.SZ" else date(2017, 6, 2)
                rows.append(
                    {
                        "ts_code": ts_code,
                        "code": ts_code.lower(),
                        "trade_date": pd.Timestamp(trade_day),
                    }
                )
            return pd.DataFrame(rows)

        with (
            patch.object(
                self.repository,
                "_stock_daily_technical_columns",
                return_value=["ts_code", "code", "trade_date"],
            ),
            patch.object(
                self.repository,
                "_load_stock_daily_technical_base",
                side_effect=load_frame,
            ),
            patch.object(
                self.repository,
                "_calculate_stock_daily_technical",
                side_effect=lambda frame: frame,
            ),
        ):
            row_count = self.repository.rebuild_stock_daily_technical(
                target_watermark=target_watermark,
            )

        self.assertEqual(row_count, 2)
        self.assertEqual(
            self._live_keys(),
            [
                ("000001.SZ", date(2017, 6, 1)),
                ("600000.SH", date(2017, 6, 2)),
            ],
        )
        success_markers = list(
            (self.db_path.parent / "rebuild" / "stock_daily_technical").glob("*/_SUCCESS")
        )
        self.assertEqual(len(success_markers), 1)

    def _seed_daily(self, rows: list[tuple[str, date]]) -> None:
        with self.repository.duckdb.connect(read_only=False) as connection:
            connection.executemany(
                "insert into tushare.daily(ts_code, trade_date) values (?, ?)",
                rows,
            )

    def _seed_live_row(self, ts_code: str, trade_day: date) -> None:
        with self.repository.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                insert into tushare.stock_daily_technical(ts_code, code, trade_date)
                values (?, ?, ?)
                """,
                [ts_code, ts_code.lower(), trade_day],
            )

    def _live_keys(self) -> list[tuple[str, date]]:
        with self.repository.duckdb.connect(read_only=True) as connection:
            return connection.execute(
                """
                select ts_code, trade_date
                from tushare.stock_daily_technical
                order by ts_code, trade_date
                """
            ).fetchall()


if __name__ == "__main__":
    unittest.main()
