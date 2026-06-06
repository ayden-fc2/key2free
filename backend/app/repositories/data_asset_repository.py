from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.dtos.data_asset_dto import StockDatasetOverviewDTO
from app.repositories.duckdb_repository import DuckDBRepository


class DataAssetRepository:
    DATASET_TABLES: dict[str, dict[str, str]] = {
        "security_master": {"table_name": "source.security_master", "date_column": "updated_at"},
        "trade_calendar": {"table_name": "source.trade_calendar", "date_column": "calendar_date"},
        "all_stock_snapshot": {"table_name": "source.all_stock_snapshot", "date_column": "trade_date"},
        "bar_1d_raw": {"table_name": "source.bar_1d_raw", "date_column": "trade_date"},
        "bar_5m_raw": {"table_name": "source.bar_5m_raw", "date_column": "trade_date"},
        "adjust_factor": {"table_name": "source.adjust_factor", "date_column": "divid_operate_date"},
        "dividend": {"table_name": "source.dividend", "date_column": "divid_operate_date"},
        "profit": {"table_name": "source.profit", "date_column": "stat_date"},
        "operation": {"table_name": "source.operation", "date_column": "stat_date"},
        "growth": {"table_name": "source.growth", "date_column": "stat_date"},
        "balance": {"table_name": "source.balance", "date_column": "stat_date"},
        "cash_flow": {"table_name": "source.cash_flow", "date_column": "stat_date"},
        "dupont": {"table_name": "source.dupont", "date_column": "stat_date"},
        "performance_express": {"table_name": "source.performance_express", "date_column": "pub_date"},
        "forecast": {"table_name": "source.forecast", "date_column": "pub_date"},
        "deposit_rate": {"table_name": "source.deposit_rate", "date_column": "pub_date"},
        "loan_rate": {"table_name": "source.loan_rate", "date_column": "pub_date"},
        "reserve_ratio": {"table_name": "source.reserve_ratio", "date_column": "effective_date"},
        "money_supply_month": {"table_name": "source.money_supply_month", "date_column": "stat_date"},
        "money_supply_year": {"table_name": "source.money_supply_year", "date_column": "stat_date"},
        "industry_snapshot": {"table_name": "source.industry_snapshot", "date_column": "update_date"},
        "index_member_snapshot": {"table_name": "source.index_member_snapshot", "date_column": "update_date"},
    }

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def get_stock_dataset_overview(self) -> list[StockDatasetOverviewDTO]:
        with self.duckdb.connect(read_only=True) as connection:
            catalog_rows = connection.execute(
                """
                select dataset_name, endpoint, enabled, priority
                from meta.dataset_catalog
                order by case when enabled = 1 then 0 else 1 end, priority, dataset_name
                """
            ).fetchall()
            watermark_rows = connection.execute(
                """
                select dataset_name, watermark_value, updated_at
                from meta.dataset_watermark
                """
            ).fetchall()
            watermarks = {
                dataset_name: {
                    "watermark": watermark_value,
                    "updated_at": None if updated_at is None else str(updated_at),
                }
                for dataset_name, watermark_value, updated_at in watermark_rows
            }

            datasets: list[StockDatasetOverviewDTO] = []
            for dataset_name, endpoint, enabled, _priority in catalog_rows:
                physical = self.DATASET_TABLES.get(dataset_name)
                row_count = None
                actual_max_date = None
                if physical is not None:
                    row_count, actual_max_date = connection.execute(
                        f"""
                        select count(*) as row_count,
                               max({physical["date_column"]}) as actual_max_date
                        from {physical["table_name"]}
                        """
                    ).fetchone()

                watermark_item = watermarks.get(dataset_name, {})
                watermark = watermark_item.get("watermark")
                actual_max_date_str = None if actual_max_date is None else str(actual_max_date)
                status = self._resolve_status(watermark, actual_max_date_str)
                datasets.append(
                    StockDatasetOverviewDTO(
                        dataset_name=dataset_name,
                        enabled=bool(enabled),
                        endpoint=endpoint,
                        row_count=row_count,
                        watermark=watermark,
                        actual_max_date=actual_max_date_str,
                        updated_at=watermark_item.get("updated_at"),
                        status=status,
                    )
                )
        return datasets

    def _resolve_status(
        self,
        watermark: Any,
        actual_max_date: Any,
    ) -> str:
        if watermark is None:
            return "unknown"
        if actual_max_date is None:
            return "empty"
        return (
            "ok"
            if self._normalize_date_value(watermark)
            == self._normalize_date_value(actual_max_date)
            else "warning"
        )

    def _normalize_date_value(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()

        text = str(value).strip()
        match = text[:10]
        if len(match) == 10 and match[4] == "-" and match[7] == "-":
            return match
        return text
