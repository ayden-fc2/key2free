from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories.data_asset_repository import DataAssetRepository
from app.services.mart_adapters import (
    MART_ADAPTER_REGISTRY,
    MartAdapter,
    MartAdapterError,
    MartAdapterResult,
    MartValidationResult,
)


class MartRefreshError(RuntimeError):
    def __init__(self, dataset_name: str, message: str) -> None:
        super().__init__(message)
        self.dataset_name = dataset_name


@dataclass(frozen=True)
class MartRefreshRunResult:
    refreshed_count: int


class MartRefreshService:
    def __init__(self) -> None:
        self.repository = DataAssetRepository()

    def run(self) -> MartRefreshRunResult:
        adapters = list(MART_ADAPTER_REGISTRY.values())
        refreshed_count = 0
        with self.repository.duckdb.connect(read_only=False) as connection:
            run_id = self.repository.create_mart_run_log(connection)
            try:
                connection.execute("begin transaction")
                for adapter in adapters:
                    self.repository.ensure_mart_catalog_item_with_connection(
                        connection=connection,
                        dataset_name=adapter.dataset_name,
                        table_type=adapter.table_type,
                        expected_columns=adapter.expected_columns,
                        priority=adapter.priority,
                    )
                    result = self._run_adapter(
                        connection=connection,
                        run_id=run_id,
                        adapter=adapter,
                    )
                    refreshed_count += 1
                    self.repository.upsert_chunk_state_with_connection(
                        connection=connection,
                        dataset_name=result.dataset_name,
                        chunk_key="mart_refresh",
                        scope={"schema": "mart", "adapter": type(adapter).__name__},
                        status="success",
                        run_id=run_id,
                        row_count=result.row_count,
                    )
                self.repository.finish_mart_run_log(
                    connection=connection,
                    run_id=run_id,
                    refreshed_count=refreshed_count,
                    failed_count=0,
                )
                connection.execute("commit")
            except Exception as exc:
                connection.execute("rollback")
                failed_dataset = (
                    exc.dataset_name
                    if isinstance(exc, MartRefreshError)
                    else self._resolve_exception_dataset(exc)
                )
                self._record_failed_run(
                    connection=connection,
                    run_id=run_id,
                    dataset_name=failed_dataset,
                    refreshed_count=refreshed_count,
                    exc=exc,
                )
                raise MartRefreshError(failed_dataset, str(exc)) from exc
        return MartRefreshRunResult(refreshed_count=refreshed_count)

    def _run_adapter(
        self,
        *,
        connection: Any,
        run_id: int,
        adapter: MartAdapter,
    ) -> MartAdapterResult:
        try:
            result = adapter.run(connection)
        except MartAdapterError as exc:
            raise MartRefreshError(adapter.dataset_name, str(exc)) from exc
        except Exception as exc:
            raise MartRefreshError(adapter.dataset_name, str(exc)) from exc

        self._write_validations(
            connection=connection,
            run_id=run_id,
            dataset_name=result.dataset_name,
            adapter=adapter,
            validation_results=result.validation_results,
        )
        failed_errors = [
            item
            for item in result.validation_results
            if item.severity == "error" and not item.passed
        ]
        if failed_errors:
            names = ", ".join(item.rule_name for item in failed_errors)
            raise MartRefreshError(result.dataset_name, f"{result.dataset_name} validation failed: {names}")
        if result.watermark_value is not None:
            self.repository.update_watermark_with_connection(
                connection=connection,
                dataset_name=result.dataset_name,
                asset_scope="mart",
                watermark_value=result.watermark_value,
            )
        return result

    def _write_validations(
        self,
        *,
        connection: Any,
        run_id: int,
        dataset_name: str,
        adapter: MartAdapter,
        validation_results: list[MartValidationResult],
    ) -> None:
        for validation in validation_results:
            self.repository.write_validation_result_with_connection(
                connection=connection,
                run_id=run_id,
                dataset_name=dataset_name,
                scope={"schema": "mart", "adapter": type(adapter).__name__},
                rule_name=validation.rule_name,
                severity=validation.severity,
                passed=validation.passed,
                sample_count=validation.sample_count,
                detail=validation.detail,
            )

    def _record_failed_run(
        self,
        *,
        connection: Any,
        run_id: int,
        dataset_name: str,
        refreshed_count: int,
        exc: Exception,
    ) -> None:
        self.repository.write_validation_result_with_connection(
            connection=connection,
            run_id=run_id,
            dataset_name=dataset_name,
            scope={"schema": "mart"},
            rule_name="refresh",
            severity="error",
            passed=False,
            sample_count=0,
            detail={"error": str(exc)},
        )
        self.repository.upsert_chunk_state_with_connection(
            connection=connection,
            dataset_name=dataset_name,
            chunk_key="mart_refresh",
            scope={"schema": "mart"},
            status="failed",
            run_id=run_id,
            row_count=0,
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
        self.repository.finish_mart_run_log(
            connection=connection,
            run_id=run_id,
            refreshed_count=refreshed_count,
            failed_count=1,
            error_summary=str(exc),
        )

    def _resolve_exception_dataset(self, exc: Exception) -> str:
        if isinstance(exc, MartRefreshError):
            return exc.dataset_name
        return "mart_refresh"
