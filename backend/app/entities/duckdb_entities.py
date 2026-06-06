from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Optional


# This file is generated from data/data.duckdb by an ad hoc schema sync.
# Keep entity table names aligned with the current DuckDB schema.

@dataclass(frozen=True)
class SourceAdjustFactor:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "adjust_factor"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    divid_operate_date: Optional[date] = None
    fore_adjust_factor: Optional[float] = None
    back_adjust_factor: Optional[float] = None
    adjust_factor: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceAllStockSnapshot:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "all_stock_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    trade_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceBalance:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "balance"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    cash_ratio: Optional[float] = None
    yoy_liability: Optional[float] = None
    liability_to_asset: Optional[float] = None
    asset_to_equity: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceBar1dRaw:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "bar_1d_raw"
    table_type: ClassVar[str] = "BASE TABLE"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    preclose: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    tradestatus: Optional[int] = None
    pct_chg: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb_mrq: Optional[float] = None
    ps_ttm: Optional[float] = None
    pcf_ncf_ttm: Optional[float] = None
    is_st: Optional[int] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceBar5mRaw:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "bar_5m_raw"
    table_type: ClassVar[str] = "BASE TABLE"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    time_raw: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceCashFlow:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "cash_flow"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    ca_to_asset: Optional[float] = None
    nca_to_asset: Optional[float] = None
    tangible_asset_to_asset: Optional[float] = None
    ebit_to_interest: Optional[float] = None
    cfo_to_or: Optional[float] = None
    cfo_to_np: Optional[float] = None
    cfo_to_gr: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceDepositRate:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "deposit_rate"
    table_type: ClassVar[str] = "BASE TABLE"
    pub_date: Optional[date] = None
    demand_deposit_rate: Optional[float] = None
    fixed_deposit_rate3_month: Optional[float] = None
    fixed_deposit_rate6_month: Optional[float] = None
    fixed_deposit_rate1_year: Optional[float] = None
    fixed_deposit_rate2_year: Optional[float] = None
    fixed_deposit_rate3_year: Optional[float] = None
    fixed_deposit_rate5_year: Optional[float] = None
    installment_fixed_deposit_rate1_year: Optional[float] = None
    installment_fixed_deposit_rate3_year: Optional[float] = None
    installment_fixed_deposit_rate5_year: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceDividend:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "dividend"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    query_year: Optional[int] = None
    query_year_type: Optional[str] = None
    divid_pre_notice_date: Optional[date] = None
    divid_agm_pum_date: Optional[date] = None
    divid_plan_announce_date: Optional[date] = None
    divid_plan_date: Optional[date] = None
    divid_regist_date: Optional[date] = None
    divid_operate_date: Optional[date] = None
    divid_pay_date: Optional[date] = None
    divid_stock_market_date: Optional[date] = None
    divid_cash_ps_before_tax: Optional[float] = None
    divid_cash_ps_after_tax: Optional[float] = None
    divid_stocks_ps: Optional[float] = None
    divid_cash_stock: Optional[str] = None
    divid_reserve_to_stock_ps: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceDupont:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "dupont"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    dupont_roe: Optional[float] = None
    dupont_asset_sto_equity: Optional[float] = None
    dupont_asset_turn: Optional[float] = None
    dupont_pnitoni: Optional[float] = None
    dupont_nitogr: Optional[float] = None
    dupont_tax_burden: Optional[float] = None
    dupont_intburden: Optional[float] = None
    dupont_ebittogr: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceForecast:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "forecast"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    profit_forcast_type: Optional[str] = None
    profit_forcast_abstract: Optional[str] = None
    profit_forcast_chg_pct_up: Optional[float] = None
    profit_forcast_chg_pct_dwn: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceGrowth:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "growth"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    yoy_equity: Optional[float] = None
    yoy_asset: Optional[float] = None
    yoyni: Optional[float] = None
    yoyeps_basic: Optional[float] = None
    yoypni: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceIndexMemberSnapshot:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "index_member_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    index_code: Optional[str] = None
    index_name: Optional[str] = None
    update_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceIndustrySnapshot:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "industry_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    update_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    industry: Optional[str] = None
    industry_classification: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceLoanRate:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "loan_rate"
    table_type: ClassVar[str] = "BASE TABLE"
    pub_date: Optional[date] = None
    loan_rate6_month: Optional[float] = None
    loan_rate6_month_to1_year: Optional[float] = None
    loan_rate1_year_to3_year: Optional[float] = None
    loan_rate3_year_to5_year: Optional[float] = None
    loan_rate_above5_year: Optional[float] = None
    mortgate_rate_below5_year: Optional[float] = None
    mortgate_rate_above5_year: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceMoneySupplyMonth:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "money_supply_month"
    table_type: ClassVar[str] = "BASE TABLE"
    stat_year: Optional[int] = None
    stat_month: Optional[int] = None
    m0_month: Optional[float] = None
    m0_yoy: Optional[float] = None
    m0_chain_relative: Optional[float] = None
    m1_month: Optional[float] = None
    m1_yoy: Optional[float] = None
    m1_chain_relative: Optional[float] = None
    m2_month: Optional[float] = None
    m2_yoy: Optional[float] = None
    m2_chain_relative: Optional[float] = None
    stat_date: Optional[date] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceMoneySupplyYear:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "money_supply_year"
    table_type: ClassVar[str] = "BASE TABLE"
    stat_year: Optional[int] = None
    m0_year: Optional[float] = None
    m0_year_yoy: Optional[float] = None
    m1_year: Optional[float] = None
    m1_year_yoy: Optional[float] = None
    m2_year: Optional[float] = None
    m2_year_yoy: Optional[float] = None
    stat_date: Optional[date] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceOperation:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "operation"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    nr_turn_ratio: Optional[float] = None
    nr_turn_days: Optional[float] = None
    inv_turn_ratio: Optional[float] = None
    inv_turn_days: Optional[float] = None
    ca_turn_ratio: Optional[float] = None
    asset_turn_ratio: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourcePerformanceExpress:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "performance_express"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    performance_exp_update_date: Optional[date] = None
    performance_express_total_asset: Optional[float] = None
    performance_express_net_asset: Optional[float] = None
    performance_express_eps_chg_pct: Optional[float] = None
    performance_express_roe_wa: Optional[float] = None
    performance_express_eps_diluted: Optional[float] = None
    performance_express_gryoy: Optional[float] = None
    performance_express_opyoy: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceProfit:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "profit"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    pub_date: Optional[date] = None
    stat_date: Optional[date] = None
    fiscal_year: Optional[int] = None
    fiscal_quarter: Optional[int] = None
    roe_avg: Optional[float] = None
    np_margin: Optional[float] = None
    gp_margin: Optional[float] = None
    net_profit: Optional[float] = None
    eps_ttm: Optional[float] = None
    mb_revenue: Optional[float] = None
    total_share: Optional[float] = None
    liqa_share: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceReserveRatio:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "reserve_ratio"
    table_type: ClassVar[str] = "BASE TABLE"
    pub_date: Optional[date] = None
    effective_date: Optional[date] = None
    big_institutions_ratio_pre: Optional[float] = None
    big_institutions_ratio_after: Optional[float] = None
    medium_institutions_ratio_pre: Optional[float] = None
    medium_institutions_ratio_after: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceSecurityMaster:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "security_master"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    code_name: Optional[str] = None
    ipo_date: Optional[date] = None
    out_date: Optional[date] = None
    security_type: Optional[int] = None
    list_status: Optional[int] = None
    first_seen_date: Optional[date] = None
    last_seen_date: Optional[date] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class SourceTradeCalendar:
    schema_name: ClassVar[str] = "source"
    table_name: ClassVar[str] = "trade_calendar"
    table_type: ClassVar[str] = "BASE TABLE"
    calendar_date: Optional[date] = None
    is_trading_day: Optional[int] = None
    exchange: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class MartBar15m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_15m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[Any] = None
    amount: Optional[float] = None

@dataclass(frozen=True)
class MartBar1dHfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_1d_hfq"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    preclose: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    turn: Optional[float] = None
    tradestatus: Optional[int] = None
    pct_chg: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb_mrq: Optional[float] = None
    ps_ttm: Optional[float] = None
    pcf_ncf_ttm: Optional[float] = None
    is_st: Optional[int] = None
    adjust_factor_value: Optional[float] = None

@dataclass(frozen=True)
class MartBar1dQfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_1d_qfq"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    preclose: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    turn: Optional[float] = None
    tradestatus: Optional[int] = None
    pct_chg: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb_mrq: Optional[float] = None
    ps_ttm: Optional[float] = None
    pcf_ncf_ttm: Optional[float] = None
    is_st: Optional[int] = None
    adjust_factor_value: Optional[float] = None

@dataclass(frozen=True)
class MartBar1m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_1m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[Any] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    pct_chg: Optional[float] = None

@dataclass(frozen=True)
class MartBar1w:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_1w"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[Any] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    pct_chg: Optional[float] = None

@dataclass(frozen=True)
class MartBar1y:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_1y"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[Any] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    pct_chg: Optional[float] = None

@dataclass(frozen=True)
class MartBar30m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_30m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[Any] = None
    amount: Optional[float] = None

@dataclass(frozen=True)
class MartBar5mHfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_5m_hfq"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    time_raw: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjust_factor_value: Optional[float] = None

@dataclass(frozen=True)
class MartBar5mQfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_5m_qfq"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    time_raw: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjust_factor_value: Optional[float] = None

@dataclass(frozen=True)
class MartBar60m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "bar_60m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[Any] = None
    amount: Optional[float] = None

@dataclass(frozen=True)
class MartUniverseDaily:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "universe_daily"
    table_type: ClassVar[str] = "BASE TABLE"
    trade_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    security_type: Optional[int] = None
    list_status: Optional[int] = None
    industry: Optional[str] = None
    industry_classification: Optional[str] = None
    is_sz50: Optional[int] = None
    is_hs300: Optional[int] = None
    is_zz500: Optional[int] = None

@dataclass(frozen=True)
class MetaApiQuotaDaily:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "api_quota_daily"
    table_type: ClassVar[str] = "BASE TABLE"
    quota_date: Optional[date] = None
    quota_channel: Optional[str] = None
    request_count: Optional[int] = None
    retry_count: Optional[int] = None
    login_count: Optional[int] = None
    blacklisted: Optional[int] = None
    soft_stop_at: Optional[datetime] = None
    hard_stop_at: Optional[datetime] = None
    last_run_id: Optional[int] = None

@dataclass(frozen=True)
class MetaChunkState:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "chunk_state"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: Optional[str] = None
    chunk_key: Optional[str] = None
    scope_json: Optional[str] = None
    status: Optional[str] = None
    attempts: Optional[int] = None
    lease_run_id: Optional[int] = None
    lease_expires_at: Optional[datetime] = None
    last_error_code: Optional[str] = None
    last_error_msg: Optional[str] = None
    row_count: Optional[int] = None
    checksum: Optional[str] = None
    last_success_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    lease_token: Optional[str] = None

@dataclass(frozen=True)
class MetaDatasetCatalog:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "dataset_catalog"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: Optional[str] = None
    endpoint: Optional[str] = None
    tier: Optional[str] = None
    enabled: Optional[int] = None
    asset_scope: Optional[str] = None
    chunk_strategy: Optional[str] = None
    replace_strategy: Optional[str] = None
    logical_key_json: Optional[str] = None
    expected_columns_json: Optional[str] = None
    duckdb_schema_json: Optional[str] = None
    validation_rules_json: Optional[str] = None
    priority: Optional[int] = None

@dataclass(frozen=True)
class MetaDatasetWatermark:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "dataset_watermark"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: Optional[str] = None
    asset_scope: Optional[str] = None
    watermark_value: Optional[str] = None
    repair_backfill_from: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class MetaMyTask:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "my_task"
    table_type: ClassVar[str] = "BASE TABLE"
    id: Optional[int] = None
    type: Optional[str] = None
    logs: Optional[str] = None
    status: Optional[str] = None

@dataclass(frozen=True)
class MetaRepairManifest:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "repair_manifest"
    table_type: ClassVar[str] = "BASE TABLE"
    repair_id: Optional[str] = None
    dataset_name: Optional[str] = None
    scope_json: Optional[str] = None
    reason: Optional[str] = None
    source_doc_hash: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

@dataclass(frozen=True)
class MetaRunLog:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "run_log"
    table_type: ClassVar[str] = "BASE TABLE"
    run_id: Optional[int] = None
    command: Optional[str] = None
    tier: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: Optional[str] = None
    exit_reason: Optional[str] = None
    request_count: Optional[int] = None
    retry_count: Optional[int] = None
    login_count: Optional[int] = None
    chunk_success: Optional[int] = None
    chunk_failed: Optional[int] = None
    blacklisted: Optional[int] = None
    error_summary: Optional[str] = None

@dataclass(frozen=True)
class MetaSchemaSnapshot:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "schema_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: Optional[str] = None
    endpoint: Optional[str] = None
    doc_file: Optional[str] = None
    doc_hash: Optional[str] = None
    fields_json: Optional[str] = None
    captured_at: Optional[datetime] = None

@dataclass(frozen=True)
class MetaSecurityCapability:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "security_capability"
    table_type: ClassVar[str] = "BASE TABLE"
    security_type: Optional[int] = None
    dataset_name: Optional[str] = None
    frequency: Optional[str] = None
    supported: Optional[int] = None
    supported_from: Optional[date] = None
    note: Optional[str] = None

@dataclass(frozen=True)
class MetaValidationResult:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "validation_result"
    table_type: ClassVar[str] = "BASE TABLE"
    run_id: Optional[int] = None
    dataset_name: Optional[str] = None
    scope_json: Optional[str] = None
    rule_name: Optional[str] = None
    severity: Optional[str] = None
    passed: Optional[int] = None
    sample_count: Optional[int] = None
    detail_json: Optional[str] = None
    created_at: Optional[datetime] = None

DUCKDB_ENTITY_REGISTRY: dict[str, type[Any]] = {
    f"{SourceAdjustFactor.schema_name}.{SourceAdjustFactor.table_name}": SourceAdjustFactor,
    f"{SourceAllStockSnapshot.schema_name}.{SourceAllStockSnapshot.table_name}": SourceAllStockSnapshot,
    f"{SourceBalance.schema_name}.{SourceBalance.table_name}": SourceBalance,
    f"{SourceBar1dRaw.schema_name}.{SourceBar1dRaw.table_name}": SourceBar1dRaw,
    f"{SourceBar5mRaw.schema_name}.{SourceBar5mRaw.table_name}": SourceBar5mRaw,
    f"{SourceCashFlow.schema_name}.{SourceCashFlow.table_name}": SourceCashFlow,
    f"{SourceDepositRate.schema_name}.{SourceDepositRate.table_name}": SourceDepositRate,
    f"{SourceDividend.schema_name}.{SourceDividend.table_name}": SourceDividend,
    f"{SourceDupont.schema_name}.{SourceDupont.table_name}": SourceDupont,
    f"{SourceForecast.schema_name}.{SourceForecast.table_name}": SourceForecast,
    f"{SourceGrowth.schema_name}.{SourceGrowth.table_name}": SourceGrowth,
    f"{SourceIndexMemberSnapshot.schema_name}.{SourceIndexMemberSnapshot.table_name}": SourceIndexMemberSnapshot,
    f"{SourceIndustrySnapshot.schema_name}.{SourceIndustrySnapshot.table_name}": SourceIndustrySnapshot,
    f"{SourceLoanRate.schema_name}.{SourceLoanRate.table_name}": SourceLoanRate,
    f"{SourceMoneySupplyMonth.schema_name}.{SourceMoneySupplyMonth.table_name}": SourceMoneySupplyMonth,
    f"{SourceMoneySupplyYear.schema_name}.{SourceMoneySupplyYear.table_name}": SourceMoneySupplyYear,
    f"{SourceOperation.schema_name}.{SourceOperation.table_name}": SourceOperation,
    f"{SourcePerformanceExpress.schema_name}.{SourcePerformanceExpress.table_name}": SourcePerformanceExpress,
    f"{SourceProfit.schema_name}.{SourceProfit.table_name}": SourceProfit,
    f"{SourceReserveRatio.schema_name}.{SourceReserveRatio.table_name}": SourceReserveRatio,
    f"{SourceSecurityMaster.schema_name}.{SourceSecurityMaster.table_name}": SourceSecurityMaster,
    f"{SourceTradeCalendar.schema_name}.{SourceTradeCalendar.table_name}": SourceTradeCalendar,
    f"{MartBar15m.schema_name}.{MartBar15m.table_name}": MartBar15m,
    f"{MartBar1dHfq.schema_name}.{MartBar1dHfq.table_name}": MartBar1dHfq,
    f"{MartBar1dQfq.schema_name}.{MartBar1dQfq.table_name}": MartBar1dQfq,
    f"{MartBar1m.schema_name}.{MartBar1m.table_name}": MartBar1m,
    f"{MartBar1w.schema_name}.{MartBar1w.table_name}": MartBar1w,
    f"{MartBar1y.schema_name}.{MartBar1y.table_name}": MartBar1y,
    f"{MartBar30m.schema_name}.{MartBar30m.table_name}": MartBar30m,
    f"{MartBar5mHfq.schema_name}.{MartBar5mHfq.table_name}": MartBar5mHfq,
    f"{MartBar5mQfq.schema_name}.{MartBar5mQfq.table_name}": MartBar5mQfq,
    f"{MartBar60m.schema_name}.{MartBar60m.table_name}": MartBar60m,
    f"{MartUniverseDaily.schema_name}.{MartUniverseDaily.table_name}": MartUniverseDaily,
    f"{MetaApiQuotaDaily.schema_name}.{MetaApiQuotaDaily.table_name}": MetaApiQuotaDaily,
    f"{MetaChunkState.schema_name}.{MetaChunkState.table_name}": MetaChunkState,
    f"{MetaDatasetCatalog.schema_name}.{MetaDatasetCatalog.table_name}": MetaDatasetCatalog,
    f"{MetaDatasetWatermark.schema_name}.{MetaDatasetWatermark.table_name}": MetaDatasetWatermark,
    f"{MetaMyTask.schema_name}.{MetaMyTask.table_name}": MetaMyTask,
    f"{MetaRepairManifest.schema_name}.{MetaRepairManifest.table_name}": MetaRepairManifest,
    f"{MetaRunLog.schema_name}.{MetaRunLog.table_name}": MetaRunLog,
    f"{MetaSchemaSnapshot.schema_name}.{MetaSchemaSnapshot.table_name}": MetaSchemaSnapshot,
    f"{MetaSecurityCapability.schema_name}.{MetaSecurityCapability.table_name}": MetaSecurityCapability,
    f"{MetaValidationResult.schema_name}.{MetaValidationResult.table_name}": MetaValidationResult,
}

DUCKDB_ENTITIES = DUCKDB_ENTITY_REGISTRY
