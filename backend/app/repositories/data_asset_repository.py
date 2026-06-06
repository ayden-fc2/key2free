from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.dtos.data_asset_dto import StockDatasetOverviewDTO
from app.repositories.duckdb_repository import DuckDBRepository


SOURCE_TABLE_COLUMNS: dict[str, list[str]] = {
    "security_master": [
        "code",
        "code_name",
        "ipo_date",
        "out_date",
        "security_type",
        "list_status",
        "first_seen_date",
        "last_seen_date",
        "updated_at",
    ],
    "trade_calendar": [
        "calendar_date",
        "is_trading_day",
        "exchange",
        "updated_at",
    ],
    "all_stock_snapshot": [
        "trade_date",
        "code",
        "code_name",
        "updated_at",
    ],
}


class DataAssetRepository:
    DATASET_TABLES: dict[str, dict[str, str]] = {
        "security_master": {"table_name": "source.security_master", "date_column": "last_seen_date"},
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
            validation_rows = connection.execute(
                """
                with latest_run as (
                    select dataset_name, max(run_id) as run_id
                    from meta.validation_result
                    group by dataset_name
                )
                select v.dataset_name,
                       max(v.created_at) as latest_validation_at,
                       sum(case when v.passed = 0 then 1 else 0 end) as failed_count
                from meta.validation_result v
                join latest_run r
                  on v.dataset_name = r.dataset_name
                 and v.run_id = r.run_id
                group by v.dataset_name
                """
            ).fetchall()
            validations = {
                dataset_name: {
                    "latest_validation_at": (
                        None if latest_validation_at is None else str(latest_validation_at)
                    ),
                    "failed_count": int(failed_count or 0),
                }
                for dataset_name, latest_validation_at, failed_count in validation_rows
            }
            latest_chunk_rows = connection.execute(
                """
                with ranked as (
                    select dataset_name, status,
                           row_number() over (
                               partition by dataset_name
                               order by updated_at desc nulls last
                           ) as rn
                    from meta.chunk_state
                )
                select dataset_name, status
                from ranked
                where rn = 1
                """
            ).fetchall()
            latest_chunks = {
                dataset_name: status for dataset_name, status in latest_chunk_rows
            }
            chunk_failed_rows = connection.execute(
                """
                select dataset_name, count(*) as failed_count
                from meta.chunk_state
                where status = 'failed'
                group by dataset_name
                """
            ).fetchall()
            chunk_failed_counts = {
                dataset_name: int(failed_count or 0)
                for dataset_name, failed_count in chunk_failed_rows
            }
            repair_rows = connection.execute(
                """
                select dataset_name, count(*) as open_count
                from meta.repair_manifest
                where status is null or status not in ('closed', 'success', 'done')
                group by dataset_name
                """
            ).fetchall()
            open_repairs = {
                dataset_name: int(open_count or 0)
                for dataset_name, open_count in repair_rows
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
                validation_item = validations.get(dataset_name, {})
                watermark = watermark_item.get("watermark")
                actual_max_date_str = None if actual_max_date is None else str(actual_max_date)
                validation_failed_count = int(validation_item.get("failed_count") or 0)
                chunk_failed_count = chunk_failed_counts.get(dataset_name, 0)
                open_repair_count = open_repairs.get(dataset_name, 0)
                latest_chunk_status = latest_chunks.get(dataset_name)
                status = self._resolve_status(
                    watermark,
                    actual_max_date_str,
                    validation_failed_count,
                    chunk_failed_count,
                    open_repair_count,
                    latest_chunk_status,
                )
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
                        latest_validation_at=validation_item.get("latest_validation_at"),
                        validation_failed_count=validation_failed_count,
                        latest_chunk_status=latest_chunk_status,
                        chunk_failed_count=chunk_failed_count,
                        open_repair_count=open_repair_count,
                    )
                )
        return datasets

    def get_enabled_source_catalog(self) -> list[dict[str, Any]]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select dataset_name, endpoint, tier, enabled, asset_scope,
                       chunk_strategy, replace_strategy, logical_key_json,
                       expected_columns_json, duckdb_schema_json,
                       validation_rules_json, priority
                from meta.dataset_catalog
                where enabled = 1
                order by priority, dataset_name
                """
            ).fetchall()
        return [
            {
                "dataset_name": dataset_name,
                "endpoint": endpoint,
                "tier": tier,
                "enabled": bool(enabled),
                "asset_scope": asset_scope,
                "chunk_strategy": chunk_strategy,
                "replace_strategy": replace_strategy,
                "logical_key": json.loads(logical_key_json or "[]"),
                "expected_columns": json.loads(expected_columns_json or "[]"),
                "duckdb_schema": json.loads(duckdb_schema_json or "{}"),
                "validation_rules": json.loads(validation_rules_json or "[]"),
                "priority": priority,
            }
            for (
                dataset_name,
                endpoint,
                tier,
                enabled,
                asset_scope,
                chunk_strategy,
                replace_strategy,
                logical_key_json,
                expected_columns_json,
                duckdb_schema_json,
                validation_rules_json,
                priority,
            ) in rows
        ]

    def create_run_log(self) -> int:
        with self.duckdb.connect(read_only=False) as connection:
            run_id = connection.execute(
                """
                insert into meta.run_log(command, tier, started_at, status,
                                         request_count, retry_count, login_count,
                                         chunk_success, chunk_failed, blacklisted)
                values ('daily_source_refresh', 'source', current_timestamp,
                        'running', 0, 0, 0, 0, 0, 0)
                returning run_id
                """
            ).fetchone()[0]
        return run_id

    def finish_run_log(
        self,
        *,
        run_id: int,
        status: str,
        exit_reason: str | None = None,
        request_count: int = 0,
        retry_count: int = 0,
        login_count: int = 0,
        chunk_success: int = 0,
        chunk_failed: int = 0,
        blacklisted: int = 0,
        error_summary: str | None = None,
    ) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                update meta.run_log
                set ended_at = current_timestamp,
                    status = ?,
                    exit_reason = ?,
                    request_count = ?,
                    retry_count = ?,
                    login_count = ?,
                    chunk_success = ?,
                    chunk_failed = ?,
                    blacklisted = ?,
                    error_summary = ?
                where run_id = ?
                """,
                [
                    status,
                    exit_reason,
                    request_count,
                    retry_count,
                    login_count,
                    chunk_success,
                    chunk_failed,
                    blacklisted,
                    error_summary,
                    run_id,
                ],
            )

    def upsert_quota_state(
        self,
        *,
        quota_date: date,
        request_count_delta: int,
        retry_count_delta: int,
        login_count_delta: int,
        blacklisted: bool,
        run_id: int,
    ) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            existing = connection.execute(
                """
                select 1
                from meta.api_quota_daily
                where quota_date = ? and quota_channel = 'direct'
                """,
                [quota_date],
            ).fetchone()
            if existing is not None:
                connection.execute(
                    """
                    update meta.api_quota_daily
                    set request_count = coalesce(request_count, 0) + ?,
                        retry_count = coalesce(retry_count, 0) + ?,
                        login_count = coalesce(login_count, 0) + ?,
                        blacklisted = greatest(coalesce(blacklisted, 0), ?),
                        last_run_id = ?
                    where quota_date = ? and quota_channel = 'direct'
                    """,
                    [
                        request_count_delta,
                        retry_count_delta,
                        login_count_delta,
                        1 if blacklisted else 0,
                        run_id,
                        quota_date,
                    ],
                )
                return

            connection.execute(
                """
                insert into meta.api_quota_daily(
                    quota_date, quota_channel, request_count, retry_count,
                    login_count, blacklisted, soft_stop_at, hard_stop_at,
                    last_run_id
                )
                values (?, 'direct', ?, ?, ?, ?, null, null, ?)
                """,
                [
                    quota_date,
                    request_count_delta,
                    retry_count_delta,
                    login_count_delta,
                    1 if blacklisted else 0,
                    run_id,
                ],
            )

    def get_quota_state(self, quota_date: date) -> dict[str, Any] | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select request_count, retry_count, login_count, blacklisted,
                       soft_stop_at, hard_stop_at
                from meta.api_quota_daily
                where quota_date = ? and quota_channel = 'direct'
                """,
                [quota_date],
            ).fetchone()
        if row is None:
            return None
        request_count, retry_count, login_count, blacklisted, soft_stop_at, hard_stop_at = row
        return {
            "request_count": request_count or 0,
            "retry_count": retry_count or 0,
            "login_count": login_count or 0,
            "blacklisted": bool(blacklisted),
            "soft_stop_at": soft_stop_at,
            "hard_stop_at": hard_stop_at,
        }

    def clear_expired_leases(self) -> int:
        with self.duckdb.connect(read_only=False) as connection:
            rows = connection.execute(
                """
                update meta.chunk_state
                set status = 'pending',
                    lease_run_id = null,
                    lease_expires_at = null,
                    lease_token = null,
                    updated_at = current_timestamp
                where status = 'running'
                  and lease_expires_at is not null
                  and lease_expires_at < current_timestamp
                returning dataset_name
                """
            ).fetchall()
        return len(rows)

    def get_latest_trading_day(self, today: date) -> date | None:
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select max(calendar_date)
                from source.trade_calendar
                where is_trading_day = 1 and calendar_date <= ?
                """,
                [today],
            ).fetchone()
        return None if row is None else row[0]

    def replace_source_rows(
        self,
        *,
        dataset_name: str,
        rows: list[dict[str, Any]],
        replace_strategy: str,
        scope: dict[str, Any],
        expected_columns: list[str],
        logical_key: list[str],
    ) -> int:
        count, _validation_results = self.stage_validate_replace_source_rows(
            dataset_name=dataset_name,
            rows=rows,
            replace_strategy=replace_strategy,
            scope=scope,
            expected_columns=expected_columns,
            logical_key=logical_key,
        )
        failed_errors = [
            result
            for result in _validation_results
            if not result["passed"] and result["severity"] == "error"
        ]
        if failed_errors:
            raise ValueError(f"{dataset_name} staging validation failed")
        return count

    def stage_validate_replace_source_rows(
        self,
        *,
        dataset_name: str,
        rows: list[dict[str, Any]],
        replace_strategy: str,
        scope: dict[str, Any],
        expected_columns: list[str],
        logical_key: list[str],
    ) -> tuple[int, list[dict[str, Any]]]:
        columns = SOURCE_TABLE_COLUMNS[dataset_name]
        table_name = f"source.{dataset_name}"
        values = [[row.get(column) for column in columns] for row in rows]
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute("begin transaction")
            staging_table_name = f"temp.staging_{dataset_name}"
            try:
                connection.execute(
                    f"create temp table staging_{dataset_name} as "
                    f"select {', '.join(columns)} from {table_name} where false"
                )
                if values:
                    placeholders = ", ".join(["?"] * len(columns))
                    column_sql = ", ".join(columns)
                    connection.executemany(
                        f"insert into {staging_table_name}({column_sql}) "
                        f"values ({placeholders})",
                        values,
                    )

                validation_results = self._validate_dataset_relation(
                    connection=connection,
                    dataset_name=dataset_name,
                    relation_name=staging_table_name,
                    expected_columns=expected_columns,
                    logical_key=logical_key,
                    scope=scope,
                )
                failed_errors = [
                    result
                    for result in validation_results
                    if not result["passed"] and result["severity"] == "error"
                ]
                if failed_errors:
                    connection.execute("rollback")
                    return len(rows), validation_results

                self._delete_source_scope(
                    connection=connection,
                    table_name=table_name,
                    replace_strategy=replace_strategy,
                    scope=scope,
                )

                if values:
                    column_sql = ", ".join(columns)
                    connection.execute(
                        f"insert into {table_name}({column_sql}) "
                        f"select {column_sql} from {staging_table_name}"
                    )
                connection.execute("commit")
            except Exception:
                connection.execute("rollback")
                raise
        return len(rows), validation_results

    def _delete_source_scope(
        self,
        *,
        connection: Any,
        table_name: str,
        replace_strategy: str,
        scope: dict[str, Any],
    ) -> None:
        if replace_strategy == "full_table":
            connection.execute(f"delete from {table_name}")
        elif replace_strategy == "date_window":
            connection.execute(
                f"delete from {table_name} where calendar_date between ? and ?",
                [scope["start_date"], scope["end_date"]],
            )
        elif replace_strategy == "single_date":
            connection.execute(
                f"delete from {table_name} where trade_date = ?",
                [scope["trade_date"]],
            )
        else:
            raise ValueError(f"unsupported replace strategy: {replace_strategy}")

    def validate_source_dataset(
        self,
        *,
        dataset_name: str,
        expected_columns: list[str],
        logical_key: list[str],
        scope: dict[str, Any],
    ) -> list[dict[str, Any]]:
        with self.duckdb.connect(read_only=True) as connection:
            return self._validate_dataset_relation(
                connection=connection,
                dataset_name=dataset_name,
                relation_name=f"source.{dataset_name}",
                expected_columns=expected_columns,
                logical_key=logical_key,
                scope=scope,
            )

    def _validate_dataset_relation(
        self,
        *,
        connection: Any,
        dataset_name: str,
        relation_name: str,
        expected_columns: list[str],
        logical_key: list[str],
        scope: dict[str, Any],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        actual_rows = connection.execute(f"describe {relation_name}").fetchall()
        actual_columns = [row[0] for row in actual_rows]
        schema_passed = actual_columns == expected_columns
        results.append(
            {
                "rule_name": "schema",
                "severity": "error",
                "passed": schema_passed,
                "sample_count": 0,
                "detail": {
                    "actual": actual_columns,
                    "expected": expected_columns,
                },
            }
        )

        duplicate_groups = 0
        if logical_key:
            key_sql = ", ".join(logical_key)
            duplicate_groups = connection.execute(
                f"""
                select count(*)
                from (
                    select {key_sql}, count(*) as row_count
                    from {relation_name}
                    group by {key_sql}
                    having count(*) > 1
                )
                """
            ).fetchone()[0]
        results.append(
            {
                "rule_name": "logical_key",
                "severity": "error",
                "passed": duplicate_groups == 0,
                "sample_count": duplicate_groups,
                "detail": {"duplicate_groups": duplicate_groups},
            }
        )

        if dataset_name == "trade_calendar":
            row_count = connection.execute(
                f"""
                select count(*)
                from {relation_name}
                where calendar_date between ? and ?
                """,
                [scope["start_date"], scope["end_date"]],
            ).fetchone()[0]
            expected_days = (
                date.fromisoformat(scope["end_date"])
                - date.fromisoformat(scope["start_date"])
            ).days + 1
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": row_count == expected_days,
                    "sample_count": row_count,
                    "detail": {
                        "expected_days": expected_days,
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                    },
                }
            )
        elif dataset_name == "security_master":
            row_count, missing_code = connection.execute(
                f"""
                select count(*),
                       sum(case when code is null or code = '' then 1 else 0 end)
                from {relation_name}
                where last_seen_date = ?
                """,
                [scope["date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": row_count > 0 and (missing_code or 0) == 0,
                    "sample_count": row_count,
                    "detail": {"missing_code": int(missing_code or 0)},
                }
            )
        elif dataset_name == "all_stock_snapshot":
            row_count, missing_code = connection.execute(
                f"""
                select count(*),
                       sum(case when code is null or code = '' then 1 else 0 end)
                from {relation_name}
                where trade_date = ?
                """,
                [scope["trade_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": row_count > 0 and (missing_code or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "trade_date": scope["trade_date"],
                        "missing_code": int(missing_code or 0),
                    },
                }
            )
        return results

    def update_watermark(
        self,
        *,
        dataset_name: str,
        asset_scope: str,
        watermark_value: str,
    ) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                delete from meta.dataset_watermark
                where dataset_name = ? and asset_scope = ?
                """,
                [dataset_name, asset_scope],
            )
            connection.execute(
                """
                insert into meta.dataset_watermark(
                    dataset_name, asset_scope, watermark_value,
                    repair_backfill_from, updated_at
                )
                values (?, ?, ?, null, current_timestamp)
                """,
                [dataset_name, asset_scope, watermark_value],
            )

    def upsert_chunk_state(
        self,
        *,
        dataset_name: str,
        chunk_key: str,
        scope: dict[str, Any],
        status: str,
        run_id: int | None = None,
        row_count: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            existing = connection.execute(
                """
                select coalesce(attempts, 0)
                from meta.chunk_state
                where dataset_name = ? and chunk_key = ?
                """,
                [dataset_name, chunk_key],
            ).fetchone()
            previous_attempts = 0 if existing is None else int(existing[0] or 0)
            attempts = previous_attempts
            if status == "running" or previous_attempts == 0:
                attempts = previous_attempts + 1
            connection.execute(
                """
                delete from meta.chunk_state
                where dataset_name = ? and chunk_key = ?
                """,
                [dataset_name, chunk_key],
            )
            connection.execute(
                """
                insert into meta.chunk_state(
                    dataset_name, chunk_key, scope_json, status, attempts,
                    lease_run_id, lease_expires_at, last_error_code,
                    last_error_msg, row_count, checksum, last_success_at,
                    updated_at, lease_token
                )
                values (?, ?, ?, ?, ?, ?, null, ?, ?, ?, null,
                        case when ? = 'success' then current_timestamp else null end,
                        current_timestamp, null)
                """,
                [
                    dataset_name,
                    chunk_key,
                    json.dumps(scope, ensure_ascii=False),
                    status,
                    attempts,
                    run_id,
                    error_code,
                    error_message,
                    row_count,
                    status,
                ],
            )

    def write_validation_result(
        self,
        *,
        run_id: int,
        dataset_name: str,
        scope: dict[str, Any],
        rule_name: str,
        severity: str,
        passed: bool,
        sample_count: int,
        detail: dict[str, Any],
    ) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                insert into meta.validation_result(
                    run_id, dataset_name, scope_json, rule_name, severity,
                    passed, sample_count, detail_json, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                """,
                [
                    run_id,
                    dataset_name,
                    json.dumps(scope, ensure_ascii=False),
                    rule_name,
                    severity,
                    1 if passed else 0,
                    sample_count,
                    json.dumps(detail, ensure_ascii=False),
                ],
            )

    def _resolve_status(
        self,
        watermark: Any,
        actual_max_date: Any,
        validation_failed_count: int,
        chunk_failed_count: int,
        open_repair_count: int,
        latest_chunk_status: str | None,
    ) -> str:
        if open_repair_count > 0:
            return "repair"
        if chunk_failed_count > 0 or latest_chunk_status == "failed":
            return "error"
        if validation_failed_count > 0:
            return "validation_failed"
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
