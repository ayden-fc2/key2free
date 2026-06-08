from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.dtos.data_asset_dto import MartDatasetOverviewDTO, StockDatasetOverviewDTO
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
    "bar_1d_raw": [
        "trade_date",
        "trade_year",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "adjustflag",
        "turn",
        "tradestatus",
        "pct_chg",
        "pe_ttm",
        "pb_mrq",
        "ps_ttm",
        "pcf_ncf_ttm",
        "is_st",
        "ingest_run_id",
        "loaded_at",
    ],
    "bar_5m_raw": [
        "trade_date",
        "trade_year",
        "code",
        "time_raw",
        "bar_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "adjustflag",
        "ingest_run_id",
        "loaded_at",
    ],
    "adjust_factor": [
        "code",
        "divid_operate_date",
        "fore_adjust_factor",
        "back_adjust_factor",
        "adjust_factor",
        "ingest_run_id",
        "loaded_at",
    ],
    "dividend": [
        "code",
        "query_year",
        "query_year_type",
        "divid_pre_notice_date",
        "divid_agm_pum_date",
        "divid_plan_announce_date",
        "divid_plan_date",
        "divid_regist_date",
        "divid_operate_date",
        "divid_pay_date",
        "divid_stock_market_date",
        "divid_cash_ps_before_tax",
        "divid_cash_ps_after_tax",
        "divid_stocks_ps",
        "divid_cash_stock",
        "divid_reserve_to_stock_ps",
        "ingest_run_id",
        "loaded_at",
    ],
    "profit": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "roe_avg",
        "np_margin",
        "gp_margin",
        "net_profit",
        "eps_ttm",
        "mb_revenue",
        "total_share",
        "liqa_share",
        "ingest_run_id",
        "loaded_at",
    ],
    "operation": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "nr_turn_ratio",
        "nr_turn_days",
        "inv_turn_ratio",
        "inv_turn_days",
        "ca_turn_ratio",
        "asset_turn_ratio",
        "ingest_run_id",
        "loaded_at",
    ],
    "growth": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "yoy_equity",
        "yoy_asset",
        "yoyni",
        "yoyeps_basic",
        "yoypni",
        "ingest_run_id",
        "loaded_at",
    ],
    "balance": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "current_ratio",
        "quick_ratio",
        "cash_ratio",
        "yoy_liability",
        "liability_to_asset",
        "asset_to_equity",
        "ingest_run_id",
        "loaded_at",
    ],
    "cash_flow": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "ca_to_asset",
        "nca_to_asset",
        "tangible_asset_to_asset",
        "ebit_to_interest",
        "cfo_to_or",
        "cfo_to_np",
        "cfo_to_gr",
        "ingest_run_id",
        "loaded_at",
    ],
    "dupont": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "dupont_roe",
        "dupont_asset_sto_equity",
        "dupont_asset_turn",
        "dupont_pnitoni",
        "dupont_nitogr",
        "dupont_tax_burden",
        "dupont_intburden",
        "dupont_ebittogr",
        "ingest_run_id",
        "loaded_at",
    ],
    "performance_express": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "performance_exp_update_date",
        "performance_express_total_asset",
        "performance_express_net_asset",
        "performance_express_eps_chg_pct",
        "performance_express_roe_wa",
        "performance_express_eps_diluted",
        "performance_express_gryoy",
        "performance_express_opyoy",
        "ingest_run_id",
        "loaded_at",
    ],
    "forecast": [
        "code",
        "pub_date",
        "stat_date",
        "fiscal_year",
        "fiscal_quarter",
        "profit_forcast_type",
        "profit_forcast_abstract",
        "profit_forcast_chg_pct_up",
        "profit_forcast_chg_pct_dwn",
        "ingest_run_id",
        "loaded_at",
    ],
    "deposit_rate": [
        "pub_date",
        "demand_deposit_rate",
        "fixed_deposit_rate3_month",
        "fixed_deposit_rate6_month",
        "fixed_deposit_rate1_year",
        "fixed_deposit_rate2_year",
        "fixed_deposit_rate3_year",
        "fixed_deposit_rate5_year",
        "installment_fixed_deposit_rate1_year",
        "installment_fixed_deposit_rate3_year",
        "installment_fixed_deposit_rate5_year",
        "ingest_run_id",
        "loaded_at",
    ],
    "loan_rate": [
        "pub_date",
        "loan_rate6_month",
        "loan_rate6_month_to1_year",
        "loan_rate1_year_to3_year",
        "loan_rate3_year_to5_year",
        "loan_rate_above5_year",
        "mortgate_rate_below5_year",
        "mortgate_rate_above5_year",
        "ingest_run_id",
        "loaded_at",
    ],
    "reserve_ratio": [
        "pub_date",
        "effective_date",
        "big_institutions_ratio_pre",
        "big_institutions_ratio_after",
        "medium_institutions_ratio_pre",
        "medium_institutions_ratio_after",
        "ingest_run_id",
        "loaded_at",
    ],
    "money_supply_month": [
        "stat_year",
        "stat_month",
        "m0_month",
        "m0_yoy",
        "m0_chain_relative",
        "m1_month",
        "m1_yoy",
        "m1_chain_relative",
        "m2_month",
        "m2_yoy",
        "m2_chain_relative",
        "stat_date",
        "ingest_run_id",
        "loaded_at",
    ],
    "money_supply_year": [
        "stat_year",
        "m0_year",
        "m0_year_yoy",
        "m1_year",
        "m1_year_yoy",
        "m2_year",
        "m2_year_yoy",
        "stat_date",
        "ingest_run_id",
        "loaded_at",
    ],
    "industry_snapshot": [
        "update_date",
        "code",
        "code_name",
        "industry",
        "industry_classification",
        "updated_at",
    ],
    "index_member_snapshot": [
        "index_code",
        "index_name",
        "update_date",
        "code",
        "code_name",
        "updated_at",
    ],
}

SOURCE_LOGICAL_KEYS: dict[str, list[str]] = {
    "dividend": [],
}

MAINTAINED_SOURCE_DATASETS: set[str] = {
    "trade_calendar",
    "all_stock_snapshot",
    "bar_1d_raw",
    "adjust_factor",
}

MAINTAINED_MART_DATASETS: set[str] = {
    "universe_daily",
    "bar_1d_qfq",
}


class DataAssetRepository:
    DAILY_TRADING_COVERAGE_DATASETS: set[str] = {
        "all_stock_snapshot",
        "bar_1d_raw",
    }
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
    MART_DATE_COLUMN_CANDIDATES: tuple[str, ...] = (
        "trade_date",
        "calendar_date",
        "stat_date",
        "update_date",
        "pub_date",
        "bar_time",
    )

    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def sync_catalog_maintenance_flags(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            self.sync_catalog_maintenance_flags_with_connection(connection)

    def sync_catalog_maintenance_flags_with_connection(self, connection: Any) -> None:
        source_names = sorted(MAINTAINED_SOURCE_DATASETS)
        mart_names = sorted(MAINTAINED_MART_DATASETS)
        connection.execute(
            """
            update meta.dataset_catalog
            set enabled = case
                when coalesce(tier, '') <> 'mart'
                 and dataset_name in (select unnest(?))
                then 1
                when tier = 'mart'
                 and dataset_name in (select unnest(?))
                then 1
                else 0
            end
            """,
            [source_names, mart_names],
        )

    def get_stock_dataset_overview(self) -> list[StockDatasetOverviewDTO]:
        self.sync_catalog_maintenance_flags()
        with self.duckdb.connect(read_only=True) as connection:
            catalog_rows = connection.execute(
                """
                select dataset_name, endpoint, enabled, priority
                from meta.dataset_catalog
                where coalesce(tier, '') <> 'mart'
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

    def get_mart_dataset_overview(self) -> list[MartDatasetOverviewDTO]:
        self.sync_catalog_maintenance_flags()
        with self.duckdb.connect(read_only=True) as connection:
            catalog_rows = connection.execute(
                """
                select c.dataset_name,
                       coalesce(t.table_type, 'UNKNOWN') as table_type,
                       c.enabled,
                       c.priority
                from meta.dataset_catalog c
                left join information_schema.tables t
                  on t.table_schema = 'mart'
                 and t.table_name = c.dataset_name
                where c.tier = 'mart'
                order by c.priority, c.dataset_name
                """
            ).fetchall()
            watermark_rows = connection.execute(
                """
                select dataset_name, watermark_value, updated_at
                from meta.dataset_watermark
                where asset_scope = 'mart'
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
                    select dataset_name, status, row_count,
                           row_number() over (
                               partition by dataset_name
                               order by updated_at desc nulls last
                           ) as rn
                    from meta.chunk_state
                    where dataset_name in (
                        select dataset_name
                        from meta.dataset_catalog
                        where tier = 'mart'
                    )
                )
                select dataset_name, status, row_count
                from ranked
                where rn = 1
                """
            ).fetchall()
            latest_chunks = {
                dataset_name: {
                    "status": status,
                    "row_count": None if row_count is None else int(row_count),
                }
                for dataset_name, status, row_count in latest_chunk_rows
            }

            datasets: list[MartDatasetOverviewDTO] = []
            for dataset_name, table_type, enabled, _priority in catalog_rows:
                table_name = f"mart.{dataset_name}"
                watermark_item = watermarks.get(dataset_name, {})
                validation_item = validations.get(dataset_name, {})
                chunk_item = latest_chunks.get(dataset_name, {})
                watermark = watermark_item.get("watermark")
                row_count = chunk_item.get("row_count")
                actual_max_date_str = watermark
                if table_type == "BASE TABLE":
                    columns = self._get_relation_columns(connection, table_name)
                    date_column = self._resolve_mart_date_column(columns)
                    row_count, actual_max_date = self._get_relation_count_and_max_date(
                        connection=connection,
                        table_name=table_name,
                        date_column=date_column,
                    )
                    actual_max_date_str = None if actual_max_date is None else str(actual_max_date)
                validation_failed_count = int(validation_item.get("failed_count") or 0)
                status = self._resolve_mart_status(
                    watermark=watermark,
                    actual_max_date=actual_max_date_str,
                    validation_failed_count=validation_failed_count,
                    row_count=row_count,
                    table_type=table_type,
                )
                datasets.append(
                    MartDatasetOverviewDTO(
                        dataset_name=dataset_name,
                        table_name=table_name,
                        table_type=table_type,
                        enabled=bool(enabled),
                        row_count=row_count,
                        watermark=watermark,
                        actual_max_date=actual_max_date_str,
                        updated_at=watermark_item.get("updated_at"),
                        status=status,
                        latest_validation_at=validation_item.get("latest_validation_at"),
                        validation_failed_count=validation_failed_count,
                    )
                )
        return datasets

    def get_enabled_source_catalog(self) -> list[dict[str, Any]]:
        self.sync_catalog_maintenance_flags()
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select dataset_name, endpoint, tier, enabled, asset_scope,
                       chunk_strategy, replace_strategy, logical_key_json,
                       expected_columns_json, duckdb_schema_json,
                       validation_rules_json, priority,
                       (
                           select watermark_value
                           from meta.dataset_watermark w
                           where w.dataset_name = c.dataset_name
                             and w.asset_scope = c.asset_scope
                       ) as current_watermark
                from meta.dataset_catalog c
                where enabled = 1
                  and coalesce(tier, '') <> 'mart'
                order by priority, dataset_name
                """
            ).fetchall()
        catalog = [
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
                "current_watermark": current_watermark,
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
                current_watermark,
            ) in rows
        ]
        for item in catalog:
            if item["dataset_name"] in SOURCE_LOGICAL_KEYS:
                item["logical_key"] = SOURCE_LOGICAL_KEYS[item["dataset_name"]]
            if item["dataset_name"] in {
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
            }:
                item["asset_universe"] = self.get_asset_universe(item["asset_scope"])
        return catalog

    def get_asset_universe(self, asset_scope: str) -> list[dict[str, Any]]:
        if asset_scope not in {"equity_index_etf", "equity_etf", "equity"}:
            raise ValueError(f"unsupported asset_scope: {asset_scope}")

        latest_snapshot_date = self.get_dataset_actual_max_date("all_stock_snapshot")
        if latest_snapshot_date is None:
            return []

        type_filter = ""
        if asset_scope == "equity":
            type_filter = "and not (code like 'sh.000%' or code like 'sz.399%' or code like 'sh.51%' or code like 'sz.15%' or code like 'sz.16%')"
        elif asset_scope == "equity_etf":
            type_filter = "and not (code like 'sh.000%' or code like 'sz.399%')"

        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                f"""
                with latest_codes as (
                    select distinct code
                    from source.all_stock_snapshot
                    where trade_date = ?::date
                      and code is not null
                      and code <> ''
                      {type_filter}
                )
                select s.code,
                       min(s.trade_date) as ipo_date,
                       null as out_date,
                       case
                           when s.code like 'sh.000%' or s.code like 'sz.399%' then 2
                           when s.code like 'sh.51%' or s.code like 'sz.15%' or s.code like 'sz.16%' then 5
                           else 1
                       end as security_type
                from source.all_stock_snapshot s
                join latest_codes l on s.code = l.code
                group by s.code
                order by s.code
                """,
                [latest_snapshot_date],
            ).fetchall()
        return [
            {
                "code": code,
                "ipo_date": ipo_date,
                "out_date": out_date,
                "security_type": security_type,
            }
            for code, ipo_date, out_date, security_type in rows
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

    def get_missing_snapshot_trading_days(
        self,
        *,
        start_date: date,
        end_date: date,
        dataset_name: str,
    ) -> list[date]:
        if dataset_name != "all_stock_snapshot":
            raise ValueError(f"unsupported snapshot dataset: {dataset_name}")
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select trade_date
                from (
                    select calendar_date as trade_date
                    from source.trade_calendar
                    where is_trading_day = 1
                      and calendar_date between ? and ?
                    except
                    select distinct trade_date
                    from source.all_stock_snapshot
                    where trade_date between ? and ?
                )
                order by trade_date
                """,
                [start_date, end_date, start_date, end_date],
            ).fetchall()
        return [row[0] for row in rows]

    def get_trading_days(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select calendar_date
                from source.trade_calendar
                where is_trading_day = 1
                  and calendar_date between ? and ?
                order by calendar_date
                """,
                [start_date, end_date],
            ).fetchall()
        return [row[0] for row in rows]

    def get_daily_source_coverage_issues(
        self,
        *,
        dataset_name: str,
        end_date: date,
        start_date: date | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if dataset_name not in self.DAILY_TRADING_COVERAGE_DATASETS:
            raise ValueError(f"unsupported daily coverage dataset: {dataset_name}")
        physical = self.DATASET_TABLES[dataset_name]
        table_name = physical["table_name"]
        date_column = physical["date_column"]
        with self.duckdb.connect(read_only=True) as connection:
            if start_date is None:
                row = connection.execute(
                    f"select min({date_column}) from {table_name}"
                ).fetchone()
                start_date = None if row is None else row[0]
            if start_date is None:
                return []

            min_expected_codes_sql = "1"
            min_expected_rows_sql = "1"
            if dataset_name == "all_stock_snapshot":
                min_expected_codes_sql = """
                    case
                        when coalesce(reference_snapshot_count, 0) > 0
                        then greatest(1, cast(ceil(reference_snapshot_count * 0.75) as bigint))
                        else 1
                    end
                """
                min_expected_rows_sql = min_expected_codes_sql
            elif dataset_name == "bar_1d_raw":
                min_expected_codes_sql = """
                    case
                        when coalesce(snapshot_count, 0) > 0
                        then greatest(1, cast(ceil(snapshot_count * 0.5) as bigint))
                        else 1
                    end
                """
                min_expected_rows_sql = min_expected_codes_sql
            elif dataset_name == "bar_5m_raw":
                min_expected_codes_sql = "1"
                min_expected_rows_sql = """
                    case
                        when coalesce(snapshot_count, 0) > 0
                        then greatest(1, cast(snapshot_count * 35 as bigint))
                        else 1
                    end
                """

            limit_sql = "" if limit is None else f"limit {int(limit)}"
            rows = connection.execute(
                f"""
                with trading_days as (
                    select calendar_date as trade_date
                    from source.trade_calendar
                    where is_trading_day = 1
                      and calendar_date between ? and ?
                ),
                source_counts as (
                    select {date_column} as trade_date,
                           count(*) as row_count,
                           count(distinct code) as code_count
                    from {table_name}
                    where {date_column} between ? and ?
                    group by {date_column}
                ),
                snapshot_counts as (
                    select trade_date, count(*) as snapshot_count
                    from source.all_stock_snapshot
                    where trade_date between ? and ?
                    group by trade_date
                ),
                same_day_active_counts as (
                    select trade_date, count(*) as active_security_count
                    from source.all_stock_snapshot
                    where trade_date between ? and ?
                      and code is not null
                      and code <> ''
                    group by trade_date
                ),
                reference_snapshot_counts as (
                    select d.trade_date,
                           coalesce(
                               (
                                   select p.snapshot_count
                                   from snapshot_counts p
                                   where p.trade_date < d.trade_date
                                   order by p.trade_date desc
                                   limit 1
                               ),
                               (
                                   select n.snapshot_count
                                   from snapshot_counts n
                                   where n.trade_date > d.trade_date
                                   order by n.trade_date asc
                                   limit 1
                               )
                           ) as reference_snapshot_count
                    from trading_days d
                ),
                coverage as (
                    select d.trade_date,
                           coalesce(s.row_count, 0) as row_count,
                           coalesce(s.code_count, 0) as code_count,
                           coalesce(a.snapshot_count, 0) as snapshot_count,
                           coalesce(same_day.active_security_count, 0) as active_security_count,
                           coalesce(ref.reference_snapshot_count, 0) as reference_snapshot_count,
                           {min_expected_codes_sql} as min_expected_codes,
                           {min_expected_rows_sql} as min_expected_rows
                    from trading_days d
                    left join source_counts s on d.trade_date = s.trade_date
                    left join snapshot_counts a on d.trade_date = a.trade_date
                    left join same_day_active_counts same_day on d.trade_date = same_day.trade_date
                    left join reference_snapshot_counts ref on d.trade_date = ref.trade_date
                )
                select trade_date,
                       row_count,
                       code_count,
                       snapshot_count,
                       active_security_count,
                       reference_snapshot_count,
                       min_expected_codes,
                       min_expected_rows,
                       case
                           when row_count = 0 then 'missing'
                           when code_count < min_expected_codes then 'partial_codes'
                           else 'partial_rows'
                       end as issue_type
                from coverage
                where row_count < min_expected_rows
                   or code_count < min_expected_codes
                order by trade_date
                {limit_sql}
                """,
                [
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                    start_date,
                    end_date,
                ],
            ).fetchall()
        return [
            {
                "trade_date": trade_date,
                "row_count": int(row_count or 0),
                "code_count": int(code_count or 0),
                "snapshot_count": int(snapshot_count or 0),
                "active_security_count": int(active_security_count or 0),
                "reference_snapshot_count": int(reference_snapshot_count or 0),
                "min_expected_codes": int(min_expected_codes or 0),
                "min_expected_rows": int(min_expected_rows or 0),
                "issue_type": issue_type,
            }
            for (
                trade_date,
                row_count,
                code_count,
                snapshot_count,
                active_security_count,
                reference_snapshot_count,
                min_expected_codes,
                min_expected_rows,
                issue_type,
            ) in rows
        ]

    def validate_source_watermark_coverage(
        self,
        *,
        dataset_name: str,
        watermark_value: str,
    ) -> list[dict[str, Any]]:
        if dataset_name not in self.DAILY_TRADING_COVERAGE_DATASETS:
            return []
        physical = self.DATASET_TABLES[dataset_name]
        table_name = physical["table_name"]
        date_column = physical["date_column"]
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                f"select min({date_column}) from {table_name}"
            ).fetchone()
        start_date = None if row is None else row[0]
        if start_date is None:
            return [
                {
                    "rule_name": "trading_date_coverage",
                    "severity": "error",
                    "passed": False,
                    "sample_count": 0,
                    "detail": {
                        "watermark_value": watermark_value,
                        "reason": "source table is empty",
                    },
                }
            ]

        issues = self.get_daily_source_coverage_issues(
            dataset_name=dataset_name,
            start_date=start_date,
            end_date=date.fromisoformat(str(watermark_value)[:10]),
            limit=50,
        )
        return [
            {
                "rule_name": "trading_date_coverage",
                "severity": "error",
                "passed": not issues,
                "sample_count": len(issues),
                "detail": {
                    "start_date": str(start_date),
                    "watermark_value": watermark_value,
                    "issue_sample": [
                        {
                            "trade_date": str(item["trade_date"]),
                            "issue_type": item["issue_type"],
                            "row_count": item["row_count"],
                            "code_count": item["code_count"],
                            "snapshot_count": item["snapshot_count"],
                            "active_security_count": item["active_security_count"],
                            "min_expected_codes": item["min_expected_codes"],
                            "min_expected_rows": item["min_expected_rows"],
                        }
                        for item in issues[:10]
                    ],
                },
            }
        ]

    def get_dataset_actual_max_date(self, dataset_name: str) -> str | None:
        physical = self.DATASET_TABLES.get(dataset_name)
        if physical is None:
            return None
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                select max({physical["date_column"]})
                from {physical["table_name"]}
                """
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def get_dataset_actual_min_date(self, dataset_name: str) -> date | None:
        physical = self.DATASET_TABLES.get(dataset_name)
        if physical is None:
            return None
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                select min({physical["date_column"]})
                from {physical["table_name"]}
                """
            ).fetchone()
        if row is None:
            return None
        return row[0]

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
            staging_table_name = f"temp.staging_{dataset_name}"
            staging_relation_name = f"staging_{dataset_name}"
            validation_relation_name = staging_table_name
            written_count = len(rows)
            try:
                connection.execute(f"drop table if exists {staging_table_name}")
                connection.execute("begin transaction")
                connection.execute(
                    f"create temp table {staging_relation_name} as "
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
                if dataset_name == "dividend":
                    dedup_relation_name = f"{staging_relation_name}_dedup"
                    connection.execute(
                        f"create temp table {dedup_relation_name} as "
                        f"select distinct * from {staging_table_name}"
                    )
                    validation_relation_name = f"temp.{dedup_relation_name}"

                validation_results = self._validate_dataset_relation(
                    connection=connection,
                    dataset_name=dataset_name,
                    relation_name=validation_relation_name,
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
                    written_count = connection.execute(
                        f"select count(*) from {validation_relation_name}"
                    ).fetchone()[0]
                    connection.execute(
                        f"insert into {table_name}({column_sql}) "
                        f"select {column_sql} from {validation_relation_name}"
                    )
                connection.execute("commit")
            except Exception:
                connection.execute("rollback")
                raise
            finally:
                if dataset_name == "dividend":
                    connection.execute(
                        f"drop table if exists temp.{staging_relation_name}_dedup"
                    )
                connection.execute(f"drop table if exists {staging_table_name}")
        return written_count, validation_results

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
            if table_name.endswith((".trade_calendar",)):
                date_column = "calendar_date"
            elif table_name.endswith((".deposit_rate", ".loan_rate")):
                date_column = "pub_date"
            elif table_name.endswith(".reserve_ratio"):
                date_column = "effective_date"
            elif table_name.endswith((".money_supply_month", ".money_supply_year")):
                date_column = "stat_date"
            else:
                raise ValueError(f"date_window unsupported table: {table_name}")
            connection.execute(
                f"delete from {table_name} where {date_column} between ? and ?",
                [scope["start_date"], scope["end_date"]],
            )
        elif replace_strategy == "single_date":
            if table_name.endswith(".all_stock_snapshot"):
                connection.execute(
                    f"delete from {table_name} where trade_date = ?",
                    [scope["trade_date"]],
                )
            elif table_name.endswith(".industry_snapshot"):
                connection.execute(
                    f"delete from {table_name} where update_date = ?",
                    [scope["update_date"]],
                )
            else:
                raise ValueError(f"single_date unsupported table: {table_name}")
        elif replace_strategy == "code_or_code_year":
            if "start_date" in scope and "end_date" in scope:
                connection.execute(
                    f"""
                    delete from {table_name}
                    where code = ? and trade_date between ? and ?
                    """,
                    [scope["code"], scope["start_date"], scope["end_date"]],
                )
            elif "trade_year" in scope:
                connection.execute(
                    f"delete from {table_name} where code = ? and trade_year = ?",
                    [scope["code"], scope["trade_year"]],
                )
            else:
                raise ValueError("code_or_code_year requires date window or trade_year")
        elif replace_strategy == "code_year_or_quarter":
            if "start_date" in scope and "end_date" in scope:
                connection.execute(
                    f"""
                    delete from {table_name}
                    where code = ? and trade_date between ? and ?
                    """,
                    [scope["code"], scope["start_date"], scope["end_date"]],
                )
            elif "trade_year" in scope:
                connection.execute(
                    f"delete from {table_name} where code = ? and trade_year = ?",
                    [scope["code"], scope["trade_year"]],
                )
            else:
                raise ValueError("code_year_or_quarter requires date window or trade_year")
        elif replace_strategy == "code_date_window":
            if table_name.endswith(".adjust_factor"):
                connection.execute(
                    f"""
                    delete from {table_name}
                    where code = ? and divid_operate_date between ? and ?
                    """,
                    [scope["code"], scope["start_date"], scope["end_date"]],
                )
            elif table_name.endswith(".performance_express"):
                connection.execute(
                    f"""
                    delete from {table_name}
                    where code = ?
                      and (
                          pub_date between ? and ?
                          or performance_exp_update_date between ? and ?
                      )
                    """,
                    [
                        scope["code"],
                        scope["start_date"],
                        scope["end_date"],
                        scope["start_date"],
                        scope["end_date"],
                    ],
                )
            elif table_name.endswith(".forecast"):
                connection.execute(
                    f"""
                    delete from {table_name}
                    where code = ?
                      and (
                          pub_date between ? and ?
                          or stat_date between ? and ?
                      )
                    """,
                    [
                        scope["code"],
                        scope["start_date"],
                        scope["end_date"],
                        scope["start_date"],
                        scope["end_date"],
                    ],
                )
            else:
                raise ValueError(f"code_date_window unsupported table: {table_name}")
        elif replace_strategy == "code_year_type":
            connection.execute(
                f"""
                delete from {table_name}
                where code = ? and query_year = ? and query_year_type = ?
                """,
                [scope["code"], scope["year"], scope["year_type"]],
            )
        elif replace_strategy == "code_year_quarter":
            connection.execute(
                f"""
                delete from {table_name}
                where code = ? and fiscal_year = ? and fiscal_quarter = ?
                """,
                [scope["code"], scope["year"], scope["quarter"]],
            )
        elif replace_strategy == "index_code_date":
            connection.execute(
                f"""
                delete from {table_name}
                where index_code = ? and update_date = ?
                """,
                [scope["index_code"], scope["update_date"]],
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

    def get_dataset_watermark(
        self,
        *,
        dataset_name: str,
        asset_scope: str | None = None,
    ) -> str | None:
        where_scope = "" if asset_scope is None else "and asset_scope = ?"
        params: list[Any] = [dataset_name]
        if asset_scope is not None:
            params.append(asset_scope)
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                select watermark_value
                from meta.dataset_watermark
                where dataset_name = ?
                  {where_scope}
                order by updated_at desc nulls last
                limit 1
                """,
                params,
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def ensure_mart_catalog_item_with_connection(
        self,
        *,
        connection: Any,
        dataset_name: str,
        table_type: str,
        expected_columns: list[str],
        priority: int = 1000,
    ) -> None:
        existing = connection.execute(
            """
            select 1
            from meta.dataset_catalog
            where dataset_name = ?
            limit 1
            """,
            [dataset_name],
        ).fetchone()
        if existing is not None:
            return

        logical_key_json = (
            '["trade_date","code"]' if dataset_name == "universe_daily" else "[]"
        )
        validation_rules_json = (
            '["schema","row_count","logical_key","watermark"]'
            if table_type == "BASE TABLE"
            else '["schema","watermark"]'
        )
        connection.execute(
            """
            insert into meta.dataset_catalog(
                dataset_name, endpoint, tier, enabled, asset_scope,
                chunk_strategy, replace_strategy, logical_key_json,
                expected_columns_json, duckdb_schema_json,
                validation_rules_json, priority
            )
            values (?, 'mart_adapter', 'mart', ?, 'mart', ?, ?, ?, ?, '{}', ?, ?)
            """,
            [
                dataset_name,
                1 if dataset_name in MAINTAINED_MART_DATASETS else 0,
                "watermark_incremental" if table_type == "BASE TABLE" else "view_validate",
                "date_window" if table_type == "BASE TABLE" else "none",
                logical_key_json,
                json.dumps(expected_columns, ensure_ascii=False),
                validation_rules_json,
                priority,
            ],
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
            non_null_key_sql = " and ".join(f"{column} is not null" for column in logical_key)
            duplicate_groups = connection.execute(
                f"""
                select count(*)
                from (
                    select {key_sql}, count(*) as row_count
                    from {relation_name}
                    where {non_null_key_sql}
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
        elif dataset_name == "bar_1d_raw":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when code <> ?
                                 or trade_date < ?
                                 or trade_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when code is null
                                 or code = ''
                                 or trade_date is null
                                 or trade_year is null
                                 or trade_year <> year(trade_date)
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["code"], scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": (
                        int(out_of_scope or 0) == 0
                        and int(missing_required or 0) == 0
                    ),
                    "sample_count": row_count,
                    "detail": {
                        "code": scope["code"],
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "bar_5m_raw":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when code <> ?
                                 or trade_date < ?
                                 or trade_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when code is null
                                 or code = ''
                                 or trade_date is null
                                 or trade_year is null
                                 or trade_year <> year(trade_date)
                                 or time_raw is null
                                 or time_raw = ''
                                 or bar_time is null
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["code"], scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": (
                        int(out_of_scope or 0) == 0
                        and int(missing_required or 0) == 0
                    ),
                    "sample_count": row_count,
                    "detail": {
                        "code": scope["code"],
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "adjust_factor":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when code <> ?
                                 or divid_operate_date < ?
                                 or divid_operate_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when code is null
                                 or code = ''
                                 or divid_operate_date is null
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["code"], scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "code": scope["code"],
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "dividend":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when code <> ?
                                 or query_year <> ?
                                 or query_year_type <> ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when code is null
                                 or code = ''
                                 or query_year is null
                                 or query_year_type is null
                                 or query_year_type = ''
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["code"], scope["year"], scope["year_type"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "code": scope["code"],
                        "year": scope["year"],
                        "year_type": scope["year_type"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name in {
            "profit",
            "operation",
            "growth",
            "balance",
            "cash_flow",
            "dupont",
        }:
            if int(scope["quarter"]) == 4:
                expected_stat_date = date(int(scope["year"]), 12, 31)
            else:
                expected_stat_date = date(
                    int(scope["year"]),
                    int(scope["quarter"]) * 3 + 1,
                    1,
                ) - date.resolution
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when code <> ?
                                 or fiscal_year <> ?
                                 or fiscal_quarter <> ?
                                 or stat_date <> ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when code is null
                                 or code = ''
                                 or stat_date is null
                                 or fiscal_year is null
                                 or fiscal_quarter is null
                                 or fiscal_year <> year(stat_date)
                                 or fiscal_quarter <> quarter(stat_date)
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [
                    scope["code"],
                    scope["year"],
                    scope["quarter"],
                    expected_stat_date,
                ],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "code": scope["code"],
                        "year": scope["year"],
                        "quarter": scope["quarter"],
                        "stat_date": expected_stat_date.isoformat(),
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name in {"performance_express", "forecast"}:
            if dataset_name == "performance_express":
                scope_condition = """
                    (
                        pub_date between ? and ?
                        or performance_exp_update_date between ? and ?
                    )
                """
            else:
                scope_condition = """
                    (
                        pub_date between ? and ?
                        or stat_date between ? and ?
                    )
                """
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when code <> ?
                                 or not {scope_condition}
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when code is null
                                 or code = ''
                                 or pub_date is null
                                 or stat_date is null
                                 or fiscal_year is null
                                 or fiscal_quarter is null
                                 or fiscal_year <> year(stat_date)
                                 or fiscal_quarter <> quarter(stat_date)
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [
                    scope["code"],
                    scope["start_date"],
                    scope["end_date"],
                    scope["start_date"],
                    scope["end_date"],
                ],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "code": scope["code"],
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name in {"deposit_rate", "loan_rate"}:
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when pub_date < ? or pub_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when pub_date is null
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "reserve_ratio":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when effective_date < ? or effective_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when pub_date is null
                                 or effective_date is null
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "money_supply_month":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when stat_date < ? or stat_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when stat_year is null
                                 or stat_month is null
                                 or stat_date is null
                                 or stat_year <> year(stat_date)
                                 or stat_month <> month(stat_date)
                                 or day(stat_date) <> 1
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "money_supply_year":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when stat_date < ? or stat_date > ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when stat_year is null
                                 or stat_date is null
                                 or stat_year <> year(stat_date)
                                 or month(stat_date) <> 12
                                 or day(stat_date) <> 31
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["start_date"], scope["end_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": int(out_of_scope or 0) == 0 and int(missing_required or 0) == 0,
                    "sample_count": row_count,
                    "detail": {
                        "start_date": scope["start_date"],
                        "end_date": scope["end_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "industry_snapshot":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when update_date <> ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when update_date is null
                                 or code is null
                                 or code = ''
                                 or code_name is null
                                 or code_name = ''
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["update_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": (
                        row_count > 0
                        and int(out_of_scope or 0) == 0
                        and int(missing_required or 0) == 0
                    ),
                    "sample_count": row_count,
                    "detail": {
                        "update_date": scope["update_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
                    },
                }
            )
        elif dataset_name == "index_member_snapshot":
            row_count, out_of_scope, missing_required = connection.execute(
                f"""
                select count(*),
                       sum(
                           case
                               when index_code <> ?
                                 or update_date <> ?
                               then 1 else 0
                           end
                       ),
                       sum(
                           case
                               when index_code is null
                                 or index_code = ''
                                 or index_name is null
                                 or index_name = ''
                                 or update_date is null
                                 or code is null
                                 or code = ''
                                 or code_name is null
                                 or code_name = ''
                               then 1 else 0
                           end
                       )
                from {relation_name}
                """,
                [scope["index_code"], scope["update_date"]],
            ).fetchone()
            results.append(
                {
                    "rule_name": "scope_row_count",
                    "severity": "error",
                    "passed": (
                        row_count > 0
                        and int(out_of_scope or 0) == 0
                        and int(missing_required or 0) == 0
                    ),
                    "sample_count": row_count,
                    "detail": {
                        "index_code": scope["index_code"],
                        "update_date": scope["update_date"],
                        "out_of_scope": int(out_of_scope or 0),
                        "missing_required": int(missing_required or 0),
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
            self.update_watermark_with_connection(
                connection=connection,
                dataset_name=dataset_name,
                asset_scope=asset_scope,
                watermark_value=watermark_value,
            )

    def upsert_chunk_state(
        self,
        *,
        dataset_name: str,
        chunk_key: str,
        scope: dict[str, Any],
        status: str,
        run_id: int | None = None,
        row_count: int | None = 0,
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

    def get_completed_chunk_keys(
        self,
        dataset_name: str,
        chunks: list[Any],
    ) -> set[str]:
        if not chunks:
            return set()

        expected_scopes = {chunk.chunk_key: chunk.scope for chunk in chunks}
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select chunk_key, scope_json
                from meta.chunk_state
                where dataset_name = ?
                  and status in ('success', 'split_success')
                """,
                [dataset_name],
            ).fetchall()

        completed = set()
        for chunk_key, scope_json in rows:
            try:
                stored_scope = json.loads(scope_json or "{}")
            except json.JSONDecodeError:
                continue
            if expected_scopes.get(chunk_key) == stored_scope:
                completed.add(chunk_key)
        return completed

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
            self.write_validation_result_with_connection(
                connection=connection,
                run_id=run_id,
                dataset_name=dataset_name,
                scope=scope,
                rule_name=rule_name,
                severity=severity,
                passed=passed,
                sample_count=sample_count,
                detail=detail,
            )

    def _get_relation_columns(self, connection: Any, table_name: str) -> list[str]:
        return [row[0] for row in connection.execute(f"describe {table_name}").fetchall()]

    def _resolve_mart_date_column(self, columns: list[str]) -> str | None:
        for column in self.MART_DATE_COLUMN_CANDIDATES:
            if column in columns:
                return column
        return None

    def _get_relation_count_and_max_date(
        self,
        *,
        connection: Any,
        table_name: str,
        date_column: str | None,
    ) -> tuple[int | None, Any | None]:
        if date_column is None:
            row = connection.execute(f"select count(*) from {table_name}").fetchone()
            return row[0], None
        row = connection.execute(
            f"select count(*), max({date_column}) from {table_name}"
        ).fetchone()
        return row[0], row[1]

    def _validate_mart_relation(
        self,
        *,
        dataset_name: str,
        table_name: str,
        table_type: str,
        columns: list[str],
        row_count: int | None,
        date_column: str | None,
    ) -> list[dict[str, Any]]:
        results = [
            {
                "rule_name": "schema",
                "severity": "error",
                "passed": len(columns) > 0,
                "sample_count": len(columns),
                "detail": {
                    "schema": "mart",
                    "table_name": table_name,
                    "table_type": table_type,
                    "columns": columns,
                },
            },
        ]
        if table_type == "BASE TABLE":
            results.append(
                {
                    "rule_name": "row_count",
                    "severity": "error",
                    "passed": row_count is not None and row_count > 0,
                    "sample_count": int(row_count or 0),
                    "detail": {"row_count": int(row_count or 0)},
                }
            )
        results.append(
            {
                "rule_name": "watermark_column",
                "severity": "info",
                "passed": date_column is not None,
                "sample_count": 0,
                "detail": {"date_column": date_column},
            }
        )
        if dataset_name == "universe_daily":
            expected_columns = [
                "trade_date",
                "code",
                "code_name",
                "security_type",
                "list_status",
                "industry",
                "industry_classification",
                "is_sz50",
                "is_hs300",
                "is_zz500",
            ]
            results.append(
                {
                    "rule_name": "expected_columns",
                    "severity": "error",
                    "passed": columns == expected_columns,
                    "sample_count": len(columns),
                    "detail": {"actual": columns, "expected": expected_columns},
                }
            )
        return results

    def update_watermark_with_connection(
        self,
        *,
        connection: Any,
        dataset_name: str,
        asset_scope: str,
        watermark_value: str,
    ) -> None:
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

    def write_validation_result_with_connection(
        self,
        *,
        connection: Any,
        run_id: int,
        dataset_name: str,
        scope: dict[str, Any],
        rule_name: str,
        severity: str,
        passed: bool,
        sample_count: int,
        detail: dict[str, Any],
    ) -> None:
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

    def upsert_chunk_state_with_connection(
        self,
        *,
        connection: Any,
        dataset_name: str,
        chunk_key: str,
        scope: dict[str, Any],
        status: str,
        run_id: int | None = None,
        row_count: int | None = 0,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        existing = connection.execute(
            """
            select coalesce(attempts, 0)
            from meta.chunk_state
            where dataset_name = ? and chunk_key = ?
            """,
            [dataset_name, chunk_key],
        ).fetchone()
        previous_attempts = 0 if existing is None else int(existing[0] or 0)
        attempts = previous_attempts + 1 if status == "running" or previous_attempts == 0 else previous_attempts
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

    def create_mart_run_log(self, connection: Any) -> int:
        return connection.execute(
            """
            insert into meta.run_log(command, tier, started_at, status,
                                     request_count, retry_count, login_count,
                                     chunk_success, chunk_failed, blacklisted)
            values ('mart_refresh', 'mart', current_timestamp,
                    'running', 0, 0, 0, 0, 0, 0)
            returning run_id
            """
        ).fetchone()[0]

    def finish_mart_run_log(
        self,
        *,
        connection: Any,
        run_id: int,
        refreshed_count: int,
        failed_count: int,
        error_summary: str | None = None,
    ) -> None:
        connection.execute(
            """
            update meta.run_log
            set ended_at = current_timestamp,
                status = ?,
                exit_reason = ?,
                request_count = 0,
                retry_count = 0,
                login_count = 0,
                chunk_success = ?,
                chunk_failed = ?,
                blacklisted = 0,
                error_summary = ?
            where run_id = ?
            """,
            [
                "success" if failed_count == 0 else "partial_success",
                "completed" if failed_count == 0 else "aborted_on_error",
                refreshed_count - failed_count,
                failed_count,
                error_summary,
                run_id,
            ],
        )

    def _resolve_mart_status(
        self,
        *,
        watermark: Any,
        actual_max_date: Any,
        validation_failed_count: int,
        row_count: int | None,
        table_type: str,
    ) -> str:
        if validation_failed_count > 0:
            return "validation_failed"
        if table_type == "BASE TABLE" and (row_count is None or row_count == 0):
            return "empty"
        if actual_max_date is None:
            return "unknown"
        if watermark is None:
            return "unknown"
        return (
            "ok"
            if self._normalize_date_value(watermark)
            == self._normalize_date_value(actual_max_date)
            else "warning"
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
