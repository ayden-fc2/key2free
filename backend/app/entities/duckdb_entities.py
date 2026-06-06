from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar, Optional


# This file is generated from data/data.duckdb by an ad hoc schema sync.
# Keep entity table names aligned with the current DuckDB schema.

@dataclass(frozen=True)
class DimServiceSecurityCapability:
    schema_name: ClassVar[str] = "dim"
    table_name: ClassVar[str] = "service_security_capability"
    table_type: ClassVar[str] = "BASE TABLE"
    security_type: Optional[int] = None
    dataset_name: Optional[str] = None
    frequency: Optional[str] = None
    supported: Optional[int] = None
    supported_from: Optional[date] = None
    note: Optional[str] = None

@dataclass(frozen=True)
class DimSourcedataAllStockSnapshot:
    schema_name: ClassVar[str] = "dim"
    table_name: ClassVar[str] = "sourcedata_all_stock_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    trade_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class DimSourcedataIndexMemberSnapshot:
    schema_name: ClassVar[str] = "dim"
    table_name: ClassVar[str] = "sourcedata_index_member_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    index_code: Optional[str] = None
    index_name: Optional[str] = None
    update_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class DimSourcedataIndustrySnapshot:
    schema_name: ClassVar[str] = "dim"
    table_name: ClassVar[str] = "sourcedata_industry_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    update_date: Optional[date] = None
    code: Optional[str] = None
    code_name: Optional[str] = None
    industry: Optional[str] = None
    industry_classification: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class DimSourcedataSecurityMaster:
    schema_name: ClassVar[str] = "dim"
    table_name: ClassVar[str] = "sourcedata_security_master"
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
class DimSourcedataTradeCalendar:
    schema_name: ClassVar[str] = "dim"
    table_name: ClassVar[str] = "sourcedata_trade_calendar"
    table_type: ClassVar[str] = "BASE TABLE"
    calendar_date: Optional[date] = None
    is_trading_day: Optional[int] = None
    exchange: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class FactSourcedataAdjustFactor:
    schema_name: ClassVar[str] = "fact"
    table_name: ClassVar[str] = "sourcedata_adjust_factor"
    table_type: ClassVar[str] = "BASE TABLE"
    code: Optional[str] = None
    divid_operate_date: Optional[date] = None
    fore_adjust_factor: Optional[float] = None
    back_adjust_factor: Optional[float] = None
    adjust_factor: Optional[float] = None
    ingest_run_id: Optional[int] = None
    loaded_at: Optional[datetime] = None

@dataclass(frozen=True)
class FactSourcedataBar1dRaw:
    schema_name: ClassVar[str] = "fact"
    table_name: ClassVar[str] = "sourcedata_bar_1d_raw"
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
class FactSourcedataBar5mRaw:
    schema_name: ClassVar[str] = "fact"
    table_name: ClassVar[str] = "sourcedata_bar_5m_raw"
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
class FactSourcedataDividend:
    schema_name: ClassVar[str] = "fact"
    table_name: ClassVar[str] = "sourcedata_dividend"
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
class FinSourcedataBalance:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_balance"
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
class FinSourcedataCashFlow:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_cash_flow"
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
class FinSourcedataDupont:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_dupont"
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
class FinSourcedataForecast:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_forecast"
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
class FinSourcedataGrowth:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_growth"
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
class FinSourcedataOperation:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_operation"
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
class FinSourcedataPerformanceExpress:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_performance_express"
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
class FinSourcedataProfit:
    schema_name: ClassVar[str] = "fin"
    table_name: ClassVar[str] = "sourcedata_profit"
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
class MacroSourcedataDepositRate:
    schema_name: ClassVar[str] = "macro"
    table_name: ClassVar[str] = "sourcedata_deposit_rate"
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
class MacroSourcedataLoanRate:
    schema_name: ClassVar[str] = "macro"
    table_name: ClassVar[str] = "sourcedata_loan_rate"
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
class MacroSourcedataMoneySupplyMonth:
    schema_name: ClassVar[str] = "macro"
    table_name: ClassVar[str] = "sourcedata_money_supply_month"
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
class MacroSourcedataMoneySupplyYear:
    schema_name: ClassVar[str] = "macro"
    table_name: ClassVar[str] = "sourcedata_money_supply_year"
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
class MacroSourcedataReserveRatio:
    schema_name: ClassVar[str] = "macro"
    table_name: ClassVar[str] = "sourcedata_reserve_ratio"
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
class MainServiceMyTask:
    schema_name: ClassVar[str] = "main"
    table_name: ClassVar[str] = "service_my_task"
    table_type: ClassVar[str] = "BASE TABLE"
    id: int = None
    type: str = None
    logs: Optional[str] = None
    status: str = None

@dataclass(frozen=True)
class MartCalculatedBar15m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_15m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None

@dataclass(frozen=True)
class MartCalculatedBar1dHfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_1d_hfq"
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
class MartCalculatedBar1dQfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_1d_qfq"
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
class MartCalculatedBar1m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_1m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    pct_chg: Optional[float] = None

@dataclass(frozen=True)
class MartCalculatedBar1w:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_1w"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    pct_chg: Optional[float] = None

@dataclass(frozen=True)
class MartCalculatedBar1y:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_1y"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None
    adjustflag: Optional[int] = None
    turn: Optional[float] = None
    pct_chg: Optional[float] = None

@dataclass(frozen=True)
class MartCalculatedBar30m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_30m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None

@dataclass(frozen=True)
class MartCalculatedBar5mHfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_5m_hfq"
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
class MartCalculatedBar5mQfq:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_5m_qfq"
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
class MartCalculatedBar60m:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_bar_60m"
    table_type: ClassVar[str] = "VIEW"
    trade_date: Optional[date] = None
    trade_year: Optional[int] = None
    code: Optional[str] = None
    bar_time: Optional[datetime] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    amount: Optional[float] = None

@dataclass(frozen=True)
class MartCalculatedUniverseDaily:
    schema_name: ClassVar[str] = "mart"
    table_name: ClassVar[str] = "calculated_universe_daily"
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
class MetaServiceApiQuotaDaily:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_api_quota_daily"
    table_type: ClassVar[str] = "BASE TABLE"
    quota_date: date = None
    quota_channel: str = None
    request_count: Optional[int] = None
    retry_count: Optional[int] = None
    login_count: Optional[int] = None
    blacklisted: Optional[int] = None
    soft_stop_at: Optional[datetime] = None
    hard_stop_at: Optional[datetime] = None
    last_run_id: Optional[int] = None

@dataclass(frozen=True)
class MetaServiceChunkState:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_chunk_state"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: str = None
    chunk_key: str = None
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
class MetaServiceDatasetCatalog:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_dataset_catalog"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: str = None
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
class MetaServiceDatasetWatermark:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_dataset_watermark"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: str = None
    asset_scope: str = None
    watermark_value: Optional[str] = None
    repair_backfill_from: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass(frozen=True)
class MetaServiceRepairManifest:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_repair_manifest"
    table_type: ClassVar[str] = "BASE TABLE"
    repair_id: str = None
    dataset_name: Optional[str] = None
    scope_json: Optional[str] = None
    reason: Optional[str] = None
    source_doc_hash: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

@dataclass(frozen=True)
class MetaServiceRunLog:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_run_log"
    table_type: ClassVar[str] = "BASE TABLE"
    run_id: int = None
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
class MetaServiceSchemaSnapshot:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_schema_snapshot"
    table_type: ClassVar[str] = "BASE TABLE"
    dataset_name: Optional[str] = None
    endpoint: Optional[str] = None
    doc_file: Optional[str] = None
    doc_hash: Optional[str] = None
    fields_json: Optional[str] = None
    captured_at: Optional[datetime] = None

@dataclass(frozen=True)
class MetaServiceValidationResult:
    schema_name: ClassVar[str] = "meta"
    table_name: ClassVar[str] = "service_validation_result"
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

DUCKDB_ENTITIES: dict[str, type[Any]] = {
    f"{DimServiceSecurityCapability.schema_name}.{DimServiceSecurityCapability.table_name}": DimServiceSecurityCapability,
    f"{DimSourcedataAllStockSnapshot.schema_name}.{DimSourcedataAllStockSnapshot.table_name}": DimSourcedataAllStockSnapshot,
    f"{DimSourcedataIndexMemberSnapshot.schema_name}.{DimSourcedataIndexMemberSnapshot.table_name}": DimSourcedataIndexMemberSnapshot,
    f"{DimSourcedataIndustrySnapshot.schema_name}.{DimSourcedataIndustrySnapshot.table_name}": DimSourcedataIndustrySnapshot,
    f"{DimSourcedataSecurityMaster.schema_name}.{DimSourcedataSecurityMaster.table_name}": DimSourcedataSecurityMaster,
    f"{DimSourcedataTradeCalendar.schema_name}.{DimSourcedataTradeCalendar.table_name}": DimSourcedataTradeCalendar,
    f"{FactSourcedataAdjustFactor.schema_name}.{FactSourcedataAdjustFactor.table_name}": FactSourcedataAdjustFactor,
    f"{FactSourcedataBar1dRaw.schema_name}.{FactSourcedataBar1dRaw.table_name}": FactSourcedataBar1dRaw,
    f"{FactSourcedataBar5mRaw.schema_name}.{FactSourcedataBar5mRaw.table_name}": FactSourcedataBar5mRaw,
    f"{FactSourcedataDividend.schema_name}.{FactSourcedataDividend.table_name}": FactSourcedataDividend,
    f"{FinSourcedataBalance.schema_name}.{FinSourcedataBalance.table_name}": FinSourcedataBalance,
    f"{FinSourcedataCashFlow.schema_name}.{FinSourcedataCashFlow.table_name}": FinSourcedataCashFlow,
    f"{FinSourcedataDupont.schema_name}.{FinSourcedataDupont.table_name}": FinSourcedataDupont,
    f"{FinSourcedataForecast.schema_name}.{FinSourcedataForecast.table_name}": FinSourcedataForecast,
    f"{FinSourcedataGrowth.schema_name}.{FinSourcedataGrowth.table_name}": FinSourcedataGrowth,
    f"{FinSourcedataOperation.schema_name}.{FinSourcedataOperation.table_name}": FinSourcedataOperation,
    f"{FinSourcedataPerformanceExpress.schema_name}.{FinSourcedataPerformanceExpress.table_name}": FinSourcedataPerformanceExpress,
    f"{FinSourcedataProfit.schema_name}.{FinSourcedataProfit.table_name}": FinSourcedataProfit,
    f"{MacroSourcedataDepositRate.schema_name}.{MacroSourcedataDepositRate.table_name}": MacroSourcedataDepositRate,
    f"{MacroSourcedataLoanRate.schema_name}.{MacroSourcedataLoanRate.table_name}": MacroSourcedataLoanRate,
    f"{MacroSourcedataMoneySupplyMonth.schema_name}.{MacroSourcedataMoneySupplyMonth.table_name}": MacroSourcedataMoneySupplyMonth,
    f"{MacroSourcedataMoneySupplyYear.schema_name}.{MacroSourcedataMoneySupplyYear.table_name}": MacroSourcedataMoneySupplyYear,
    f"{MacroSourcedataReserveRatio.schema_name}.{MacroSourcedataReserveRatio.table_name}": MacroSourcedataReserveRatio,
    f"{MainServiceMyTask.schema_name}.{MainServiceMyTask.table_name}": MainServiceMyTask,
    f"{MartCalculatedBar15m.schema_name}.{MartCalculatedBar15m.table_name}": MartCalculatedBar15m,
    f"{MartCalculatedBar1dHfq.schema_name}.{MartCalculatedBar1dHfq.table_name}": MartCalculatedBar1dHfq,
    f"{MartCalculatedBar1dQfq.schema_name}.{MartCalculatedBar1dQfq.table_name}": MartCalculatedBar1dQfq,
    f"{MartCalculatedBar1m.schema_name}.{MartCalculatedBar1m.table_name}": MartCalculatedBar1m,
    f"{MartCalculatedBar1w.schema_name}.{MartCalculatedBar1w.table_name}": MartCalculatedBar1w,
    f"{MartCalculatedBar1y.schema_name}.{MartCalculatedBar1y.table_name}": MartCalculatedBar1y,
    f"{MartCalculatedBar30m.schema_name}.{MartCalculatedBar30m.table_name}": MartCalculatedBar30m,
    f"{MartCalculatedBar5mHfq.schema_name}.{MartCalculatedBar5mHfq.table_name}": MartCalculatedBar5mHfq,
    f"{MartCalculatedBar5mQfq.schema_name}.{MartCalculatedBar5mQfq.table_name}": MartCalculatedBar5mQfq,
    f"{MartCalculatedBar60m.schema_name}.{MartCalculatedBar60m.table_name}": MartCalculatedBar60m,
    f"{MartCalculatedUniverseDaily.schema_name}.{MartCalculatedUniverseDaily.table_name}": MartCalculatedUniverseDaily,
    f"{MetaServiceApiQuotaDaily.schema_name}.{MetaServiceApiQuotaDaily.table_name}": MetaServiceApiQuotaDaily,
    f"{MetaServiceChunkState.schema_name}.{MetaServiceChunkState.table_name}": MetaServiceChunkState,
    f"{MetaServiceDatasetCatalog.schema_name}.{MetaServiceDatasetCatalog.table_name}": MetaServiceDatasetCatalog,
    f"{MetaServiceDatasetWatermark.schema_name}.{MetaServiceDatasetWatermark.table_name}": MetaServiceDatasetWatermark,
    f"{MetaServiceRepairManifest.schema_name}.{MetaServiceRepairManifest.table_name}": MetaServiceRepairManifest,
    f"{MetaServiceRunLog.schema_name}.{MetaServiceRunLog.table_name}": MetaServiceRunLog,
    f"{MetaServiceSchemaSnapshot.schema_name}.{MetaServiceSchemaSnapshot.table_name}": MetaServiceSchemaSnapshot,
    f"{MetaServiceValidationResult.schema_name}.{MetaServiceValidationResult.table_name}": MetaServiceValidationResult,
}
