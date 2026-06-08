from __future__ import annotations

from datetime import date
from threading import Event, Lock, Thread

from app.dtos.data_asset_dto import (
    MartDataAssetRefreshDTO,
    MartDataAssetSummaryDTO,
    StockDataAssetRefreshDTO,
    StockDataAssetSummaryDTO,
    TaskDTO,
)
from app.repositories.data_asset_repository import DataAssetRepository
from app.repositories.task_repository import TaskRepository
from app.services.mart_refresh_service import MartRefreshService
from app.services.source_refresh_service import SourceRefreshService


class SourceUpdateTaskRegistry:
    _lock = Lock()
    _threads: dict[int, Thread] = {}
    _cancel_events: dict[int, Event] = {}

    @classmethod
    def register(cls, task_id: int, thread: Thread, cancel_event: Event) -> None:
        with cls._lock:
            cls._threads[task_id] = thread
            cls._cancel_events[task_id] = cancel_event

    @classmethod
    def unregister(cls, task_id: int) -> None:
        with cls._lock:
            cls._threads.pop(task_id, None)
            cls._cancel_events.pop(task_id, None)

    @classmethod
    def is_active(cls, task_id: int) -> bool:
        with cls._lock:
            thread = cls._threads.get(task_id)
            if thread is None:
                return False
            if thread.ident is None:
                return True
            return thread.is_alive()

    @classmethod
    def cancel(cls, task_id: int) -> bool:
        with cls._lock:
            cancel_event = cls._cancel_events.get(task_id)
            if cancel_event is None:
                return False
            cancel_event.set()
            return True


class DataAssetService:
    def __init__(self) -> None:
        self.repository = DataAssetRepository()
        self.tasks = TaskRepository()

    def get_stock_data_asset_summary(self) -> StockDataAssetSummaryDTO:
        return StockDataAssetSummaryDTO(
            datasets=self.repository.get_stock_dataset_overview()
        )

    def get_mart_data_asset_summary(self) -> MartDataAssetSummaryDTO:
        return MartDataAssetSummaryDTO(
            datasets=self.repository.get_mart_dataset_overview()
        )

    def refresh_mart_data_assets(self) -> MartDataAssetRefreshDTO:
        result = MartRefreshService().run()
        return MartDataAssetRefreshDTO(
            status="success",
            message=f"mart 后处理数据同步完成，共处理 {result.refreshed_count} 个对象。",
            refreshed_count=result.refreshed_count,
        )

    def request_stock_data_asset_refresh(
        self,
        target_date: str | None = None,
        dataset_names: str | None = None,
    ) -> StockDataAssetRefreshDTO:
        parsed_target_date = self._parse_target_date(target_date)
        parsed_dataset_names = self._parse_dataset_names(dataset_names)
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
            (
                "创建 source_update 任务，准备执行每日 source 数据更新。"
                f" target_date={parsed_target_date.isoformat() if parsed_target_date else 'yesterday'}"
                f" dataset_names={','.join(parsed_dataset_names) if parsed_dataset_names else 'all'}"
            ),
        )
        if task.id is None:
            raise RuntimeError("source_update task id is empty")

        task_id = task.id
        cancel_event = Event()

        def run_source_update() -> None:
            try:
                SourceRefreshService(
                    cancel_event=cancel_event,
                    dataset_names=parsed_dataset_names,
                    target_date=parsed_target_date,
                ).run(task_id)
            finally:
                SourceUpdateTaskRegistry.unregister(task_id)

        thread = Thread(
            target=run_source_update,
            daemon=True,
        )
        SourceUpdateTaskRegistry.register(task_id, thread, cancel_event)
        thread.start()

        return StockDataAssetRefreshDTO(
            status="running",
            message="source_update 任务已创建。",
            task_id=task.id,
        )

    def _parse_target_date(self, target_date: str | None) -> date | None:
        if target_date is None or target_date.strip() == "":
            return None
        try:
            return date.fromisoformat(target_date)
        except ValueError as exc:
            raise ValueError("target_date must be YYYY-MM-DD") from exc

    def _parse_dataset_names(self, dataset_names: str | None) -> list[str] | None:
        if dataset_names is None or dataset_names.strip() == "":
            return None
        names = [name.strip() for name in dataset_names.split(",") if name.strip()]
        return names or None

    def get_source_update_task(self, task_id: int | None = None) -> TaskDTO | None:
        self._clear_stale_running_task(task_id)
        if task_id is not None:
            return self.tasks.get_task(task_id)
        return self.tasks.get_latest_task_by_type(SourceRefreshService.TASK_TYPE)

    def stop_source_update_task(self, task_id: int | None = None) -> TaskDTO | None:
        task = (
            self.tasks.get_task(task_id)
            if task_id is not None
            else self.tasks.get_running_task_by_type(SourceRefreshService.TASK_TYPE)
        )
        if task is None:
            return None
        if task.id is None:
            raise RuntimeError("source_update task id is empty")
        if task.status != "running":
            return task

        cancellation_requested = SourceUpdateTaskRegistry.cancel(task.id)
        message = (
            "手动停止 source_update：已发送取消信号，任务将在当前 chunk 结束后退出。"
            if cancellation_requested
            else "手动停止 source_update：未找到活动后台线程，已直接标记为 error。"
        )
        self.tasks.finish_task(task.id, "error", message)
        return self.tasks.get_task(task.id)

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
