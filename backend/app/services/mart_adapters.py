from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class MartAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class MartValidationResult:
    rule_name: str
    severity: str
    passed: bool
    sample_count: int
    detail: dict[str, Any]


@dataclass(frozen=True)
class MartAdapterResult:
    dataset_name: str
    row_count: int | None
    watermark_value: str | None
    validation_results: list[MartValidationResult]


class MartAdapter(Protocol):
    dataset_name: str
    table_name: str
    table_type: str
    expected_columns: list[str]
    priority: int

    def run(self, connection: Any) -> MartAdapterResult:
        ...


class MartViewAdapter:
    table_type = "VIEW"
    asset_scope = "mart"

    def __init__(
        self,
        *,
        dataset_name: str,
        upstream_dataset_name: str,
        expected_columns: list[str],
        priority: int,
    ) -> None:
        self.dataset_name = dataset_name
        self.table_name = f"mart.{dataset_name}"
        self.upstream_dataset_name = upstream_dataset_name
        self.expected_columns = expected_columns
        self.priority = priority

    def run(self, connection: Any) -> MartAdapterResult:
        columns = [row[0] for row in connection.execute(f"describe {self.table_name}").fetchall()]
        upstream_watermark = self._get_upstream_watermark(connection)
        upstream_actual_max_date = self._get_upstream_actual_max_date(connection)
        watermark_value = upstream_actual_max_date or upstream_watermark
        validation_results = [
            MartValidationResult(
                rule_name="schema",
                severity="error",
                passed=columns == self.expected_columns,
                sample_count=len(columns),
                detail={"actual": columns, "expected": self.expected_columns},
            ),
            MartValidationResult(
                rule_name="watermark",
                severity="error",
                passed=watermark_value is not None,
                sample_count=0,
                detail={"watermark_value": watermark_value},
            ),
            MartValidationResult(
                rule_name="row_count",
                severity="info",
                passed=True,
                sample_count=0,
                detail={
                    "row_count": None,
                    "note": "VIEW row_count is read from meta.chunk_state in summaries; refresh avoids materializing large views.",
                },
            ),
            MartValidationResult(
                rule_name="upstream_state",
                severity="info",
                passed=True,
                sample_count=0,
                detail={
                    "upstream_dataset_name": self.upstream_dataset_name,
                    "upstream_watermark": upstream_watermark,
                    "upstream_actual_max_date": upstream_actual_max_date,
                },
            ),
            MartValidationResult(
                rule_name="view_materialization",
                severity="info",
                passed=True,
                sample_count=0,
                detail={
                    "mode": "metadata_only",
                    "note": "VIEW adapter validates schema and advances mart watermark from upstream data state.",
                },
            ),
        ]
        self._raise_if_failed(validation_results)
        return MartAdapterResult(
            dataset_name=self.dataset_name,
            row_count=None,
            watermark_value=watermark_value,
            validation_results=validation_results,
        )

    def _get_upstream_watermark(self, connection: Any) -> str | None:
        row = connection.execute(
            """
            select watermark_value
            from meta.dataset_watermark
            where dataset_name = ?
            order by updated_at desc nulls last
            limit 1
            """,
            [self.upstream_dataset_name],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def _get_upstream_actual_max_date(self, connection: Any) -> str | None:
        if self.upstream_dataset_name in {"bar_1d_raw", "bar_5m_raw"}:
            row = connection.execute(
                f"select max(trade_date) from source.{self.upstream_dataset_name}"
            ).fetchone()
        else:
            return None
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def _raise_if_failed(self, validation_results: list[MartValidationResult]) -> None:
        failed = [
            result
            for result in validation_results
            if result.severity == "error" and not result.passed
        ]
        if failed:
            names = ", ".join(result.rule_name for result in failed)
            raise MartAdapterError(f"{self.dataset_name} validation failed: {names}")


class UniverseDailyAdapter:
    dataset_name = "universe_daily"
    table_name = "mart.universe_daily"
    table_type = "BASE TABLE"
    asset_scope = "mart"
    priority = 10
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
    index_code_to_flag = {
        "sh.000016": "is_sz50",
        "sh.000300": "is_hs300",
        "sh.000905": "is_zz500",
    }

    def run(self, connection: Any) -> MartAdapterResult:
        self._ensure_table(connection)
        initialization_result = self._initialize_from_existing_if_needed(connection)
        start_date, end_date = self._resolve_fill_window(
            connection,
            initialized_watermark=(
                None if initialization_result is None else initialization_result.watermark_value
            ),
        )
        if start_date is None or end_date is None:
            if initialization_result is not None:
                return initialization_result
            return self._validate_existing(connection)

        row_count = self._fill_window(connection, start_date, end_date)
        validation_results = self._validate_window(
            connection=connection,
            start_date=start_date,
            end_date=end_date,
            row_count=row_count,
        )
        self._raise_if_failed(validation_results)
        watermark_value = self._get_actual_max_date(connection)
        if initialization_result is not None:
            validation_results = (
                initialization_result.validation_results + validation_results
            )
            row_count += initialization_result.row_count
        return MartAdapterResult(
            dataset_name=self.dataset_name,
            row_count=row_count,
            watermark_value=watermark_value,
            validation_results=validation_results,
        )

    def _initialize_from_existing_if_needed(
        self,
        connection: Any,
    ) -> MartAdapterResult | None:
        if self._get_watermark(connection) is not None:
            return None

        row_count, actual_max_date = connection.execute(
            """
            select count(*), max(trade_date)
            from mart.universe_daily
            """
        ).fetchone()
        if actual_max_date is None:
            return None

        validation_results = self._validate_table(
            connection=connection,
            row_count=int(row_count or 0),
            watermark_value=actual_max_date,
        )
        validation_results.append(
            MartValidationResult(
                rule_name="initialize_watermark",
                severity="info",
                passed=True,
                sample_count=int(row_count or 0),
                detail={
                    "reason": "meta.dataset_watermark missing, initialized from existing mart table",
                    "watermark_value": str(actual_max_date),
                },
            )
        )
        self._raise_if_failed(validation_results)
        return MartAdapterResult(
            dataset_name=self.dataset_name,
            row_count=int(row_count or 0),
            watermark_value=str(actual_max_date),
            validation_results=validation_results,
        )

    def _ensure_table(self, connection: Any) -> None:
        connection.execute(
            """
            create schema if not exists mart
            """
        )
        connection.execute(
            """
            create table if not exists mart.universe_daily (
                trade_date date,
                code varchar,
                code_name varchar,
                security_type smallint,
                list_status smallint,
                industry varchar,
                industry_classification varchar,
                is_sz50 smallint,
                is_hs300 smallint,
                is_zz500 smallint
            )
            """
        )

    def _resolve_fill_window(
        self,
        connection: Any,
        *,
        initialized_watermark: str | None = None,
    ) -> tuple[Any | None, Any | None]:
        source_max_date = self._get_source_max_date(connection)
        if source_max_date is None:
            raise MartAdapterError("source.all_stock_snapshot has no trade_date")

        watermark = initialized_watermark or self._get_watermark(connection)
        if watermark is None:
            target_start = self._get_source_min_date(connection)
        else:
            target_start = connection.execute("select (?::date + interval 1 day)::date", [watermark]).fetchone()[0]

        missing_start = self._get_earliest_missing_source_date(connection)
        if missing_start is not None:
            target_start = missing_start if target_start is None else min(target_start, missing_start)

        if target_start is None or target_start > source_max_date:
            return None, None
        return target_start, source_max_date

    def _fill_window(self, connection: Any, start_date: Any, end_date: Any) -> int:
        connection.execute("drop table if exists temp.staging_mart_universe_daily")
        try:
            connection.execute(
                """
                create temp table staging_mart_universe_daily as
                with source_rows as (
                    select s.trade_date,
                           s.code,
                           s.code_name,
                           sm.security_type,
                           sm.list_status
                    from source.all_stock_snapshot s
                    left join source.security_master sm
                      on s.code = sm.code
                    where s.trade_date between ? and ?
                      and s.code is not null
                      and s.code <> ''
                ),
                industry_ranked as (
                    select r.trade_date,
                           r.code,
                           industry,
                           industry_classification,
                           row_number() over (
                               partition by r.trade_date, r.code
                               order by i.update_date desc nulls last
                           ) as rn
                    from source_rows r
                    left join source.industry_snapshot i
                      on r.code = i.code
                     and i.update_date <= r.trade_date
                ),
                source_dates as (
                    select distinct trade_date
                    from source_rows
                ),
                latest_index_dates as (
                    select d.trade_date,
                           m.index_code,
                           max(m.update_date) as update_date
                    from source_dates d
                    join (
                        select distinct index_code, update_date
                        from source.index_member_snapshot
                    ) m
                      on m.update_date <= d.trade_date
                    group by d.trade_date, m.index_code
                ),
                index_flags as (
                    select r.trade_date,
                           r.code,
                           max(
                               case
                                   when l.index_code = 'sh.000016' and m.code is not null
                                   then 1 else 0
                               end
                           ) as is_sz50,
                           max(
                               case
                                   when l.index_code = 'sh.000300' and m.code is not null
                                   then 1 else 0
                               end
                           ) as is_hs300,
                           max(
                               case
                                   when l.index_code = 'sh.000905' and m.code is not null
                                   then 1 else 0
                               end
                           ) as is_zz500
                    from source_rows r
                    left join latest_index_dates l
                      on r.trade_date = l.trade_date
                    left join source.index_member_snapshot m
                      on m.index_code = l.index_code
                     and m.update_date = l.update_date
                     and m.code = r.code
                    group by r.trade_date, r.code
                )
                select r.trade_date,
                       r.code,
                       r.code_name,
                       r.security_type,
                       r.list_status,
                       i.industry,
                       i.industry_classification,
                       cast(coalesce(f.is_sz50, 0) as smallint) as is_sz50,
                       cast(coalesce(f.is_hs300, 0) as smallint) as is_hs300,
                       cast(coalesce(f.is_zz500, 0) as smallint) as is_zz500
                from source_rows r
                left join industry_ranked i
                  on r.trade_date = i.trade_date and r.code = i.code and i.rn = 1
                left join index_flags f
                  on r.trade_date = f.trade_date and r.code = f.code
                """,
                [start_date, end_date],
            )
            row_count = connection.execute(
                "select count(*) from temp.staging_mart_universe_daily"
            ).fetchone()[0]
            connection.execute(
                """
                delete from mart.universe_daily
                where trade_date between ? and ?
                """,
                [start_date, end_date],
            )
            connection.execute(
                """
                insert into mart.universe_daily(
                    trade_date, code, code_name, security_type, list_status,
                    industry, industry_classification, is_sz50, is_hs300, is_zz500
                )
                select trade_date, code, code_name, security_type, list_status,
                       industry, industry_classification, is_sz50, is_hs300, is_zz500
                from temp.staging_mart_universe_daily
                """
            )
            return int(row_count or 0)
        finally:
            connection.execute("drop table if exists temp.staging_mart_universe_daily")

    def _validate_existing(self, connection: Any) -> MartAdapterResult:
        row_count, min_date, watermark_value = connection.execute(
            """
            select count(*), min(trade_date), max(trade_date)
            from mart.universe_daily
            """
        ).fetchone()
        validation_results = self._validate_table(
            connection=connection,
            row_count=int(row_count or 0),
            watermark_value=watermark_value,
        )
        if min_date is not None and watermark_value is not None:
            validation_results.append(
                self._validate_trading_date_coverage(
                    connection=connection,
                    start_date=min_date,
                    end_date=watermark_value,
                )
            )
        self._raise_if_failed(validation_results)
        return MartAdapterResult(
            dataset_name=self.dataset_name,
            row_count=int(row_count or 0),
            watermark_value=None if watermark_value is None else str(watermark_value),
            validation_results=validation_results,
        )

    def _validate_window(
        self,
        *,
        connection: Any,
        start_date: Any,
        end_date: Any,
        row_count: int,
    ) -> list[MartValidationResult]:
        validation_results = self._validate_table(
            connection=connection,
            row_count=row_count,
            watermark_value=end_date,
        )
        missing_source_dates = connection.execute(
            """
            select count(*)
            from (
                select distinct trade_date
                from source.all_stock_snapshot
                where trade_date between ? and ?
                except
                select distinct trade_date
                from mart.universe_daily
                where trade_date between ? and ?
            )
            """,
            [start_date, end_date, start_date, end_date],
        ).fetchone()[0]
        validation_results.append(
            MartValidationResult(
                rule_name="date_coverage",
                severity="error",
                passed=int(missing_source_dates or 0) == 0,
                sample_count=int(missing_source_dates or 0),
                detail={
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "missing_source_dates": int(missing_source_dates or 0),
                },
            )
        )
        validation_results.append(
            self._validate_trading_date_coverage(
                connection=connection,
                start_date=start_date,
                end_date=end_date,
            )
        )
        return validation_results

    def _validate_table(
        self,
        *,
        connection: Any,
        row_count: int,
        watermark_value: Any | None,
    ) -> list[MartValidationResult]:
        columns = [row[0] for row in connection.execute("describe mart.universe_daily").fetchall()]
        duplicate_groups = connection.execute(
            """
            select count(*)
            from (
                select trade_date, code, count(*) as row_count
                from mart.universe_daily
                group by trade_date, code
                having count(*) > 1
            )
            """
        ).fetchone()[0]
        missing_required = connection.execute(
            """
            select count(*)
            from mart.universe_daily
            where trade_date is null
               or code is null
               or code = ''
            """
        ).fetchone()[0]
        return [
            MartValidationResult(
                rule_name="schema",
                severity="error",
                passed=columns == self.expected_columns,
                sample_count=len(columns),
                detail={"actual": columns, "expected": self.expected_columns},
            ),
            MartValidationResult(
                rule_name="row_count",
                severity="error",
                passed=row_count > 0,
                sample_count=row_count,
                detail={"row_count": row_count},
            ),
            MartValidationResult(
                rule_name="logical_key",
                severity="error",
                passed=int(duplicate_groups or 0) == 0,
                sample_count=int(duplicate_groups or 0),
                detail={"duplicate_groups": int(duplicate_groups or 0)},
            ),
            MartValidationResult(
                rule_name="required_fields",
                severity="error",
                passed=int(missing_required or 0) == 0,
                sample_count=int(missing_required or 0),
                detail={"missing_required": int(missing_required or 0)},
            ),
            MartValidationResult(
                rule_name="watermark",
                severity="error",
                passed=watermark_value is not None,
                sample_count=0,
                detail={"watermark_value": None if watermark_value is None else str(watermark_value)},
            ),
        ]

    def _raise_if_failed(self, validation_results: list[MartValidationResult]) -> None:
        failed = [
            result
            for result in validation_results
            if result.severity == "error" and not result.passed
        ]
        if failed:
            names = ", ".join(result.rule_name for result in failed)
            raise MartAdapterError(f"{self.dataset_name} validation failed: {names}")

    def _get_watermark(self, connection: Any) -> str | None:
        row = connection.execute(
            """
            select watermark_value
            from meta.dataset_watermark
            where dataset_name = ? and asset_scope = ?
            order by updated_at desc nulls last
            limit 1
            """,
            [self.dataset_name, self.asset_scope],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

    def _get_source_min_date(self, connection: Any) -> Any | None:
        return connection.execute(
            "select min(trade_date) from source.all_stock_snapshot"
        ).fetchone()[0]

    def _get_source_max_date(self, connection: Any) -> Any | None:
        return connection.execute(
            "select max(trade_date) from source.all_stock_snapshot"
        ).fetchone()[0]

    def _get_earliest_missing_source_date(self, connection: Any) -> Any | None:
        return connection.execute(
            """
            select min(s.trade_date)
            from (
                select distinct trade_date
                from source.all_stock_snapshot
            ) s
            left join (
                select distinct trade_date
                from mart.universe_daily
            ) u
              on s.trade_date = u.trade_date
            where u.trade_date is null
            """
        ).fetchone()[0]

    def _validate_trading_date_coverage(
        self,
        *,
        connection: Any,
        start_date: Any,
        end_date: Any,
    ) -> MartValidationResult:
        missing_snapshot_rows = connection.execute(
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
        missing_universe_rows = connection.execute(
            """
            select trade_date
            from (
                select calendar_date as trade_date
                from source.trade_calendar
                where is_trading_day = 1
                  and calendar_date between ? and ?
                except
                select distinct trade_date
                from mart.universe_daily
                where trade_date between ? and ?
            )
            order by trade_date
            """,
            [start_date, end_date, start_date, end_date],
        ).fetchall()
        missing_snapshot_dates = [str(row[0]) for row in missing_snapshot_rows]
        missing_universe_dates = [str(row[0]) for row in missing_universe_rows]
        missing_count = len(missing_snapshot_dates) + len(missing_universe_dates)
        return MartValidationResult(
            rule_name="trading_date_coverage",
            severity="error",
            passed=missing_count == 0,
            sample_count=missing_count,
            detail={
                "start_date": str(start_date),
                "end_date": str(end_date),
                "missing_snapshot_dates": len(missing_snapshot_dates),
                "missing_snapshot_dates_sample": missing_snapshot_dates[:10],
                "missing_universe_dates": len(missing_universe_dates),
                "missing_universe_dates_sample": missing_universe_dates[:10],
            },
        )

    def _get_actual_max_date(self, connection: Any) -> str | None:
        row = connection.execute(
            "select max(trade_date) from mart.universe_daily"
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0])

BAR_1D_COLUMNS = [
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
    "turn",
    "tradestatus",
    "pct_chg",
    "pe_ttm",
    "pb_mrq",
    "ps_ttm",
    "pcf_ncf_ttm",
    "is_st",
    "adjust_factor_value",
]

BAR_5M_COLUMNS = [
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
    "adjust_factor_value",
]

BAR_AGG_DAILY_COLUMNS = [
    "trade_date",
    "trade_year",
    "code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adjustflag",
    "turn",
    "pct_chg",
]

BAR_AGG_INTRADAY_COLUMNS = [
    "trade_date",
    "trade_year",
    "code",
    "bar_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
]


MART_ADAPTER_REGISTRY: dict[str, MartAdapter] = {
    "universe_daily": UniverseDailyAdapter(),
    "bar_1d_qfq": MartViewAdapter(
        dataset_name="bar_1d_qfq",
        upstream_dataset_name="bar_1d_raw",
        expected_columns=BAR_1D_COLUMNS,
        priority=100,
    ),
    "bar_1d_hfq": MartViewAdapter(
        dataset_name="bar_1d_hfq",
        upstream_dataset_name="bar_1d_raw",
        expected_columns=BAR_1D_COLUMNS,
        priority=110,
    ),
    "bar_1w": MartViewAdapter(
        dataset_name="bar_1w",
        upstream_dataset_name="bar_1d_raw",
        expected_columns=BAR_AGG_DAILY_COLUMNS,
        priority=120,
    ),
    "bar_1m": MartViewAdapter(
        dataset_name="bar_1m",
        upstream_dataset_name="bar_1d_raw",
        expected_columns=BAR_AGG_DAILY_COLUMNS,
        priority=130,
    ),
    "bar_1y": MartViewAdapter(
        dataset_name="bar_1y",
        upstream_dataset_name="bar_1d_raw",
        expected_columns=BAR_AGG_DAILY_COLUMNS,
        priority=140,
    ),
    "bar_5m_qfq": MartViewAdapter(
        dataset_name="bar_5m_qfq",
        upstream_dataset_name="bar_5m_raw",
        expected_columns=BAR_5M_COLUMNS,
        priority=200,
    ),
    "bar_5m_hfq": MartViewAdapter(
        dataset_name="bar_5m_hfq",
        upstream_dataset_name="bar_5m_raw",
        expected_columns=BAR_5M_COLUMNS,
        priority=210,
    ),
    "bar_15m": MartViewAdapter(
        dataset_name="bar_15m",
        upstream_dataset_name="bar_5m_raw",
        expected_columns=BAR_AGG_INTRADAY_COLUMNS,
        priority=220,
    ),
    "bar_30m": MartViewAdapter(
        dataset_name="bar_30m",
        upstream_dataset_name="bar_5m_raw",
        expected_columns=BAR_AGG_INTRADAY_COLUMNS,
        priority=230,
    ),
    "bar_60m": MartViewAdapter(
        dataset_name="bar_60m",
        upstream_dataset_name="bar_5m_raw",
        expected_columns=BAR_AGG_INTRADAY_COLUMNS,
        priority=240,
    ),
}
