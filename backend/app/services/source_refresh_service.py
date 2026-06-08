from __future__ import annotations

import os
import time
from datetime import date, timedelta
from threading import Event
from typing import Any

from app.repositories.data_asset_repository import DataAssetRepository
from app.repositories.task_repository import TaskRepository
from app.services.baostock_client import (
    BaoStockClient,
    BaoStockError,
    BaoStockTimeoutError,
)
from app.services.source_adapters import (
    ADAPTER_REGISTRY,
    AdapterNotImplementedError,
    AdapterResult,
    AdapterRuntime,
)


class AdapterRunError(RuntimeError):
    def __init__(
        self,
        *,
        dataset_name: str,
        message: str,
        partial_results: list[AdapterResult],
        request_count: int,
    ) -> None:
        super().__init__(message)
        self.dataset_name = dataset_name
        self.partial_results = partial_results
        self.request_count = request_count


class ChunkFetchError(RuntimeError):
    pass


class ChunkRetryableBaoStockError(ChunkFetchError):
    def __init__(self, message: str, *, worker_thread: Any | None = None) -> None:
        super().__init__(message)
        self.worker_thread = worker_thread


class AdapterBudgetSkipped(RuntimeError):
    def __init__(self, *, dataset_name: str, planned_chunks: int, remaining_requests: int) -> None:
        super().__init__(
            f"{dataset_name} planned chunks {planned_chunks} exceeds remaining request budget {remaining_requests}"
        )
        self.dataset_name = dataset_name
        self.planned_chunks = planned_chunks
        self.remaining_requests = remaining_requests


class SourceRefreshRetryExhausted(RuntimeError):
    pass


class SourceRefreshCancelled(RuntimeError):
    pass


class SourceRefreshService:
    TASK_TYPE = "source_update"
    DEFAULT_MAX_REQUESTS_PER_RUN = 2000000
    DEFAULT_CHUNK_MAX_ATTEMPTS = 3
    DEFAULT_CHUNK_RETRY_DELAY_SECONDS = 600

    def __init__(
        self,
        cancel_event: Event | None = None,
        dataset_names: list[str] | None = None,
        target_date: date | None = None,
    ) -> None:
        self.data_assets = DataAssetRepository()
        self.tasks = TaskRepository()
        self.cancel_event = cancel_event
        self.dataset_names = set(dataset_names) if dataset_names else None
        self.target_date = target_date
        self._run_retry_count = 0
        self._run_login_count = 0

    def run(self, task_id: int) -> None:
        run_id: int | None = None
        request_count = 0
        retry_count = 0
        login_count = 0
        chunk_success = 0
        chunk_failed = 0
        chunk_skipped = 0
        stop_reason: str | None = None
        blacklisted = False
        today = date.today()
        target_date = self.target_date or (today - timedelta(days=1))
        max_requests_per_run = self._max_requests_per_run()
        self._run_retry_count = 0
        self._run_login_count = 0
        try:
            run_id = self.data_assets.create_run_log()
            self.tasks.append_log(task_id, f"创建 run: {run_id}")
            self.tasks.append_log(
                task_id,
                (
                    f"本轮 BaoStock 请求预算: {max_requests_per_run}; "
                    f"目标基准日期: {target_date}"
                ),
            )
            if self.dataset_names is not None:
                self.tasks.append_log(
                    task_id,
                    f"本轮指定 source 表: {', '.join(sorted(self.dataset_names))}",
                )

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
                self._run_login_count += 1
                trade_item = self._get_catalog_item(catalog, "trade_calendar")
                if trade_item is None:
                    raise RuntimeError("enabled source catalog missing trade_calendar")
                trade_results = self._run_adapter(
                    client=client,
                    run_id=run_id,
                    item=trade_item,
                    runtime=AdapterRuntime(
                        today=today,
                        run_id=run_id,
                        repository=self.data_assets,
                    ),
                    max_requests=None,
                    task_id=task_id,
                )
                request_count += sum(result.request_count for result in trade_results)
                trade_window = self._format_scope(trade_results[-1].scope)
                chunk_success += len(trade_results)

                latest_trading_day = self.data_assets.get_latest_trading_day(target_date)
                if latest_trading_day is None:
                    latest_trading_day = target_date
                    self.tasks.append_log(
                        task_id,
                        "未能从 source.trade_calendar 找到最近交易日，临时使用目标基准日期。",
                    )
                self.tasks.append_log(task_id, f"目标交易日: {latest_trading_day}")

                for bootstrap_dataset in ("security_master", "all_stock_snapshot"):
                    if not self._should_run_dataset(bootstrap_dataset):
                        self.tasks.append_log(task_id, f"跳过 {bootstrap_dataset}: 未选择。")
                        continue
                    item = self._get_catalog_item(catalog, bootstrap_dataset)
                    if item is None:
                        continue
                    try:
                        results = self._run_adapter(
                            client=client,
                            run_id=run_id,
                            item=item,
                            runtime=AdapterRuntime(
                                today=today,
                                latest_trading_day=latest_trading_day,
                                run_id=run_id,
                                repository=self.data_assets,
                            ),
                            max_requests=max_requests_per_run - request_count,
                            task_id=task_id,
                        )
                        request_count += sum(result.request_count for result in results)
                        chunk_success += len(results)
                        self.tasks.append_log(
                            task_id,
                            (
                                f"{bootstrap_dataset} 同步成功: "
                                f"chunks={len(results)}, "
                                f"rows={sum(len(result.rows) for result in results)}"
                            ),
                        )
                    except AdapterBudgetSkipped as exc:
                        chunk_skipped += 1
                        stop_reason = "request_budget_exhausted"
                        self.tasks.append_log(task_id, f"跳过 {bootstrap_dataset}: {exc}")
                        break
                    except SourceRefreshCancelled:
                        raise
                    except AdapterRunError as exc:
                        request_count += exc.request_count
                        chunk_success += len(exc.partial_results)
                        chunk_failed += 1
                        self.tasks.append_log(task_id, f"{bootstrap_dataset} 同步失败: {exc}")
                    except Exception as exc:
                        chunk_failed += 1
                        self.tasks.append_log(task_id, f"{bootstrap_dataset} 同步失败: {exc}")

                catalog = self.data_assets.get_enabled_source_catalog()
                self.tasks.append_log(
                    task_id,
                    "基础表同步后已重新加载 enabled source catalog 与资产范围。",
                )

                for item in catalog:
                    dataset_name = item["dataset_name"]
                    if dataset_name in {"trade_calendar", "security_master", "all_stock_snapshot"}:
                        continue
                    if not self._should_run_dataset(dataset_name):
                        self.tasks.append_log(task_id, f"跳过 {dataset_name}: 未选择。")
                        continue
                    if stop_reason == "request_budget_exhausted":
                        chunk_skipped += 1
                        self.tasks.append_log(
                            task_id,
                            f"跳过 {dataset_name}: 本轮请求预算已用尽。",
                        )
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

                        results = self._run_adapter(
                            client=client,
                            run_id=run_id,
                            item=item,
                            runtime=AdapterRuntime(
                                today=today,
                                latest_trading_day=latest_trading_day,
                                run_id=run_id,
                                repository=self.data_assets,
                            ),
                            max_requests=max_requests_per_run - request_count,
                            task_id=task_id,
                        )
                        if not results:
                            chunk_skipped += 1
                            self.tasks.append_log(
                                task_id,
                                f"{dataset_name} 无需同步: watermark 已覆盖目标交易日。",
                            )
                            continue
                        request_count += sum(result.request_count for result in results)
                        chunk_success += len(results)
                        self.tasks.append_log(
                            task_id,
                            (
                                f"{dataset_name} 同步成功: "
                                f"chunks={len(results)}, "
                                f"rows={sum(len(result.rows) for result in results)}"
                            ),
                        )
                    except AdapterBudgetSkipped as exc:
                        chunk_skipped += 1
                        stop_reason = "request_budget_exhausted"
                        self.tasks.append_log(task_id, f"跳过 {dataset_name}: {exc}")
                    except SourceRefreshCancelled:
                        raise
                    except AdapterRunError as exc:
                        request_count += exc.request_count
                        chunk_success += len(exc.partial_results)
                        chunk_failed += 1
                        self.tasks.append_log(
                            task_id,
                            f"{dataset_name} 同步失败: {exc}",
                        )
                    except Exception as exc:
                        chunk_failed += 1
                        self.tasks.append_log(task_id, f"{dataset_name} 同步失败: {exc}")

            retry_count = self._run_retry_count
            login_count = self._run_login_count
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
            exit_reason = stop_reason or ("completed_with_skips" if chunk_skipped else "completed")
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
                    f"trade_window={trade_window}, exit_reason={exit_reason}"
                ),
            )
        except BaoStockError as exc:
            self._finish_error(
                task_id,
                run_id,
                today,
                request_count,
                self._run_retry_count,
                login_count,
                chunk_success,
                chunk_failed,
                blacklisted,
                exc,
            )
        except SourceRefreshRetryExhausted as exc:
            self._finish_error(
                task_id,
                run_id,
                today,
                request_count,
                self._run_retry_count,
                login_count,
                chunk_success,
                chunk_failed,
                blacklisted,
                exc,
            )
        except SourceRefreshCancelled as exc:
            self._finish_error(
                task_id,
                run_id,
                today,
                request_count,
                self._run_retry_count,
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
                self._run_retry_count,
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
        max_requests: int | None = None,
        task_id: int | None = None,
    ) -> list[AdapterResult]:
        dataset_name = item["dataset_name"]
        adapter = ADAPTER_REGISTRY.get(dataset_name)
        if adapter is None:
            raise RuntimeError(f"{dataset_name} adapter is not registered")
        if not adapter.spec.implemented:
            raise AdapterNotImplementedError(f"{dataset_name} adapter is not implemented")

        plan_started_at = time.perf_counter()
        self._append_stage_log(
            task_id,
            dataset_name,
            "plan",
            "开始计算分片",
        )
        chunks = adapter.plan(item=item, runtime=runtime)
        self._append_stage_log(
            task_id,
            dataset_name,
            "plan",
            f"完成，chunks={len(chunks)}, elapsed={self._elapsed(plan_started_at)}",
        )
        plan_validations = self._validate_chunk_plan(
            item=item,
            runtime=runtime,
            chunks=chunks,
        )
        for validation in plan_validations:
            self.data_assets.write_validation_result(
                run_id=run_id,
                dataset_name=dataset_name,
                scope={"dataset_name": dataset_name, "phase": "plan"},
                rule_name=validation["rule_name"],
                severity=validation["severity"],
                passed=validation["passed"],
                sample_count=validation["sample_count"],
                detail=validation["detail"],
            )
        failed_plan_errors = [
            validation
            for validation in plan_validations
            if not validation["passed"] and validation["severity"] == "error"
        ]
        if failed_plan_errors:
            raise AdapterRunError(
                dataset_name=dataset_name,
                message=f"{dataset_name} chunk plan validation failed",
                partial_results=[],
                request_count=0,
            )

        completed_chunk_keys = self.data_assets.get_completed_chunk_keys(
            dataset_name,
            chunks,
        )
        planned_chunk_count = len(chunks)
        if completed_chunk_keys:
            chunks = [
                chunk
                for chunk in chunks
                if chunk.chunk_key not in completed_chunk_keys
            ]
        self._append_stage_log(
            task_id,
            dataset_name,
            "resume",
            (
                f"断点续跑: planned={planned_chunk_count}, "
                f"completed={len(completed_chunk_keys)}, remaining={len(chunks)}"
            ),
        )
        if max_requests is not None and len(chunks) > max_requests:
            raise AdapterBudgetSkipped(
                dataset_name=dataset_name,
                planned_chunks=len(chunks),
                remaining_requests=max_requests,
            )

        if planned_chunk_count > 0 and not chunks:
            watermark_value = self.data_assets.get_dataset_actual_max_date(dataset_name)
            if watermark_value is not None:
                self._validate_watermark_coverage(
                    run_id=run_id,
                    item=item,
                    watermark_value=watermark_value,
                )
                self.data_assets.update_watermark(
                    dataset_name=dataset_name,
                    asset_scope=item["asset_scope"],
                    watermark_value=watermark_value,
                )
                self._append_stage_log(
                    task_id,
                    dataset_name,
                    "watermark",
                    f"全部分片已完成，水位按现有数据推进到 {watermark_value}",
                )
                return [
                    AdapterResult(
                        dataset_name=dataset_name,
                        chunk_key="resume_completed",
                        scope={"mode": "resume_completed"},
                        rows=[],
                        watermark=watermark_value,
                        request_count=0,
                    )
                ]

        results = []
        request_count = 0
        total_chunks = len(chunks)
        for chunk_index, chunk in enumerate(chunks, start=1):
            self._raise_if_cancelled()
            chunk_started_at = time.perf_counter()
            if self._should_log_chunk(chunk_index, total_chunks):
                self._append_stage_log(
                    task_id,
                    dataset_name,
                    "chunk",
                    (
                        f"开始 {chunk_index}/{total_chunks}, "
                        f"scope={self._format_scope(chunk.scope)}"
                    ),
                )
            try:
                result = self._run_chunk_with_retries(
                    client=client,
                    run_id=run_id,
                    item=item,
                    runtime=runtime,
                    chunk=chunk,
                    adapter=adapter,
                    task_id=task_id,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                )
            except SourceRefreshCancelled:
                raise
            except SourceRefreshRetryExhausted:
                raise
            except ChunkFetchError as exc:
                self._append_stage_log(
                    task_id,
                    dataset_name,
                    "fallback",
                    (
                        f"chunk {chunk_index}/{total_chunks} 请求失败，准备拆分 fallback: "
                        f"{exc}"
                    ),
                )
                fallback_chunks = self._get_fallback_chunks(
                    adapter=adapter,
                    item=item,
                    runtime=runtime,
                    failed_chunk=chunk,
                )
                if not fallback_chunks:
                    raise AdapterRunError(
                        dataset_name=dataset_name,
                        message=str(exc),
                        partial_results=results,
                        request_count=request_count + 1,
                    ) from exc
                request_count += 1
                fallback_results = []
                for fallback_index, fallback_chunk in enumerate(fallback_chunks, start=1):
                    fallback_started_at = time.perf_counter()
                    self._append_stage_log(
                        task_id,
                        dataset_name,
                        "fallback",
                        (
                            f"开始 {fallback_index}/{len(fallback_chunks)}, "
                            f"scope={self._format_scope(fallback_chunk.scope)}"
                        ),
                    )
                    try:
                        fallback_result = self._run_chunk_with_retries(
                            client=client,
                            run_id=run_id,
                            item=item,
                            runtime=runtime,
                            chunk=fallback_chunk,
                            adapter=adapter,
                            task_id=task_id,
                            chunk_index=fallback_index,
                            total_chunks=len(fallback_chunks),
                        )
                    except SourceRefreshCancelled:
                        raise
                    except SourceRefreshRetryExhausted:
                        raise
                    except Exception as fallback_exc:
                        raise AdapterRunError(
                            dataset_name=dataset_name,
                            message=str(fallback_exc),
                            partial_results=results,
                            request_count=request_count + 1,
                        ) from fallback_exc
                    request_count += fallback_result.request_count
                    fallback_results.append(fallback_result)
                    results.append(fallback_result)
                    self._append_stage_log(
                        task_id,
                        dataset_name,
                        "fallback",
                        (
                            f"完成 {fallback_index}/{len(fallback_chunks)}, "
                            f"rows={len(fallback_result.rows)}, "
                            f"elapsed={self._elapsed(fallback_started_at)}"
                        ),
                    )
                self.data_assets.upsert_chunk_state(
                    dataset_name=chunk.dataset_name,
                    chunk_key=chunk.chunk_key,
                    scope=chunk.scope,
                    status="split_success",
                    run_id=run_id,
                    row_count=sum(len(result.rows) for result in fallback_results),
                )
                continue
            except Exception as exc:
                raise AdapterRunError(
                    dataset_name=dataset_name,
                    message=str(exc),
                    partial_results=results,
                    request_count=request_count + 1,
                ) from exc
            request_count += result.request_count
            results.append(result)
            if self._should_log_chunk(chunk_index, total_chunks):
                self._append_stage_log(
                    task_id,
                    dataset_name,
                    "chunk",
                    (
                        f"完成 {chunk_index}/{total_chunks}, rows={len(result.rows)}, "
                        f"elapsed={self._elapsed(chunk_started_at)}"
                    ),
                )

        if results:
            watermark_value = self._resolve_dataset_watermark(
                item=item,
                runtime=runtime,
                results=results,
            )
            self._validate_watermark_coverage(
                run_id=run_id,
                item=item,
                watermark_value=watermark_value,
            )
            self.data_assets.update_watermark(
                dataset_name=dataset_name,
                asset_scope=item["asset_scope"],
                watermark_value=watermark_value,
            )
            self._append_stage_log(
                task_id,
                dataset_name,
                "watermark",
                f"推进到 {watermark_value}",
            )
        return results

    def _resolve_dataset_watermark(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        results: list[AdapterResult],
    ) -> str:
        current_watermark = self._parse_date_text(item.get("current_watermark"))
        result_watermarks = [
            parsed
            for result in results
            if (parsed := self._parse_date_text(result.watermark)) is not None
        ]
        if not result_watermarks:
            if current_watermark is None:
                raise ValueError(f"{item['dataset_name']} has no watermark candidate")
            return current_watermark.isoformat()
        candidate = max(result_watermarks)
        if runtime.latest_trading_day is not None:
            candidate = min(candidate, runtime.latest_trading_day)
        if current_watermark is not None:
            candidate = max(candidate, current_watermark)
        return candidate.isoformat()

    def _validate_chunk_plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunks: list[Any],
    ) -> list[dict[str, Any]]:
        dataset_name = item["dataset_name"]
        if dataset_name not in {
            "bar_1d_raw",
            "bar_5m_raw",
            "adjust_factor",
            "dividend",
            "profit",
            "operation",
            "growth",
            "balance",
            "cash_flow",
            "dupont",
            "performance_express",
            "forecast",
            "deposit_rate",
            "loan_rate",
            "reserve_ratio",
            "money_supply_month",
            "money_supply_year",
            "industry_snapshot",
            "index_member_snapshot",
        }:
            return []
        latest_trading_day = runtime.latest_trading_day
        if latest_trading_day is None:
            return []

        expected_scopes = self._expected_chunk_scopes(
            dataset_name=dataset_name,
            item=item,
            latest_trading_day=latest_trading_day,
        )
        planned_scopes = {
            self._scope_key(chunk.scope): chunk.scope
            for chunk in chunks
            if not chunk.scope.get("repair_missing")
        }
        non_repair_chunk_count = sum(
            1 for chunk in chunks if not chunk.scope.get("repair_missing")
        )
        duplicate_scopes = len(planned_scopes) != non_repair_chunk_count
        missing_scopes = sorted(set(expected_scopes) - set(planned_scopes))
        extra_scopes = sorted(set(planned_scopes) - set(expected_scopes))
        mismatched_scopes = sorted(
            scope_key
            for scope_key, expected_scope in expected_scopes.items()
            if scope_key in planned_scopes and planned_scopes[scope_key] != expected_scope
        )
        passed = (
            not duplicate_scopes
            and not missing_scopes
            and not extra_scopes
            and not mismatched_scopes
        )
        return [
            {
                "rule_name": "chunk_plan_coverage",
                "severity": "error",
                "passed": passed,
                "sample_count": (
                    len(missing_scopes) + len(extra_scopes) + len(mismatched_scopes)
                ),
                "detail": {
                    "asset_scope": item["asset_scope"],
                    "expected_chunk_count": len(expected_scopes),
                    "planned_chunk_count": non_repair_chunk_count,
                    "repair_chunk_count": len(chunks) - non_repair_chunk_count,
                    "duplicate_scopes": duplicate_scopes,
                    "missing_scopes_sample": missing_scopes[:10],
                    "extra_scopes_sample": extra_scopes[:10],
                    "mismatched_scopes_sample": mismatched_scopes[:10],
                },
            }
        ]

    def _expected_chunk_scopes(
        self,
        *,
        dataset_name: str,
        item: dict[str, Any],
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        if dataset_name in {"bar_1d_raw", "bar_5m_raw", "adjust_factor"}:
            return self._expected_date_window_scopes(
                dataset_name=dataset_name,
                item=item,
                latest_trading_day=latest_trading_day,
            )
        if dataset_name == "dividend":
            return self._expected_dividend_scopes(
                item=item,
                latest_trading_day=latest_trading_day,
            )
        if dataset_name in {
            "profit",
            "operation",
            "growth",
            "balance",
            "cash_flow",
            "dupont",
        }:
            return self._expected_quarterly_financial_scopes(
                item=item,
                latest_trading_day=latest_trading_day,
            )
        if dataset_name in {"performance_express", "forecast"}:
            return self._expected_announcement_scopes(
                item=item,
                latest_trading_day=latest_trading_day,
            )
        if dataset_name in {
            "deposit_rate",
            "loan_rate",
            "reserve_ratio",
            "money_supply_month",
            "money_supply_year",
        }:
            return self._expected_macro_small_table_scopes(
                dataset_name=dataset_name,
                latest_trading_day=latest_trading_day,
            )
        if dataset_name == "industry_snapshot":
            return self._expected_snapshot_date_scopes(latest_trading_day=latest_trading_day)
        if dataset_name == "index_member_snapshot":
            return self._expected_index_member_scopes(latest_trading_day=latest_trading_day)
        return {}

    def _expected_date_window_scopes(
        self,
        *,
        dataset_name: str,
        item: dict[str, Any],
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        current_watermark = self._parse_date_text(item.get("current_watermark"))
        if (
            dataset_name in {"bar_1d_raw", "bar_5m_raw"}
            and current_watermark is not None
            and current_watermark >= latest_trading_day
        ):
            return {}
        if dataset_name == "bar_5m_raw":
            window_start = max(self._years_ago(latest_trading_day, 5), date(1990, 12, 19))
            if current_watermark is not None:
                window_start = max(window_start, current_watermark + timedelta(days=1))
        elif dataset_name == "adjust_factor":
            if current_watermark is not None:
                window_start = current_watermark - timedelta(days=365)
            else:
                window_start = date(1990, 12, 19)
        else:
            window_start = date(1990, 12, 19)
            if current_watermark is not None:
                window_start = current_watermark + timedelta(days=1)

        expected = {}
        for asset in item.get("asset_universe") or []:
            code = asset.get("code")
            if not code:
                continue
            start_date = max(
                self._parse_date_text(asset.get("ipo_date")) or window_start,
                window_start,
            )
            out_date = self._parse_date_text(asset.get("out_date"))
            end_date = latest_trading_day if out_date is None else min(out_date, latest_trading_day)
            if dataset_name == "bar_5m_raw":
                windows = self._split_year_windows(start_date, end_date)
            else:
                windows = [(start_date, end_date)] if start_date <= end_date else []
            for chunk_start, chunk_end in windows:
                scope = {
                    "code": str(code),
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                }
                expected[self._scope_key(scope)] = scope
        return expected

    def _validate_watermark_coverage(
        self,
        *,
        run_id: int,
        item: dict[str, Any],
        watermark_value: str,
    ) -> None:
        dataset_name = item["dataset_name"]
        validation_results = self.data_assets.validate_source_watermark_coverage(
            dataset_name=dataset_name,
            watermark_value=watermark_value,
        )
        for validation in validation_results:
            self.data_assets.write_validation_result(
                run_id=run_id,
                dataset_name=dataset_name,
                scope={"dataset_name": dataset_name, "phase": "watermark"},
                rule_name=validation["rule_name"],
                severity=validation["severity"],
                passed=validation["passed"],
                sample_count=validation["sample_count"],
                detail=validation["detail"],
            )
        failed_errors = [
            validation
            for validation in validation_results
            if not validation["passed"] and validation["severity"] == "error"
        ]
        if failed_errors:
            raise AdapterRunError(
                dataset_name=dataset_name,
                message=f"{dataset_name} watermark coverage validation failed: {failed_errors}",
                partial_results=[],
                request_count=0,
            )

    def _expected_dividend_scopes(
        self,
        *,
        item: dict[str, Any],
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        current_watermark = self._parse_date_text(item.get("current_watermark"))
        expected = {}
        for asset in item.get("asset_universe") or []:
            code = asset.get("code")
            if not code:
                continue
            ipo_date = self._parse_date_text(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = self._parse_date_text(asset.get("out_date"))
            start_year = ipo_date.year
            if current_watermark is not None:
                start_year = max(start_year, current_watermark.year)
            end_year = latest_trading_day.year if out_date is None else min(out_date.year, latest_trading_day.year)
            for year in range(start_year, end_year + 1):
                for year_type in ("report", "operate"):
                    scope = {"code": str(code), "year": year, "year_type": year_type}
                    expected[self._scope_key(scope)] = scope
        return expected

    def _expected_quarterly_financial_scopes(
        self,
        *,
        item: dict[str, Any],
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        latest_quarter_end = self._latest_completed_quarter_end(latest_trading_day)
        current_watermark = self._parse_date_text(item.get("current_watermark"))
        if current_watermark is None:
            base_start = date(1990, 12, 31)
        else:
            base_start = min(
                self._quarter_end_for_date(current_watermark),
                self._shift_quarter_end(latest_quarter_end, -7),
            )

        expected = {}
        for asset in item.get("asset_universe") or []:
            code = asset.get("code")
            if not code:
                continue
            ipo_date = self._parse_date_text(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = self._parse_date_text(asset.get("out_date"))
            start_quarter_end = max(self._quarter_end_for_date(ipo_date), base_start)
            end_quarter_end = latest_quarter_end
            if out_date is not None:
                end_quarter_end = min(end_quarter_end, self._quarter_end_for_date(out_date))
            for year, quarter in self._iter_quarters(start_quarter_end, end_quarter_end):
                scope = {"code": str(code), "year": year, "quarter": quarter}
                expected[self._scope_key(scope)] = scope
        return expected

    def _expected_announcement_scopes(
        self,
        *,
        item: dict[str, Any],
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        current_watermark = self._parse_date_text(item.get("current_watermark"))
        if current_watermark is None:
            window_start = date(1990, 12, 19)
        else:
            window_start = self._years_ago(current_watermark, 2)
        window_end = latest_trading_day
        if window_start > window_end:
            return {}

        expected = {}
        for asset in item.get("asset_universe") or []:
            code = asset.get("code")
            if not code:
                continue
            ipo_date = self._parse_date_text(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = self._parse_date_text(asset.get("out_date"))
            start_date = max(ipo_date, window_start)
            end_date = window_end if out_date is None else min(out_date, window_end)
            for chunk_start, chunk_end in self._split_year_windows(start_date, end_date):
                scope = {
                    "code": str(code),
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                }
                expected[self._scope_key(scope)] = scope
        return expected

    def _expected_macro_small_table_scopes(
        self,
        *,
        dataset_name: str,
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        if dataset_name in {"deposit_rate", "loan_rate", "reserve_ratio"}:
            scope = {
                "request_start_date": "1990-01-01",
                "request_end_date": latest_trading_day.isoformat(),
                "start_date": "1990-01-01",
                "end_date": latest_trading_day.isoformat(),
            }
        elif dataset_name == "money_supply_month":
            scope = {
                "request_start_date": "1990-01",
                "request_end_date": f"{latest_trading_day.year}-{latest_trading_day.month:02d}",
                "start_date": "1990-01-01",
                "end_date": self._month_end(
                    date(latest_trading_day.year, latest_trading_day.month, 1)
                ).isoformat(),
            }
        elif dataset_name == "money_supply_year":
            scope = {
                "request_start_date": "1990",
                "request_end_date": str(latest_trading_day.year),
                "start_date": "1990-12-31",
                "end_date": date(latest_trading_day.year, 12, 31).isoformat(),
            }
        else:
            return {}
        return {self._scope_key(scope): scope}

    def _expected_snapshot_date_scopes(
        self,
        *,
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        scope = {"update_date": latest_trading_day.isoformat()}
        return {self._scope_key(scope): scope}

    def _expected_index_member_scopes(
        self,
        *,
        latest_trading_day: date,
    ) -> dict[str, dict[str, Any]]:
        expected = {}
        for index_code in ("sh.000016", "sh.000300", "sh.000905"):
            scope = {
                "index_code": index_code,
                "update_date": latest_trading_day.isoformat(),
            }
            expected[self._scope_key(scope)] = scope
        return expected

    def _scope_key(self, scope: dict[str, Any]) -> str:
        return "|".join(f"{key}={scope[key]}" for key in sorted(scope))

    def _years_ago(self, day: date, years: int) -> date:
        try:
            return day.replace(year=day.year - years)
        except ValueError:
            return day.replace(year=day.year - years, day=28)

    def _split_year_windows(self, start_date: date, end_date: date) -> list[tuple[date, date]]:
        if start_date > end_date:
            return []
        return [
            (
                max(start_date, date(year, 1, 1)),
                min(end_date, date(year, 12, 31)),
            )
            for year in range(start_date.year, end_date.year + 1)
        ]

    def _quarter_key(self, day: date) -> tuple[int, int]:
        return day.year, (day.month - 1) // 3 + 1

    def _quarter_end(self, year: int, quarter: int) -> date:
        month = quarter * 3
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - timedelta(days=1)

    def _quarter_end_for_date(self, day: date) -> date:
        year, quarter = self._quarter_key(day)
        return self._quarter_end(year, quarter)

    def _month_end(self, day: date) -> date:
        if day.month == 12:
            return date(day.year, 12, 31)
        return date(day.year, day.month + 1, 1) - timedelta(days=1)

    def _latest_completed_quarter_end(self, day: date) -> date:
        quarter_end = self._quarter_end_for_date(day)
        if quarter_end <= day:
            return quarter_end
        year, quarter = self._quarter_key(day)
        quarter -= 1
        if quarter == 0:
            year -= 1
            quarter = 4
        return self._quarter_end(year, quarter)

    def _shift_quarter_end(self, day: date, offset: int) -> date:
        year, quarter = self._quarter_key(day)
        index = year * 4 + quarter - 1 + offset
        target_year = index // 4
        target_quarter = index % 4 + 1
        return self._quarter_end(target_year, target_quarter)

    def _iter_quarters(
        self,
        start_quarter_end: date,
        end_quarter_end: date,
    ) -> list[tuple[int, int]]:
        if start_quarter_end > end_quarter_end:
            return []
        year, quarter = self._quarter_key(start_quarter_end)
        end_year, end_quarter = self._quarter_key(end_quarter_end)
        quarters = []
        while (year, quarter) <= (end_year, end_quarter):
            quarters.append((year, quarter))
            quarter += 1
            if quarter == 5:
                year += 1
                quarter = 1
        return quarters

    def _parse_date_text(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        return date.fromisoformat(text[:10])

    def _run_chunk(
        self,
        *,
        client: BaoStockClient,
        run_id: int,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: Any,
        adapter: Any,
    ) -> AdapterResult:
        self._raise_if_cancelled()
        self._mark_running(
            run_id=run_id,
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
        )
        try:
            result = adapter.fetch(
                client=client,
                item=item,
                runtime=runtime,
                chunk=chunk,
            )
        except BaoStockTimeoutError as exc:
            self.data_assets.upsert_chunk_state(
                dataset_name=chunk.dataset_name,
                chunk_key=chunk.chunk_key,
                scope=chunk.scope,
                status="failed",
                run_id=run_id,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            raise ChunkRetryableBaoStockError(
                str(exc),
                worker_thread=exc.worker_thread,
            ) from exc
        except BaoStockError as exc:
            self.data_assets.upsert_chunk_state(
                dataset_name=chunk.dataset_name,
                chunk_key=chunk.chunk_key,
                scope=chunk.scope,
                status="failed",
                run_id=run_id,
                error_code=exc.error_code or type(exc).__name__,
                error_message=str(exc),
            )
            if self._is_retryable_baostock_error(exc):
                raise ChunkRetryableBaoStockError(str(exc)) from exc
            raise ChunkFetchError(str(exc)) from exc
        except Exception as exc:
            self.data_assets.upsert_chunk_state(
                dataset_name=chunk.dataset_name,
                chunk_key=chunk.chunk_key,
                scope=chunk.scope,
                status="failed",
                run_id=run_id,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            raise ChunkFetchError(str(exc)) from exc
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
            chunk_key=result.chunk_key,
            scope=result.scope,
            row_count=count,
            validation_results=validation_results,
        )
        return result

    def _run_chunk_with_retries(
        self,
        *,
        client: BaoStockClient,
        run_id: int,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: Any,
        adapter: Any,
        task_id: int | None,
        chunk_index: int,
        total_chunks: int,
    ) -> AdapterResult:
        max_attempts = self._chunk_max_attempts()
        retry_delay_seconds = self._chunk_retry_delay_seconds()
        for attempt in range(1, max_attempts + 1):
            try:
                return self._run_chunk(
                    client=client,
                    run_id=run_id,
                    item=item,
                    runtime=runtime,
                    chunk=chunk,
                    adapter=adapter,
                )
            except SourceRefreshCancelled:
                raise
            except ChunkRetryableBaoStockError as exc:
                if attempt >= max_attempts:
                    raise SourceRefreshRetryExhausted(
                        f"{chunk.dataset_name} chunk {chunk_index}/{total_chunks} "
                        f"BaoStock 请求异常重试耗尽 ({max_attempts}/{max_attempts}): {exc}"
                    ) from exc
                self._run_retry_count += 1
                self._append_stage_log(
                    task_id,
                    chunk.dataset_name,
                    "retry",
                    (
                        f"chunk {chunk_index}/{total_chunks} BaoStock 请求异常，"
                        f"等待 {retry_delay_seconds}s 后重试 "
                        f"({attempt + 1}/{max_attempts}): {exc}"
                    ),
                )
                self._sleep_with_cancel(retry_delay_seconds)
                if exc.worker_thread is not None and exc.worker_thread.is_alive():
                    raise SourceRefreshRetryExhausted(
                        "BaoStock 超时请求仍未结束，停止重试以避免重复调用。"
                    ) from exc
                self._reconnect_baostock_client(
                    client=client,
                    task_id=task_id,
                    dataset_name=chunk.dataset_name,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                )
        raise RuntimeError("unreachable chunk retry state")

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise SourceRefreshCancelled("source_update 已被用户手动停止。")

    def _sleep_with_cancel(self, seconds: int) -> None:
        deadline = time.monotonic() + seconds
        while True:
            self._raise_if_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(1.0, remaining))

    def _reconnect_baostock_client(
        self,
        *,
        client: BaoStockClient,
        task_id: int | None,
        dataset_name: str,
        chunk_index: int,
        total_chunks: int,
    ) -> None:
        self._append_stage_log(
            task_id,
            dataset_name,
            "retry",
            f"chunk {chunk_index}/{total_chunks} 重建 BaoStock 会话",
        )
        try:
            client.reconnect()
        except BaoStockError as exc:
            raise SourceRefreshRetryExhausted(
                f"BaoStock 会话重建失败: {exc}"
            ) from exc
        self._run_login_count += 1

    def _chunk_max_attempts(self) -> int:
        raw_value = os.getenv("SOURCE_UPDATE_CHUNK_MAX_ATTEMPTS")
        if raw_value is None or raw_value.strip() == "":
            return self.DEFAULT_CHUNK_MAX_ATTEMPTS
        try:
            return max(int(raw_value), 1)
        except ValueError:
            return self.DEFAULT_CHUNK_MAX_ATTEMPTS

    def _chunk_retry_delay_seconds(self) -> int:
        raw_value = os.getenv("SOURCE_UPDATE_CHUNK_RETRY_DELAY_SECONDS")
        if raw_value is None or raw_value.strip() == "":
            return self.DEFAULT_CHUNK_RETRY_DELAY_SECONDS
        try:
            return max(int(raw_value), 0)
        except ValueError:
            return self.DEFAULT_CHUNK_RETRY_DELAY_SECONDS

    def _is_retryable_baostock_error(self, exc: BaoStockError) -> bool:
        error_code = (exc.error_code or "").strip()
        if error_code and error_code != "0":
            return True
        if error_code in {"10002007"}:
            return True

        message = f"{exc.error_msg or ''} {exc}".lower()
        retryable_fragments = (
            "网络接收错误",
            "网络",
            "timeout",
            "timed out",
            "connection",
            "reset",
            "temporarily",
        )
        return any(fragment in message for fragment in retryable_fragments)

    def _get_fallback_chunks(
        self,
        *,
        adapter: Any,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        failed_chunk: Any,
    ) -> list[Any]:
        fallback = getattr(adapter, "fallback_chunks", None)
        if fallback is None:
            return []
        return fallback(item=item, runtime=runtime, failed_chunk=failed_chunk)

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
        chunk_key: str,
        scope: dict[str, Any],
        row_count: int,
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
            failed_details = [
                {
                    "rule_name": validation["rule_name"],
                    "detail": validation["detail"],
                }
                for validation in validation_results
                if not validation["passed"] and validation["severity"] == "error"
            ]
            self.data_assets.upsert_chunk_state(
                dataset_name=dataset_name,
                chunk_key=chunk_key,
                scope=scope,
                status="failed",
                run_id=run_id,
                row_count=row_count,
                error_code="ValidationError",
                error_message=f"source dataset validation failed: {failed_details}",
            )
            raise RuntimeError(f"{dataset_name} validation failed: {failed_details}")

        self.data_assets.upsert_chunk_state(
            dataset_name=dataset_name,
            chunk_key=chunk_key,
            scope=scope,
            status="success",
            run_id=run_id,
            row_count=row_count,
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

    def _should_run_dataset(self, dataset_name: str) -> bool:
        if self.dataset_names is None:
            return True
        return dataset_name in self.dataset_names

    def _append_stage_log(
        self,
        task_id: int | None,
        dataset_name: str,
        stage: str,
        message: str,
    ) -> None:
        if task_id is None:
            return
        self.tasks.append_log(task_id, f"{dataset_name} 阶段={stage}: {message}")

    def _max_requests_per_run(self) -> int:
        raw_value = os.getenv("SOURCE_UPDATE_MAX_REQUESTS")
        if raw_value is None or raw_value.strip() == "":
            return self.DEFAULT_MAX_REQUESTS_PER_RUN
        try:
            value = int(raw_value)
        except ValueError:
            return self.DEFAULT_MAX_REQUESTS_PER_RUN
        return max(value, 1)

    def _should_log_chunk(self, chunk_index: int, total_chunks: int) -> bool:
        return (
            chunk_index == 1
            or chunk_index == total_chunks
            or chunk_index % 1000 == 0
        )

    def _elapsed(self, started_at: float) -> str:
        return f"{time.perf_counter() - started_at:.2f}s"

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
