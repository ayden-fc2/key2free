from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import os
from typing import Any, Callable

import numpy as np
import pandas as pd

from app.repositories.duckdb_repository import DuckDBRepository


STOCK_DAILY_TECHNICAL_START_DATE = date(2017, 6, 1)
STOCK_DAILY_TECHNICAL_WARMUP_START_DATE = date(2016, 12, 6)
STOCK_DAILY_TECHNICAL_LOG_ROW_STEP = 100000
STOCK_DAILY_TECHNICAL_WORKERS = int(os.getenv("STOCK_DAILY_TECHNICAL_WORKERS", "4"))
STOCK_DAILY_TECHNICAL_BATCH_SIZE = int(os.getenv("STOCK_DAILY_TECHNICAL_BATCH_SIZE", "40"))
TUSHARE_ASSET_TABLE_NAMES = [
    "tushare.trade_cal",
    "tushare.bak_basic",
    "tushare.adj_factor",
    "tushare.daily",
    "tushare.daily_basic",
    "tushare.stk_mins_5min",
    "tushare.stock_daily_technical",
]


class TushareRepository:
    def __init__(self) -> None:
        self.duckdb = DuckDBRepository()

    def ensure_tables(self) -> None:
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute("create schema if not exists meta")
            connection.execute("create schema if not exists tushare")
            connection.execute(
                """
                create table if not exists meta.tushare_asset_watermark (
                    asset_table_name varchar primary key,
                    earliest_trusted_watermark date,
                    trusted_watermark date,
                    issue_count bigint not null default 0,
                    last_issue_at timestamp,
                    last_issue_scope varchar,
                    last_issue_message varchar,
                    issue_log varchar not null default ''
                )
                """
            )
            connection.execute("alter table meta.tushare_asset_watermark add column if not exists earliest_trusted_watermark date")
            connection.execute("alter table meta.tushare_asset_watermark add column if not exists issue_count bigint default 0")
            connection.execute("alter table meta.tushare_asset_watermark add column if not exists last_issue_at timestamp")
            connection.execute("alter table meta.tushare_asset_watermark add column if not exists last_issue_scope varchar")
            connection.execute("alter table meta.tushare_asset_watermark add column if not exists last_issue_message varchar")
            connection.execute("alter table meta.tushare_asset_watermark add column if not exists issue_log varchar default ''")
            connection.execute(
                """
                update meta.tushare_asset_watermark
                set issue_count = coalesce(issue_count, 0),
                    issue_log = coalesce(issue_log, '')
                """
            )
            connection.execute(
                """
                update meta.tushare_asset_watermark
                set earliest_trusted_watermark = case asset_table_name
                    when 'tushare.trade_cal' then coalesce(earliest_trusted_watermark, date '2014-01-02')
                    when 'tushare.adj_factor' then coalesce(earliest_trusted_watermark, date '2014-01-02')
                    when 'tushare.daily' then coalesce(earliest_trusted_watermark, date '2014-01-02')
                    when 'tushare.daily_basic' then
                        case
                            when earliest_trusted_watermark is null or earliest_trusted_watermark < date '2016-12-06'
                            then date '2016-12-06'
                            else earliest_trusted_watermark
                        end
                    when 'tushare.stk_mins_5min' then
                        case
                            when earliest_trusted_watermark is null or earliest_trusted_watermark < date '2016-12-06'
                            then date '2016-12-06'
                            else earliest_trusted_watermark
                        end
                    when 'tushare.bak_basic' then coalesce(earliest_trusted_watermark, date '2016-12-06')
                    when 'tushare.stock_daily_technical' then
                        case
                            when earliest_trusted_watermark is null or earliest_trusted_watermark > date '2017-06-01'
                            then date '2017-06-01'
                            else earliest_trusted_watermark
                        end
                    else earliest_trusted_watermark
                end
                """
            )
            connection.execute(
                """
                create table if not exists meta.tushare_refresh_task (
                    id bigint primary key,
                    status varchar not null,
                    started_at timestamp not null default current_timestamp,
                    updated_at timestamp not null default current_timestamp,
                    finished_at timestamp,
                    current_asset_table_name varchar,
                    current_watermark date,
                    logs varchar not null default ''
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.trade_cal (
                    exchange varchar,
                    cal_date date,
                    is_open smallint,
                    pretrade_date date
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.bak_basic (
                    trade_date date,
                    ts_code varchar,
                    name varchar,
                    industry varchar,
                    area varchar,
                    pe double,
                    float_share double,
                    total_share double,
                    total_assets double,
                    liquid_assets double,
                    fixed_assets double,
                    reserved double,
                    reserved_pershare double,
                    eps double,
                    bvps double,
                    pb double,
                    list_date date,
                    undp double,
                    per_undp double,
                    rev_yoy double,
                    profit_yoy double,
                    gpr double,
                    npr double,
                    holder_num bigint
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.adj_factor (
                    ts_code varchar,
                    trade_date date,
                    adj_factor double
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.daily (
                    ts_code varchar,
                    trade_date date,
                    open double,
                    high double,
                    low double,
                    close double,
                    pre_close double,
                    change double,
                    pct_chg double,
                    vol double,
                    amount double
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.daily_basic (
                    ts_code varchar,
                    trade_date date,
                    close double,
                    turnover_rate double,
                    turnover_rate_f double,
                    volume_ratio double,
                    pe double,
                    pe_ttm double,
                    pb double,
                    ps double,
                    ps_ttm double,
                    dv_ratio double,
                    dv_ttm double,
                    total_share double,
                    float_share double,
                    free_share double,
                    total_mv double,
                    circ_mv double
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.stk_mins_5min (
                    ts_code varchar,
                    trade_time timestamp,
                    trade_date date,
                    open double,
                    close double,
                    high double,
                    low double,
                    vol double,
                    amount double
                )
                """
            )
            connection.execute(
                """
                create table if not exists tushare.stock_daily_technical (
                    ts_code varchar,
                    code varchar,
                    trade_date date,
                    open double,
                    high double,
                    low double,
                    close double,
                    pre_close double,
                    change double,
                    pct_chg double,
                    vol double,
                    amount double,
                    adj_factor double,
                    latest_adj_factor double,
                    qfq_open double,
                    qfq_high double,
                    qfq_low double,
                    qfq_close double,
                    qfq_pre_close double,
                    min5_close double,
                    name varchar,
                    industry varchar,
                    area varchar,
                    pe double,
                    pe_ttm double,
                    ps double,
                    ps_ttm double,
                    pb double,
                    dv_ratio double,
                    dv_ttm double,
                    float_share double,
                    total_share double,
                    daily_basic_float_share double,
                    daily_basic_total_share double,
                    free_share double,
                    total_mv double,
                    circ_mv double,
                    turnover_rate double,
                    turnover_rate_f double,
                    daily_basic_volume_ratio double,
                    total_assets double,
                    liquid_assets double,
                    fixed_assets double,
                    reserved double,
                    reserved_pershare double,
                    eps double,
                    bvps double,
                    list_date date,
                    undp double,
                    per_undp double,
                    rev_yoy double,
                    profit_yoy double,
                    gpr double,
                    npr double,
                    holder_num bigint,
                    is_st smallint,
                    atr_5 double,
                    atr_14 double,
                    atr_30 double,
                    atr_pct_5 double,
                    atr_pct_14 double,
                    atr_pct_30 double,
                    avg_volume_5 double,
                    avg_volume_10 double,
                    avg_volume_20 double,
                    volume_ratio_5 double,
                    volume_ratio_10 double,
                    volume_ratio_20 double,
                    vwap_5 double,
                    vwap_14 double,
                    vwap_20 double,
                    vwap_30 double,
                    ma_5 double,
                    ma_10 double,
                    ma_20 double,
                    ma_30 double,
                    ma_60 double,
                    ma_120 double,
                    bias_5 double,
                    bias_10 double,
                    bias_20 double,
                    bias_30 double,
                    bias_60 double,
                    bias_120 double,
                    ma_slope_5 double,
                    ma_slope_10 double,
                    ma_slope_20 double,
                    ma_slope_30 double,
                    ma_slope_60 double,
                    ma_slope_120 double,
                    er_10 double,
                    er_20 double,
                    er_60 double,
                    boll_upper_10_2 double,
                    boll_middle_10_2 double,
                    boll_lower_10_2 double,
                    boll_bandwidth_10_2 double,
                    boll_percent_b_10_2 double,
                    boll_upper_20_2 double,
                    boll_middle_20_2 double,
                    boll_lower_20_2 double,
                    boll_bandwidth_20_2 double,
                    boll_percent_b_20_2 double,
                    boll_upper_60_2 double,
                    boll_middle_60_2 double,
                    boll_lower_60_2 double,
                    boll_bandwidth_60_2 double,
                    boll_percent_b_60_2 double,
                    macd_dif_12_26_9 double,
                    macd_dea_12_26_9 double,
                    macd_hist_12_26_9 double,
                    rsi_5 double,
                    rsi_14 double,
                    rsi_20 double,
                    roc_5 double,
                    roc_10 double,
                    roc_20 double,
                    roc_60 double,
                    roc_120 double,
                    kdj_k_9_3_3 double,
                    kdj_d_9_3_3 double,
                    kdj_j_9_3_3 double,
                    body_atr14_ratio double,
                    range_atr14_ratio double,
                    body_range_ratio double,
                    upper_shadow_range_ratio double,
                    lower_shadow_range_ratio double,
                    overnight_return double,
                    rebuilt_at timestamp not null default current_timestamp
                )
                """
            )
            for column_name in (
                "pe_ttm",
                "ps",
                "ps_ttm",
                "dv_ratio",
                "dv_ttm",
                "daily_basic_float_share",
                "daily_basic_total_share",
                "free_share",
                "total_mv",
                "circ_mv",
                "turnover_rate",
                "turnover_rate_f",
                "daily_basic_volume_ratio",
                "min5_close",
            ):
                connection.execute(
                    f"alter table tushare.stock_daily_technical add column if not exists {column_name} double"
                )

    def get_watermarks(self) -> list[dict[str, Any]]:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                with expected(asset_table_name) as (
                    select unnest(?)
                )
                select
                    expected.asset_table_name,
                    coalesce(
                        watermark.earliest_trusted_watermark,
                        case expected.asset_table_name
                            when 'tushare.trade_cal' then date '2014-01-02'
                            when 'tushare.adj_factor' then date '2014-01-02'
                            when 'tushare.daily' then date '2014-01-02'
                            when 'tushare.bak_basic' then date '2016-12-06'
                            when 'tushare.daily_basic' then date '2016-12-06'
                            when 'tushare.stk_mins_5min' then date '2016-12-06'
                            when 'tushare.stock_daily_technical' then date '2017-06-01'
                            else null
                        end
                    ) as earliest_trusted_watermark,
                    watermark.trusted_watermark,
                    coalesce(watermark.issue_count, 0) as issue_count,
                    watermark.last_issue_at,
                    watermark.last_issue_scope,
                    watermark.last_issue_message,
                    coalesce(watermark.issue_log, '') as issue_log
                from expected
                left join meta.tushare_asset_watermark watermark
                  on watermark.asset_table_name = expected.asset_table_name
                order by list_position(?, expected.asset_table_name)
                """
                ,
                [
                    TUSHARE_ASSET_TABLE_NAMES,
                    TUSHARE_ASSET_TABLE_NAMES,
                ],
            ).fetchall()
        return [
            {
                "asset_table_name": asset_table_name,
                "earliest_trusted_watermark": None
                if earliest_trusted_watermark is None
                else str(earliest_trusted_watermark),
                "trusted_watermark": None if trusted_watermark is None else str(trusted_watermark),
                "issue_count": int(issue_count or 0),
                "last_issue_at": None if last_issue_at is None else str(last_issue_at),
                "last_issue_scope": last_issue_scope,
                "last_issue_message": last_issue_message,
                "issue_log": issue_log or "",
            }
            for (
                asset_table_name,
                earliest_trusted_watermark,
                trusted_watermark,
                issue_count,
                last_issue_at,
                last_issue_scope,
                last_issue_message,
                issue_log,
            ) in rows
        ]

    def get_watermark(self, asset_table_name: str) -> date | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select trusted_watermark
                from meta.tushare_asset_watermark
                where asset_table_name = ?
                """,
                [asset_table_name],
            ).fetchone()
        return None if row is None else row[0]

    def update_watermark(
        self,
        asset_table_name: str,
        trusted_watermark: date,
        *,
        earliest_trusted_watermark: date | None = None,
        issue_scope: str | None = None,
        issue_message: str | None = None,
    ) -> None:
        self.ensure_tables()
        earliest_value = earliest_trusted_watermark or self._default_earliest_trusted_watermark(asset_table_name)
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                """
                insert into meta.tushare_asset_watermark(
                    asset_table_name, earliest_trusted_watermark, trusted_watermark
                )
                values (?, ?, ?)
                on conflict (asset_table_name) do update
                set trusted_watermark = excluded.trusted_watermark,
                    earliest_trusted_watermark = coalesce(
                        meta.tushare_asset_watermark.earliest_trusted_watermark,
                        excluded.earliest_trusted_watermark
                    )
                """,
                [asset_table_name, earliest_value, trusted_watermark],
            )
            if issue_message is not None:
                issue_line = self._format_watermark_issue(
                    trusted_watermark=trusted_watermark,
                    issue_scope=issue_scope,
                    issue_message=issue_message,
                )
                connection.execute(
                    """
                    update meta.tushare_asset_watermark
                    set issue_count = coalesce(issue_count, 0) + 1,
                        last_issue_at = current_timestamp,
                        last_issue_scope = ?,
                        last_issue_message = ?,
                        issue_log = coalesce(issue_log, '') || ?
                    where asset_table_name = ?
                    """,
                    [issue_scope, issue_message, issue_line, asset_table_name],
                )

    def resolve_watermark_issues(
        self,
        asset_table_name: str,
        *,
        message: str,
    ) -> None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            row = connection.execute(
                """
                select trusted_watermark
                from meta.tushare_asset_watermark
                where asset_table_name = ?
                """,
                [asset_table_name],
            ).fetchone()
            trusted_watermark = None if row is None else row[0]
            issue_line = self._format_watermark_issue(
                trusted_watermark=trusted_watermark or date.today(),
                issue_scope="resolved",
                issue_message=message,
            )
            connection.execute(
                """
                update meta.tushare_asset_watermark
                set issue_count = 0,
                    last_issue_at = null,
                    last_issue_scope = null,
                    last_issue_message = ?,
                    issue_log = coalesce(issue_log, '') || ?
                where asset_table_name = ?
                """,
                [message, issue_line, asset_table_name],
            )

    def upsert_trade_cal(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        rows = [
            [
                self._none_if_blank(item.get("exchange")),
                self._parse_yyyymmdd(item.get("cal_date")),
                self._none_or_int(item.get("is_open")),
                self._parse_yyyymmdd(item.get("pretrade_date")),
            ]
            for item in frame.to_dict("records")
        ]
        dates = [[row[1]] for row in rows if row[1] is not None]
        with self.duckdb.connect(read_only=False) as connection:
            if dates:
                connection.executemany("delete from tushare.trade_cal where cal_date = ?", dates)
            connection.executemany(
                """
                insert into tushare.trade_cal(exchange, cal_date, is_open, pretrade_date)
                values (?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def upsert_bak_basic(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        fields = [
            "trade_date",
            "ts_code",
            "name",
            "industry",
            "area",
            "pe",
            "float_share",
            "total_share",
            "total_assets",
            "liquid_assets",
            "fixed_assets",
            "reserved",
            "reserved_pershare",
            "eps",
            "bvps",
            "pb",
            "list_date",
            "undp",
            "per_undp",
            "rev_yoy",
            "profit_yoy",
            "gpr",
            "npr",
            "holder_num",
        ]
        rows = []
        trade_dates: set[date] = set()
        for item in frame.to_dict("records"):
            row = [self._none_if_blank(item.get(field)) for field in fields]
            row[0] = self._parse_yyyymmdd(row[0])
            row[16] = self._parse_yyyymmdd(row[16])
            for index in range(5, 16):
                row[index] = self._none_or_float(row[index])
            for index in range(17, 23):
                row[index] = self._none_or_float(row[index])
            row[23] = self._none_or_int(row[23])
            if row[0] is not None:
                trade_dates.add(row[0])
            rows.append(row)
        with self.duckdb.connect(read_only=False) as connection:
            if trade_dates:
                connection.executemany(
                    "delete from tushare.bak_basic where trade_date = ?",
                    [[day] for day in sorted(trade_dates)],
                )
            connection.executemany(
                """
                insert into tushare.bak_basic(
                    trade_date, ts_code, name, industry, area, pe, float_share,
                    total_share, total_assets, liquid_assets, fixed_assets, reserved,
                    reserved_pershare, eps, bvps, pb, list_date, undp, per_undp,
                    rev_yoy, profit_yoy, gpr, npr, holder_num
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def upsert_adj_factor(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        rows = [
            [
                item.get("ts_code"),
                self._parse_yyyymmdd(item.get("trade_date")),
                self._none_or_float(item.get("adj_factor")),
            ]
            for item in frame.to_dict("records")
        ]
        trade_dates = sorted({row[1] for row in rows if row[1] is not None})
        with self.duckdb.connect(read_only=False) as connection:
            if trade_dates:
                connection.executemany(
                    "delete from tushare.adj_factor where trade_date = ?",
                    [[day] for day in trade_dates],
                )
            connection.executemany(
                """
                insert into tushare.adj_factor(ts_code, trade_date, adj_factor)
                values (?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def upsert_daily(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        fields = [
            "ts_code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
        ]
        rows = []
        trade_dates: set[date] = set()
        for item in frame.to_dict("records"):
            row = [self._none_if_blank(item.get(field)) for field in fields]
            row[1] = self._parse_yyyymmdd(row[1])
            for index in range(2, len(row)):
                row[index] = self._none_or_float(row[index])
            if row[1] is not None:
                trade_dates.add(row[1])
            rows.append(row)
        with self.duckdb.connect(read_only=False) as connection:
            if trade_dates:
                connection.executemany(
                    "delete from tushare.daily where trade_date = ?",
                    [[day] for day in sorted(trade_dates)],
                )
            connection.executemany(
                """
                insert into tushare.daily(
                    ts_code, trade_date, open, high, low, close, pre_close,
                    change, pct_chg, vol, amount
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def upsert_daily_basic(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        fields = [
            "ts_code",
            "trade_date",
            "close",
            "turnover_rate",
            "turnover_rate_f",
            "volume_ratio",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
            "total_share",
            "float_share",
            "free_share",
            "total_mv",
            "circ_mv",
        ]
        rows = []
        trade_dates: set[date] = set()
        for item in frame.to_dict("records"):
            row = [self._none_if_blank(item.get(field)) for field in fields]
            row[1] = self._parse_yyyymmdd(row[1])
            for index in range(2, len(row)):
                row[index] = self._none_or_float(row[index])
            if row[1] is not None:
                trade_dates.add(row[1])
            rows.append(row)
        with self.duckdb.connect(read_only=False) as connection:
            if trade_dates:
                connection.executemany(
                    "delete from tushare.daily_basic where trade_date = ?",
                    [[day] for day in sorted(trade_dates)],
                )
            connection.executemany(
                """
                insert into tushare.daily_basic(
                    ts_code, trade_date, close, turnover_rate, turnover_rate_f,
                    volume_ratio, pe, pe_ttm, pb, ps, ps_ttm, dv_ratio,
                    dv_ttm, total_share, float_share, free_share, total_mv, circ_mv
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def upsert_stk_mins_5min(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        fields = [
            "ts_code",
            "trade_time",
            "open",
            "close",
            "high",
            "low",
            "vol",
            "amount",
        ]
        rows = []
        delete_keys: set[tuple[str, date]] = set()
        for item in frame.to_dict("records"):
            row = [self._none_if_blank(item.get(field)) for field in fields]
            trade_time = self._parse_datetime(row[1])
            trade_date = None if trade_time is None else trade_time.date()
            row[1] = trade_time
            for index in range(2, len(row)):
                row[index] = self._none_or_float(row[index])
            if row[0] is not None and trade_date is not None:
                delete_keys.add((str(row[0]), trade_date))
            rows.append([row[0], row[1], trade_date, *row[2:]])
        with self.duckdb.connect(read_only=False) as connection:
            if delete_keys:
                connection.executemany(
                    "delete from tushare.stk_mins_5min where ts_code = ? and trade_date = ?",
                    [[ts_code, trade_day] for ts_code, trade_day in sorted(delete_keys)],
                )
            connection.executemany(
                """
                insert into tushare.stk_mins_5min(
                    ts_code, trade_time, trade_date, open, close, high, low, vol, amount
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def get_min_watermark(self, asset_table_names: list[str]) -> date | None:
        self.ensure_tables()
        if not asset_table_names:
            return None
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select
                    min(trusted_watermark) as min_watermark,
                    count(*) as asset_count,
                    count(trusted_watermark) as ready_count
                from meta.tushare_asset_watermark
                where asset_table_name in (select unnest(?))
                """,
                [asset_table_names],
            ).fetchone()
        if row is None:
            return None
        min_watermark, asset_count, ready_count = row
        if asset_count != len(asset_table_names) or ready_count != len(asset_table_names):
            return None
        return min_watermark

    def rebuild_stock_daily_technical(
        self,
        *,
        target_watermark: date,
        include_min5_close: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> int:
        self.ensure_tables()
        columns = self._stock_daily_technical_columns()
        total_rows = 0
        staging_table = "tushare.stock_daily_technical_rebuild"
        with self.duckdb.connect(read_only=False) as connection:
            codes = [
                row[0]
                for row in connection.execute(
                    """
                    select distinct ts_code
                    from tushare.daily
                    where trade_date >= ?
                      and trade_date <= ?
                      and ts_code is not null
                    order by ts_code
                    """,
                    [STOCK_DAILY_TECHNICAL_START_DATE, target_watermark],
                ).fetchall()
                if row[0] is not None
            ]
            if not codes:
                return 0
            connection.execute(f"drop table if exists {staging_table}")
            connection.execute(
                f"""
                create table {staging_table} as
                select *
                from tushare.stock_daily_technical
                where 1 = 0
                """
            )
        batch_size = STOCK_DAILY_TECHNICAL_BATCH_SIZE
        next_log_rows = STOCK_DAILY_TECHNICAL_LOG_ROW_STEP
        try:
            for start in range(0, len(codes), batch_size):
                batch_codes = codes[start : start + batch_size]
                with self.duckdb.connect(read_only=False) as connection:
                    base_frame = self._load_stock_daily_technical_base(
                        connection=connection,
                        target_watermark=target_watermark,
                        ts_codes=batch_codes,
                        include_min5_close=include_min5_close,
                    )
                if base_frame.empty:
                    continue
                groups = [
                    frame.copy()
                    for _ts_code, frame in base_frame.groupby("ts_code", sort=True, group_keys=False)
                ]
                enriched_frames: list[pd.DataFrame] = []
                with ThreadPoolExecutor(max_workers=STOCK_DAILY_TECHNICAL_WORKERS) as executor:
                    futures = [
                        executor.submit(self._calculate_stock_daily_technical, frame)
                        for frame in groups
                    ]
                    for future in as_completed(futures):
                        frame = future.result()
                        if not frame.empty:
                            enriched_frames.append(frame)
                if not enriched_frames:
                    continue
                enriched = pd.concat(enriched_frames, ignore_index=True)
                enriched = enriched[enriched["trade_date"] >= pd.Timestamp(STOCK_DAILY_TECHNICAL_START_DATE)]
                if enriched.empty:
                    continue
                enriched = enriched[columns].replace({np.nan: None})
                with self.duckdb.connect(read_only=False) as connection:
                    connection.register("stock_daily_technical_rebuild_frame", enriched)
                    try:
                        connection.execute(
                            f"""
                            insert into {staging_table}({', '.join(columns)})
                            select {', '.join(columns)}
                            from stock_daily_technical_rebuild_frame
                            """
                        )
                    finally:
                        connection.unregister("stock_daily_technical_rebuild_frame")
                total_rows += len(enriched)
                if progress is not None and total_rows >= next_log_rows:
                    progress(
                        "tushare.stock_daily_technical rebuilt "
                        f"rows={total_rows} codes={min(start + batch_size, len(codes))}/{len(codes)}"
                    )
                    while next_log_rows <= total_rows:
                        next_log_rows += STOCK_DAILY_TECHNICAL_LOG_ROW_STEP
            if total_rows <= 0:
                return 0
            with self.duckdb.connect(read_only=False) as connection:
                connection.execute("delete from tushare.stock_daily_technical")
                connection.execute(
                    f"""
                    insert into tushare.stock_daily_technical({', '.join(columns)})
                    select {', '.join(columns)}
                    from {staging_table}
                    """
                )
                if progress is not None:
                    progress(f"tushare.stock_daily_technical replace completed rows={total_rows}")
        finally:
            with self.duckdb.connect(read_only=False) as connection:
                connection.execute(f"drop table if exists {staging_table}")
        return total_rows

    def get_open_trade_dates_after(self, trusted_watermark: date, end_date: date) -> list[date]:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select cal_date
                from tushare.trade_cal
                where is_open = 1
                  and cal_date > ?
                  and cal_date <= ?
                order by cal_date
                """,
                [trusted_watermark, end_date],
            ).fetchall()
        return [row[0] for row in rows if row[0] is not None]

    def get_daily_ts_codes(self, trade_day: date) -> list[str]:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            rows = connection.execute(
                """
                select distinct ts_code
                from tushare.daily
                where trade_date = ?
                  and ts_code is not null
                order by ts_code
                """,
                [trade_day],
            ).fetchall()
        return [str(row[0]) for row in rows if row[0] is not None]

    def get_stk_mins_5min_day_coverage(self, trade_day: date) -> dict[str, int]:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                with daily_codes as (
                    select distinct ts_code
                    from tushare.daily
                    where trade_date = ?
                      and ts_code is not null
                )
                select
                    (select count(*) from daily_codes) as expected_code_count,
                    count(distinct minutes.ts_code) as existing_code_count,
                    count(*) as existing_row_count
                from tushare.stk_mins_5min minutes
                join daily_codes daily
                  on daily.ts_code = minutes.ts_code
                where minutes.trade_date = ?
                """,
                [trade_day, trade_day],
            ).fetchone()
        if row is None:
            return {
                "expected_code_count": 0,
                "existing_code_count": 0,
                "existing_row_count": 0,
            }
        return {
            "expected_code_count": int(row[0] or 0),
            "existing_code_count": int(row[1] or 0),
            "existing_row_count": int(row[2] or 0),
        }

    def _load_stock_daily_technical_base(
        self,
        *,
        connection: Any,
        target_watermark: date,
        ts_codes: list[str],
        include_min5_close: bool,
    ) -> pd.DataFrame:
        min5_daily_close_cte = ""
        min5_close_select = "cast(null as double) as min5_close"
        min5_daily_close_join = ""
        parameters: list[Any] = [target_watermark]
        if include_min5_close:
            min5_daily_close_cte = """
            ,
            min5_daily_close as (
                select ts_code, trade_date, close as min5_close
                from (
                    select
                        ts_code,
                        trade_date,
                        close,
                        row_number() over (
                            partition by ts_code, trade_date
                            order by trade_time desc
                        ) as rn
                    from tushare.stk_mins_5min
                    where trade_date >= ?
                      and trade_date <= ?
                      and ts_code in (select unnest(?))
                ) ranked_min5
                where rn = 1
            )
            """
            min5_close_select = "min5_daily_close.min5_close"
            min5_daily_close_join = """
            left join min5_daily_close
              on min5_daily_close.ts_code = daily.ts_code
             and min5_daily_close.trade_date = daily.trade_date
            """
            parameters.extend([STOCK_DAILY_TECHNICAL_WARMUP_START_DATE, target_watermark, ts_codes])
        parameters.extend([STOCK_DAILY_TECHNICAL_WARMUP_START_DATE, target_watermark, ts_codes])
        result = connection.execute(
            f"""
            with latest_factor as (
                select ts_code, adj_factor as latest_adj_factor
                from (
                    select
                        ts_code,
                        adj_factor,
                        row_number() over (
                            partition by ts_code
                            order by trade_date desc
                        ) as rn
                    from tushare.adj_factor
                    where trade_date <= ?
                      and adj_factor is not null
                      and adj_factor > 0
                ) ranked
                where rn = 1
            )
            {min5_daily_close_cte}
            select
                daily.ts_code,
                lower(split_part(daily.ts_code, '.', 2)) || '.' || split_part(daily.ts_code, '.', 1) as code,
                daily.trade_date,
                daily.open,
                daily.high,
                daily.low,
                daily.close,
                daily.pre_close,
                daily.change,
                daily.pct_chg,
                daily.vol,
                daily.amount,
                factor.adj_factor,
                latest_factor.latest_adj_factor,
                daily.open * factor.adj_factor / latest_factor.latest_adj_factor as qfq_open,
                daily.high * factor.adj_factor / latest_factor.latest_adj_factor as qfq_high,
                daily.low * factor.adj_factor / latest_factor.latest_adj_factor as qfq_low,
                daily.close * factor.adj_factor / latest_factor.latest_adj_factor as qfq_close,
                daily.pre_close * factor.adj_factor / latest_factor.latest_adj_factor as qfq_pre_close,
                {min5_close_select},
                basic.name,
                basic.industry,
                basic.area,
                coalesce(daily_basic.pe, basic.pe) as pe,
                daily_basic.pe_ttm,
                daily_basic.ps,
                daily_basic.ps_ttm,
                coalesce(daily_basic.pb, basic.pb) as pb,
                daily_basic.dv_ratio,
                daily_basic.dv_ttm,
                basic.float_share,
                basic.total_share,
                daily_basic.float_share as daily_basic_float_share,
                daily_basic.total_share as daily_basic_total_share,
                daily_basic.free_share,
                daily_basic.total_mv,
                daily_basic.circ_mv,
                daily_basic.turnover_rate,
                daily_basic.turnover_rate_f,
                daily_basic.volume_ratio as daily_basic_volume_ratio,
                basic.total_assets,
                basic.liquid_assets,
                basic.fixed_assets,
                basic.reserved,
                basic.reserved_pershare,
                basic.eps,
                basic.bvps,
                basic.list_date,
                basic.undp,
                basic.per_undp,
                basic.rev_yoy,
                basic.profit_yoy,
                basic.gpr,
                basic.npr,
                basic.holder_num,
                case
                    when lower(coalesce(basic.name, '')) like '%st%' or coalesce(basic.name, '') like '*%' then 1
                    else 0
                end as is_st
            from tushare.daily daily
            join tushare.adj_factor factor
              on factor.ts_code = daily.ts_code
             and factor.trade_date = daily.trade_date
             and factor.adj_factor is not null
             and factor.adj_factor > 0
            join latest_factor
              on latest_factor.ts_code = daily.ts_code
            left join tushare.bak_basic basic
              on basic.ts_code = daily.ts_code
             and basic.trade_date = daily.trade_date
            left join tushare.daily_basic daily_basic
              on daily_basic.ts_code = daily.ts_code
             and daily_basic.trade_date = daily.trade_date
            {min5_daily_close_join}
            where daily.trade_date >= ?
              and daily.trade_date <= ?
              and daily.ts_code in (select unnest(?))
              and latest_factor.latest_adj_factor is not null
              and latest_factor.latest_adj_factor > 0
            order by daily.ts_code, daily.trade_date
            """,
            parameters,
        )
        return result.fetchdf()

    def _calculate_stock_daily_technical(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        close = frame["qfq_close"].astype(float)
        high = frame["qfq_high"].astype(float)
        low = frame["qfq_low"].astype(float)
        open_ = frame["qfq_open"].astype(float)
        pre_close = close.shift(1)
        volume = frame["vol"].astype(float)
        amount = frame["amount"].astype(float)

        true_range = pd.concat(
            [
                high - low,
                (high - pre_close).abs(),
                (low - pre_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        for window in (5, 14, 30):
            atr = true_range.rolling(window=window, min_periods=window).mean()
            frame[f"atr_{window}"] = atr
            frame[f"atr_pct_{window}"] = self._safe_divide_series(atr, close)

        for window in (5, 10, 20):
            avg_volume = volume.rolling(window=window, min_periods=window).mean()
            frame[f"avg_volume_{window}"] = avg_volume
            frame[f"volume_ratio_{window}"] = self._safe_divide_series(volume, avg_volume)

        # 成交额对复权不变，成交量按复权比例折算成前复权股数，使 VWAP 落在前复权价格量纲上
        adj_ratio = frame["adj_factor"].astype(float) / frame["latest_adj_factor"].astype(float)
        qfq_volume = self._safe_divide_series(volume, adj_ratio)
        for window in (5, 14, 20, 30):
            amount_sum = amount.rolling(window=window, min_periods=window).sum()
            qfq_volume_sum = qfq_volume.rolling(window=window, min_periods=window).sum()
            frame[f"vwap_{window}"] = self._safe_divide_series(amount_sum * 1000.0, qfq_volume_sum * 100.0)

        for window in (5, 10, 20, 30, 60, 120):
            ma = close.rolling(window=window, min_periods=window).mean()
            frame[f"ma_{window}"] = ma
            frame[f"bias_{window}"] = self._safe_divide_series(close - ma, ma)
            frame[f"ma_slope_{window}"] = self._safe_divide_series(ma, ma.shift(1)) - 1.0

        abs_change = close.diff().abs()
        for window in (10, 20, 60):
            direction = (close - close.shift(window)).abs()
            volatility = abs_change.rolling(window=window, min_periods=window).sum()
            frame[f"er_{window}"] = self._safe_divide_series(direction, volatility)

        for window in (10, 20, 60):
            middle = close.rolling(window=window, min_periods=window).mean()
            std = close.rolling(window=window, min_periods=window).std(ddof=0)
            upper = middle + 2.0 * std
            lower = middle - 2.0 * std
            frame[f"boll_upper_{window}_2"] = upper
            frame[f"boll_middle_{window}_2"] = middle
            frame[f"boll_lower_{window}_2"] = lower
            frame[f"boll_bandwidth_{window}_2"] = self._safe_divide_series(upper - lower, middle)
            frame[f"boll_percent_b_{window}_2"] = self._safe_divide_series(close - lower, upper - lower)

        ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
        ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False, min_periods=9).mean()
        frame["macd_dif_12_26_9"] = dif
        frame["macd_dea_12_26_9"] = dea
        frame["macd_hist_12_26_9"] = dif - dea

        close_diff = close.diff()
        gain = close_diff.clip(lower=0)
        loss = -close_diff.clip(upper=0)
        for window in (5, 14, 20):
            avg_gain = gain.rolling(window=window, min_periods=window).mean()
            avg_loss = loss.rolling(window=window, min_periods=window).mean()
            # 等价于 100 - 100/(1+RS)，且窗口内无下跌日时正确得到 100 而不是 NaN
            frame[f"rsi_{window}"] = 100.0 * self._safe_divide_series(avg_gain, avg_gain + avg_loss)

        for window in (5, 10, 20, 60, 120):
            frame[f"roc_{window}"] = self._safe_divide_series(close, close.shift(window)) - 1.0

        low_9 = low.rolling(window=9, min_periods=9).min()
        high_9 = high.rolling(window=9, min_periods=9).max()
        rsv = self._safe_divide_series(close - low_9, high_9 - low_9) * 100.0
        k = rsv.ewm(alpha=1 / 3, adjust=False, min_periods=3).mean()
        d = k.ewm(alpha=1 / 3, adjust=False, min_periods=3).mean()
        frame["kdj_k_9_3_3"] = k
        frame["kdj_d_9_3_3"] = d
        frame["kdj_j_9_3_3"] = 3.0 * k - 2.0 * d

        body = (close - open_).abs()
        total_range = high - low
        upper_shadow = high - pd.concat([open_, close], axis=1).max(axis=1)
        lower_shadow = pd.concat([open_, close], axis=1).min(axis=1) - low
        frame["body_atr14_ratio"] = self._safe_divide_series(body, frame["atr_14"])
        frame["range_atr14_ratio"] = self._safe_divide_series(total_range, frame["atr_14"])
        frame["body_range_ratio"] = self._safe_divide_series(body, total_range)
        frame["upper_shadow_range_ratio"] = self._safe_divide_series(upper_shadow, total_range)
        frame["lower_shadow_range_ratio"] = self._safe_divide_series(lower_shadow, total_range)
        frame["overnight_return"] = self._safe_divide_series(open_, pre_close) - 1.0
        return frame

    def create_refresh_task(self) -> int:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            task_id = connection.execute(
                """
                select coalesce(max(id), 0) + 1
                from meta.tushare_refresh_task
                """
            ).fetchone()[0]
            connection.execute(
                """
                insert into meta.tushare_refresh_task(id, status, logs)
                values (?, 'running', '')
                """,
                [task_id],
            )
        return int(task_id)

    def get_refresh_task(self, task_id: int | None = None) -> dict[str, Any] | None:
        self.ensure_tables()
        where_sql = "" if task_id is None else "where id = ?"
        params = [] if task_id is None else [task_id]
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                f"""
                select id, status, started_at, updated_at, finished_at,
                       current_asset_table_name, current_watermark, logs
                from meta.tushare_refresh_task
                {where_sql}
                order by id desc
                limit 1
                """,
                params,
            ).fetchone()
        return self._refresh_task_row_to_dict(row)

    def get_running_refresh_task(self) -> dict[str, Any] | None:
        self.ensure_tables()
        with self.duckdb.connect(read_only=True) as connection:
            row = connection.execute(
                """
                select id, status, started_at, updated_at, finished_at,
                       current_asset_table_name, current_watermark, logs
                from meta.tushare_refresh_task
                where status = 'running'
                order by id desc
                limit 1
                """
            ).fetchone()
        return self._refresh_task_row_to_dict(row)

    def update_refresh_task(
        self,
        *,
        task_id: int,
        status: str | None = None,
        current_asset_table_name: str | None = None,
        current_watermark: date | None = None,
        append_log: str | None = None,
        finished: bool = False,
    ) -> None:
        self.ensure_tables()
        assignments = ["updated_at = current_timestamp"]
        values: list[Any] = []
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
        if current_asset_table_name is not None:
            assignments.append("current_asset_table_name = ?")
            values.append(current_asset_table_name)
        if current_watermark is not None:
            assignments.append("current_watermark = ?")
            values.append(current_watermark)
        if append_log is not None:
            assignments.append("logs = coalesce(logs, '') || ?")
            values.append(append_log)
        if finished:
            assignments.append("finished_at = current_timestamp")
        values.append(task_id)
        with self.duckdb.connect(read_only=False) as connection:
            connection.execute(
                f"update meta.tushare_refresh_task set {', '.join(assignments)} where id = ?",
                values,
            )

    def finish_running_refresh_tasks(self, message: str) -> int:
        self.ensure_tables()
        with self.duckdb.connect(read_only=False) as connection:
            rows = connection.execute(
                """
                select id, logs
                from meta.tushare_refresh_task
                where status = 'running'
                order by id
                """
            ).fetchall()
            for task_id, logs in rows:
                connection.execute(
                    """
                    update meta.tushare_refresh_task
                    set status = 'error',
                        logs = ?,
                        finished_at = current_timestamp,
                        updated_at = current_timestamp
                    where id = ?
                    """,
                    [
                        (logs or "") + self._format_refresh_log(message),
                        task_id,
                    ],
                )
        return len(rows)

    def _refresh_task_row_to_dict(self, row: tuple[Any, ...] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "status": row[1],
            "started_at": None if row[2] is None else str(row[2]),
            "updated_at": None if row[3] is None else str(row[3]),
            "finished_at": None if row[4] is None else str(row[4]),
            "current_asset_table_name": row[5],
            "current_watermark": None if row[6] is None else str(row[6]),
            "logs": row[7] or "",
        }

    def _parse_yyyymmdd(self, value: Any) -> date | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return date.fromisoformat(text[:10])
        if len(text) != 8 or not text.isdigit():
            return None
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text)

    def _none_or_int(self, value: Any) -> int | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))

    def _none_or_float(self, value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        return float(text)

    def _none_if_blank(self, value: Any) -> Any:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def _safe_divide_series(self, numerator: pd.Series, denominator: pd.Series) -> pd.Series:
        denominator = denominator.replace(0, np.nan)
        result = numerator / denominator
        return result.replace([np.inf, -np.inf], np.nan)

    def _normalize_insert_value(self, value: Any) -> Any:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except TypeError:
            pass
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, np.generic):
            return value.item()
        return value

    def _stock_daily_technical_columns(self) -> list[str]:
        return [
            "ts_code",
            "code",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "change",
            "pct_chg",
            "vol",
            "amount",
            "adj_factor",
            "latest_adj_factor",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "qfq_pre_close",
            "min5_close",
            "name",
            "industry",
            "area",
            "pe",
            "pe_ttm",
            "ps",
            "ps_ttm",
            "pb",
            "dv_ratio",
            "dv_ttm",
            "float_share",
            "total_share",
            "daily_basic_float_share",
            "daily_basic_total_share",
            "free_share",
            "total_mv",
            "circ_mv",
            "turnover_rate",
            "turnover_rate_f",
            "daily_basic_volume_ratio",
            "total_assets",
            "liquid_assets",
            "fixed_assets",
            "reserved",
            "reserved_pershare",
            "eps",
            "bvps",
            "list_date",
            "undp",
            "per_undp",
            "rev_yoy",
            "profit_yoy",
            "gpr",
            "npr",
            "holder_num",
            "is_st",
            "atr_5",
            "atr_14",
            "atr_30",
            "atr_pct_5",
            "atr_pct_14",
            "atr_pct_30",
            "avg_volume_5",
            "avg_volume_10",
            "avg_volume_20",
            "volume_ratio_5",
            "volume_ratio_10",
            "volume_ratio_20",
            "vwap_5",
            "vwap_14",
            "vwap_20",
            "vwap_30",
            "ma_5",
            "ma_10",
            "ma_20",
            "ma_30",
            "ma_60",
            "ma_120",
            "bias_5",
            "bias_10",
            "bias_20",
            "bias_30",
            "bias_60",
            "bias_120",
            "ma_slope_5",
            "ma_slope_10",
            "ma_slope_20",
            "ma_slope_30",
            "ma_slope_60",
            "ma_slope_120",
            "er_10",
            "er_20",
            "er_60",
            "boll_upper_10_2",
            "boll_middle_10_2",
            "boll_lower_10_2",
            "boll_bandwidth_10_2",
            "boll_percent_b_10_2",
            "boll_upper_20_2",
            "boll_middle_20_2",
            "boll_lower_20_2",
            "boll_bandwidth_20_2",
            "boll_percent_b_20_2",
            "boll_upper_60_2",
            "boll_middle_60_2",
            "boll_lower_60_2",
            "boll_bandwidth_60_2",
            "boll_percent_b_60_2",
            "macd_dif_12_26_9",
            "macd_dea_12_26_9",
            "macd_hist_12_26_9",
            "rsi_5",
            "rsi_14",
            "rsi_20",
            "roc_5",
            "roc_10",
            "roc_20",
            "roc_60",
            "roc_120",
            "kdj_k_9_3_3",
            "kdj_d_9_3_3",
            "kdj_j_9_3_3",
            "body_atr14_ratio",
            "range_atr14_ratio",
            "body_range_ratio",
            "upper_shadow_range_ratio",
            "lower_shadow_range_ratio",
            "overnight_return",
        ]

    def _format_refresh_log(self, message: str) -> str:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] {message}\n"

    def _format_watermark_issue(
        self,
        *,
        trusted_watermark: date,
        issue_scope: str | None,
        issue_message: str,
    ) -> str:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scope = issue_scope or str(trusted_watermark)
        return f"[{timestamp}] watermark={trusted_watermark} scope={scope} issue={issue_message}\n"

    def _default_earliest_trusted_watermark(self, asset_table_name: str) -> date | None:
        if asset_table_name in {"tushare.trade_cal", "tushare.adj_factor", "tushare.daily"}:
            return date(2014, 1, 2)
        if asset_table_name in {"tushare.bak_basic", "tushare.daily_basic", "tushare.stk_mins_5min"}:
            return date(2016, 12, 6)
        if asset_table_name == "tushare.stock_daily_technical":
            return date(2017, 6, 1)
        return None

    def get_refresh_start_watermark(self, asset_table_name: str) -> date:
        trusted = self.get_watermark(asset_table_name)
        if trusted is not None:
            return trusted
        earliest = self._default_earliest_trusted_watermark(asset_table_name) or date(2014, 1, 2)
        return earliest - timedelta(days=1)
