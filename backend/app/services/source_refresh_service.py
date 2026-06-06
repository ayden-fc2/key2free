from __future__ import annotations

from datetime import date
from typing import Any

from app.repositories.data_asset_repository import DataAssetRepository
from app.repositories.task_repository import TaskRepository
from app.services.baostock_client import BaoStockClient, BaoStockError
from app.services.source_adapters import (
    ADAPTER_REGISTRY,
    AdapterNotImplementedError,
    AdapterResult,
    AdapterRuntime,
)


class SourceRefreshService:
    TASK_TYPE = "source_update"

    def __init__(self) -> None:
        self.data_assets = DataAssetRepository()
        self.tasks = TaskRepository()

    def run(self, task_id: int) -> None:
        run_id: int | None = None
        request_count = 0
        retry_count = 0
        login_count = 0
        chunk_success = 0
        chunk_failed = 0
        chunk_skipped = 0
        blacklisted = False
        today = date.today()
        try:
            run_id = self.data_assets.create_run_log()
            self.tasks.append_log(task_id, f"创建 run: {run_id}")

            quota_state = self.data_assets.get_quota_state(today)
            if quota_state and quota_state["blacklisted"]:
                blacklisted = True
                message = "BaoStock 今日已标记 blacklisted，停止 source_update。"
                self.tasks.append_log(task_id, message)
                self.data_assets.finish_run_log(
                    run_id=run_id,
                    status="aborted",
                    exit_reason="baostock_blacklisted",
                    blacklisted=1,
                    error_summary=message,
                )
                self.tasks.finish_task(task_id, "error", message)
                return

            cleared = self.data_assets.clear_expired_leases()
            self.tasks.append_log(task_id, f"清理过期 running 分片: {cleared}")

            catalog = self.data_assets.get_enabled_source_catalog()
            self.tasks.append_log(task_id, f"读取 enabled source catalog: {len(catalog)} 个")

            with BaoStockClient() as client:
                login_count += 1
                trade_item = self._get_catalog_item(catalog, "trade_calendar")
                if trade_item is None:
                    raise RuntimeError("enabled source catalog missing trade_calendar")
                trade_result = self._run_adapter(
                    client=client,
                    run_id=run_id,
                    item=trade_item,
                    runtime=AdapterRuntime(today=today),
                )
                request_count += trade_result.request_count
                trade_window = self._format_scope(trade_result.scope)
                chunk_success += 1

                latest_trading_day = self.data_assets.get_latest_trading_day(today)
                if latest_trading_day is None:
                    latest_trading_day = today
                    self.tasks.append_log(
                        task_id,
                        "未能从 source.trade_calendar 找到最近交易日，临时使用今日作为目标日期。",
                    )
                self.tasks.append_log(task_id, f"目标交易日: {latest_trading_day}")

                for item in catalog:
                    dataset_name = item["dataset_name"]
                    if dataset_name == "trade_calendar":
                        continue
                    try:
                        adapter = ADAPTER_REGISTRY.get(dataset_name)
                        if adapter is None:
                            raise RuntimeError(f"{dataset_name} adapter is not registered")
                        if not adapter.spec.implemented:
                            chunk_skipped += 1
                            self.tasks.append_log(
                                task_id,
                                (
                                    f"跳过 {dataset_name}: endpoint={adapter.spec.endpoint}, "
                                    f"help_docs={list(adapter.spec.help_docs)}, "
                                    f"{adapter.spec.note}"
                                ),
                            )
                            continue

                        result = self._run_adapter(
                            client=client,
                            run_id=run_id,
                            item=item,
                            runtime=AdapterRuntime(
                                today=today,
                                latest_trading_day=latest_trading_day,
                            ),
                        )
                        request_count += result.request_count
                        chunk_success += 1
                        self.tasks.append_log(
                            task_id,
                            (
                                f"{dataset_name} 同步成功: "
                                f"scope={self._format_scope(result.scope)}, "
                                f"rows={len(result.rows)}"
                            ),
                        )
                    except Exception as exc:
                        chunk_failed += 1
                        self.tasks.append_log(task_id, f"{dataset_name} 同步失败: {exc}")
                        self.data_assets.upsert_chunk_state(
                            dataset_name=dataset_name,
                            chunk_key="daily_source_refresh",
                            scope={"target_date": str(latest_trading_day)},
                            status="failed",
                            run_id=run_id,
                            error_code=type(exc).__name__,
                            error_message=str(exc),
                        )

            if run_id is not None:
                self.data_assets.upsert_quota_state(
                    quota_date=today,
                    request_count_delta=request_count,
                    retry_count_delta=retry_count,
                    login_count_delta=login_count,
                    blacklisted=blacklisted,
                    run_id=run_id,
                )

            final_status = "success" if chunk_failed == 0 else "partial_success"
            exit_reason = "completed_with_skips" if chunk_skipped else "completed"
            self.data_assets.finish_run_log(
                run_id=run_id,
                status=final_status,
                exit_reason=exit_reason,
                request_count=request_count,
                retry_count=retry_count,
                login_count=login_count,
                chunk_success=chunk_success,
                chunk_failed=chunk_failed,
                blacklisted=1 if blacklisted else 0,
            )
            self.tasks.finish_task(
                task_id,
                "success" if chunk_failed == 0 else "error",
                (
                    f"source_update 完成。run={run_id}, "
                    f"success_chunks={chunk_success}, failed_chunks={chunk_failed}, "
                    f"skipped_chunks={chunk_skipped}, requests={request_count}, "
                    f"trade_window={trade_window}"
                ),
            )
        except BaoStockError as exc:
            self._finish_error(
                task_id,
                run_id,
                today,
                request_count,
                retry_count,
                login_count,
                chunk_success,
                chunk_failed,
                blacklisted,
                exc,
            )
        except Exception as exc:
            self._finish_error(
                task_id,
                run_id,
                today,
                request_count,
                retry_count,
                login_count,
                chunk_success,
                chunk_failed,
                blacklisted,
                exc,
            )

    def _run_adapter(
        self,
        *,
        client: BaoStockClient,
        run_id: int,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> AdapterResult:
        dataset_name = item["dataset_name"]
        adapter = ADAPTER_REGISTRY.get(dataset_name)
        if adapter is None:
            raise RuntimeError(f"{dataset_name} adapter is not registered")
        if not adapter.spec.implemented:
            raise AdapterNotImplementedError(f"{dataset_name} adapter is not implemented")

        result = adapter.fetch(client=client, item=item, runtime=runtime)
        self._mark_running(
            run_id=run_id,
            dataset_name=result.dataset_name,
            chunk_key=result.chunk_key,
            scope=result.scope,
        )
        count, validation_results = self.data_assets.stage_validate_replace_source_rows(
            dataset_name=result.dataset_name,
            rows=result.rows,
            replace_strategy=item["replace_strategy"],
            scope=result.scope,
            expected_columns=item["expected_columns"],
            logical_key=item["logical_key"],
        )
        self._mark_success(
            run_id=run_id,
            dataset_name=result.dataset_name,
            item=item,
            chunk_key=result.chunk_key,
            scope=result.scope,
            row_count=count,
            watermark=result.watermark,
            validation_results=validation_results,
        )
        return result

    def _mark_running(
        self,
        *,
        run_id: int,
        dataset_name: str,
        chunk_key: str,
        scope: dict[str, Any],
    ) -> None:
        self.data_assets.upsert_chunk_state(
            dataset_name=dataset_name,
            chunk_key=chunk_key,
            scope=scope,
            status="running",
            run_id=run_id,
        )

    def _mark_success(
        self,
        *,
        run_id: int,
        dataset_name: str,
        item: dict[str, Any],
        chunk_key: str,
        scope: dict[str, Any],
        row_count: int,
        watermark: str,
        validation_results: list[dict[str, Any]],
    ) -> None:
        passed = True
        for validation in validation_results:
            if not validation["passed"] and validation["severity"] == "error":
                passed = False
            self.data_assets.write_validation_result(
                run_id=run_id,
                dataset_name=dataset_name,
                scope=scope,
                rule_name=validation["rule_name"],
                severity=validation["severity"],
                passed=validation["passed"],
                sample_count=validation["sample_count"],
                detail=validation["detail"],
            )

        if not passed:
            self.data_assets.upsert_chunk_state(
                dataset_name=dataset_name,
                chunk_key=chunk_key,
                scope=scope,
                status="failed",
                run_id=run_id,
                row_count=row_count,
                error_code="ValidationError",
                error_message="source dataset validation failed",
            )
            raise RuntimeError(f"{dataset_name} validation failed")

        self.data_assets.upsert_chunk_state(
            dataset_name=dataset_name,
            chunk_key=chunk_key,
            scope=scope,
            status="success",
            run_id=run_id,
            row_count=row_count,
        )
        self.data_assets.update_watermark(
            dataset_name=dataset_name,
            asset_scope=item["asset_scope"],
            watermark_value=watermark,
        )

    def _get_catalog_item(
        self,
        catalog: list[dict[str, Any]],
        dataset_name: str,
    ) -> dict[str, Any] | None:
        for item in catalog:
            if item["dataset_name"] == dataset_name:
                return item
        return None

    def _finish_error(
        self,
        task_id: int,
        run_id: int | None,
        quota_date: date,
        request_count: int,
        retry_count: int,
        login_count: int,
        chunk_success: int,
        chunk_failed: int,
        blacklisted: bool,
        exc: Exception,
    ) -> None:
        if run_id is not None:
            self.data_assets.upsert_quota_state(
                quota_date=quota_date,
                request_count_delta=request_count,
                retry_count_delta=retry_count,
                login_count_delta=login_count,
                blacklisted=blacklisted,
                run_id=run_id,
            )
            self.data_assets.finish_run_log(
                run_id=run_id,
                status="error",
                exit_reason=type(exc).__name__,
                request_count=request_count,
                retry_count=retry_count,
                login_count=login_count,
                chunk_success=chunk_success,
                chunk_failed=chunk_failed,
                blacklisted=1 if blacklisted else 0,
                error_summary=str(exc),
            )
        self.tasks.finish_task(task_id, "error", f"source_update 失败: {exc}")

    def _format_scope(self, scope: dict[str, Any]) -> str:
        if "start_date" in scope and "end_date" in scope:
            return f"{scope['start_date']}->{scope['end_date']}"
        return str(scope)
