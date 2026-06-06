from __future__ import annotations

from threading import Thread

from app.dtos.data_asset_dto import (
    StockDataAssetRefreshDTO,
    StockDataAssetSummaryDTO,
    TaskDTO,
)
from app.repositories.data_asset_repository import DataAssetRepository
from app.repositories.task_repository import TaskRepository
from app.services.source_refresh_service import SourceRefreshService


class DataAssetService:
    def __init__(self) -> None:
        self.repository = DataAssetRepository()
        self.tasks = TaskRepository()

    def get_stock_data_asset_summary(self) -> StockDataAssetSummaryDTO:
        return StockDataAssetSummaryDTO(
            datasets=self.repository.get_stock_dataset_overview()
        )

    def request_stock_data_asset_refresh(self) -> StockDataAssetRefreshDTO:
        running_task = self.tasks.get_running_task_by_type(SourceRefreshService.TASK_TYPE)
        if running_task is not None:
            return StockDataAssetRefreshDTO(
                status="running",
                message="已有 source_update 任务正在执行。",
                task_id=running_task.id,
            )

        task = self.tasks.create_task(
            SourceRefreshService.TASK_TYPE,
            "创建 source_update 任务，准备执行每日 source 数据更新。",
        )
        if task.id is None:
            raise RuntimeError("source_update task id is empty")

        thread = Thread(
            target=SourceRefreshService().run,
            args=(task.id,),
            daemon=True,
        )
        thread.start()

        return StockDataAssetRefreshDTO(
            status="running",
            message="source_update 任务已创建。",
            task_id=task.id,
        )

    def get_source_update_task(self, task_id: int | None = None) -> TaskDTO | None:
        if task_id is not None:
            return self.tasks.get_task(task_id)
        return self.tasks.get_latest_task_by_type(SourceRefreshService.TASK_TYPE)
