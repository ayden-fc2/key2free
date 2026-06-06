from __future__ import annotations

from app.dtos.data_asset_dto import (
    StockDataAssetRefreshDTO,
    StockDataAssetSummaryDTO,
)
from app.repositories.data_asset_repository import DataAssetRepository


class DataAssetService:
    def __init__(self) -> None:
        self.repository = DataAssetRepository()

    def get_stock_data_asset_summary(self) -> StockDataAssetSummaryDTO:
        return StockDataAssetSummaryDTO(
            datasets=self.repository.get_stock_dataset_overview()
        )

    def request_stock_data_asset_refresh(self) -> StockDataAssetRefreshDTO:
        return StockDataAssetRefreshDTO(
            status="todo",
            message="TODO: 后续将创建任务并调用 BaoStock 同步、校验并更新水位。",
        )
