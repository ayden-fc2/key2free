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
    latest_validation_at: Optional[str]
    validation_failed_count: int
    latest_chunk_status: Optional[str]
    chunk_failed_count: int
    open_repair_count: int


@dataclass(frozen=True)
class StockDataAssetSummaryDTO:
    datasets: list[StockDatasetOverviewDTO]


@dataclass(frozen=True)
class MartDatasetOverviewDTO:
    dataset_name: str
    table_name: str
    table_type: str
    enabled: bool
    row_count: Optional[int]
    watermark: Optional[str]
    actual_max_date: Optional[str]
    updated_at: Optional[str]
    status: str
    latest_validation_at: Optional[str]
    validation_failed_count: int


@dataclass(frozen=True)
class MartDataAssetSummaryDTO:
    datasets: list[MartDatasetOverviewDTO]


@dataclass(frozen=True)
class MartDataAssetRefreshDTO:
    status: str
    message: str
    refreshed_count: int


@dataclass(frozen=True)
class StockDataAssetRefreshDTO:
    status: str
    message: str
    task_id: int | None = None


@dataclass(frozen=True)
class TaskDTO:
    id: int | None
    type: str
    logs: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None
