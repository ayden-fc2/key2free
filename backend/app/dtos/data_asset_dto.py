from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StockDatasetOverviewDTO:
    dataset_name: str
    enabled: bool
    endpoint: Optional[str]
    row_count: Optional[int]
    watermark: Optional[str]
    actual_max_date: Optional[str]
    updated_at: Optional[str]
    status: str


@dataclass(frozen=True)
class StockDataAssetSummaryDTO:
    datasets: list[StockDatasetOverviewDTO]


@dataclass(frozen=True)
class StockDataAssetRefreshDTO:
    status: str
    message: str
