from __future__ import annotations

from threading import Lock, Thread

from app.dtos.data_asset_dto import (
    StockDataAssetRefreshDTO,
    StockDataAssetSummaryDTO,
    TaskDTO,
)
from app.repositories.data_asset_repository import DataAssetRepository
from app.repositories.task_repository import TaskRepository
from app.services.source_refresh_service import SourceRefreshService


class SourceUpdateTaskRegistry:
    _lock = Lock()
    _threads: dict[int, Thread] = {}

    @classmethod
    def register(cls, task_id: int, thread: Thread) -> None:
        with cls._lock:
            cls._threads[task_id] = thread

    @classmethod
    def unregister(cls, task_id: int) -> None:
        with cls._lock:
            cls._threads.pop(task_id, None)

    @classmethod
    def is_active(cls, task_id: int) -> bool:
        with cls._lock:
            thread = cls._threads.get(task_id)
            if thread is None:
                return False
            if thread.ident is None:
                return True
            return thread.is_alive()


class DataAssetService:
    def __init__(self) -> None:
        self.repository = DataAssetRepository()
        self.tasks = TaskRepository()

    def get_stock_data_asset_summary(self) -> StockDataAssetSummaryDTO:
        return StockDataAssetSummaryDTO(
            datasets=self.repository.get_stock_dataset_overview()
        )

    def request_stock_data_asset_refresh(self) -> StockDataAssetRefreshDTO:
        self._clear_stale_running_task()
        running_task = self.tasks.get_running_task_by_type(SourceRefreshService.TASK_TYPE)
        if running_task is not None:
            return StockDataAssetRefreshDTO(
                status="running",
                message="已有 source_update 任务正在执行。",
                task_id=running_task.id,
            )

        task = self.tasks.reset_latest_task(
            SourceRefreshService.TASK_TYPE,
            "创建 source_update 任务，准备执行每日 source 数据更新。",
        )
        if task.id is None:
            raise RuntimeError("source_update task id is empty")

        task_id = task.id

        def run_source_update() -> None:
            try:
                SourceRefreshService().run(task_id)
            finally:
                SourceUpdateTaskRegistry.unregister(task_id)

        thread = Thread(
            target=run_source_update,
            daemon=True,
        )
        SourceUpdateTaskRegistry.register(task_id, thread)
        thread.start()

        return StockDataAssetRefreshDTO(
            status="running",
            message="source_update 任务已创建。",
            task_id=task.id,
        )

    def get_source_update_task(self, task_id: int | None = None) -> TaskDTO | None:
        self._clear_stale_running_task(task_id)
        if task_id is not None:
            return self.tasks.get_task(task_id)
        return self.tasks.get_latest_task_by_type(SourceRefreshService.TASK_TYPE)

    def _clear_stale_running_task(self, task_id: int | None = None) -> None:
        task = (
            self.tasks.get_task(task_id)
            if task_id is not None
            else self.tasks.get_running_task_by_type(SourceRefreshService.TASK_TYPE)
        )
        if task is None or task.id is None or task.status != "running":
            return
        if SourceUpdateTaskRegistry.is_active(task.id):
            return
        self.tasks.finish_task(
            task.id,
            "error",
            "source_update 后台执行线程不存在，已清理 running 状态。",
        )
