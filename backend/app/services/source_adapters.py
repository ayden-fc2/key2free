from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from app.services.baostock_client import BaoStockClient, BaoStockResponse


@dataclass(frozen=True)
class AdapterResult:
    dataset_name: str
    chunk_key: str
    scope: dict[str, Any]
    rows: list[dict[str, Any]]
    watermark: str
    request_count: int = 1


@dataclass(frozen=True)
class AdapterRuntime:
    today: date
    latest_trading_day: date | None = None


@dataclass(frozen=True)
class SourceAdapterSpec:
    dataset_name: str
    endpoint: str
    help_docs: tuple[str, ...]
    implemented: bool
    note: str


class SourceAdapter(Protocol):
    spec: SourceAdapterSpec

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> AdapterResult:
        ...


class AdapterNotImplementedError(NotImplementedError):
    pass


class NotImplementedSourceAdapter:
    def __init__(
        self,
        *,
        dataset_name: str,
        endpoint: str,
        help_docs: tuple[str, ...],
        note: str,
    ) -> None:
        self.spec = SourceAdapterSpec(
            dataset_name=dataset_name,
            endpoint=endpoint,
            help_docs=help_docs,
            implemented=False,
            note=note,
        )

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> AdapterResult:
        raise AdapterNotImplementedError(
            f"{self.spec.dataset_name} adapter is not implemented"
        )


class TradeCalendarAdapter:
    spec = SourceAdapterSpec(
        dataset_name="trade_calendar",
        endpoint="query_trade_dates",
        help_docs=("BaoStock query_trade_dates API",),
        implemented=True,
        note="Maintains source.trade_calendar with a rolling lookback/lookahead window.",
    )

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> AdapterResult:
        start_date = (runtime.today - timedelta(days=14)).isoformat()
        end_date = (runtime.today + timedelta(days=7)).isoformat()
        response = client.query_trade_dates(start_date=start_date, end_date=end_date)
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "calendar_date": parse_date(row.get("calendar_date")),
                "is_trading_day": parse_int(row.get("is_trading_day")),
                "exchange": "CN",
                "updated_at": now,
            }
            for row in response.rows
        ]
        scope = {"start_date": start_date, "end_date": end_date}
        return AdapterResult(
            dataset_name=self.spec.dataset_name,
            chunk_key=f"{start_date}_{end_date}",
            scope=scope,
            rows=rows,
            watermark=end_date,
        )


class SecurityMasterAdapter:
    spec = SourceAdapterSpec(
        dataset_name="security_master",
        endpoint="query_stock_basic",
        help_docs=("data/help/证券基本资料.md",),
        implemented=True,
        note="Full-table security master refresh.",
    )

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> AdapterResult:
        response = client.query_stock_basic()
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "code": empty_to_none(row.get("code")),
                "code_name": empty_to_none(row.get("code_name")),
                "ipo_date": parse_date(row.get("ipoDate")),
                "out_date": parse_date(row.get("outDate")),
                "security_type": parse_int(row.get("type")),
                "list_status": parse_int(row.get("status")),
                "first_seen_date": runtime.today,
                "last_seen_date": runtime.today,
                "updated_at": now,
            }
            for row in response.rows
        ]
        scope = {"mode": "full_table", "date": runtime.today.isoformat()}
        return AdapterResult(
            dataset_name=self.spec.dataset_name,
            chunk_key="full_table",
            scope=scope,
            rows=rows,
            watermark=runtime.today.isoformat(),
        )


class AllStockSnapshotAdapter:
    spec = SourceAdapterSpec(
        dataset_name="all_stock_snapshot",
        endpoint="query_all_stock",
        help_docs=("BaoStock query_all_stock API",),
        implemented=True,
        note="Single-trading-day all-stock snapshot.",
    )

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> AdapterResult:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for all_stock_snapshot")

        day = runtime.latest_trading_day.isoformat()
        response = client.query_all_stock(day=day)
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "trade_date": runtime.latest_trading_day,
                "code": empty_to_none(row.get("code")),
                "code_name": empty_to_none(row.get("code_name")),
                "updated_at": now,
            }
            for row in response.rows
        ]
        scope = {"trade_date": day}
        return AdapterResult(
            dataset_name=self.spec.dataset_name,
            chunk_key=day,
            scope=scope,
            rows=rows,
            watermark=day,
        )


def raise_if_error(response: BaoStockResponse) -> None:
    if response.error_code != "0":
        from app.services.baostock_client import BaoStockError

        raise BaoStockError(f"{response.error_code} {response.error_msg}")


def parse_date(value: Any) -> date | None:
    value = empty_to_none(value)
    if value is None:
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def parse_int(value: Any) -> int | None:
    value = empty_to_none(value)
    if value is None:
        return None
    return int(value)


def empty_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


ADAPTER_REGISTRY: dict[str, SourceAdapter] = {
    "security_master": SecurityMasterAdapter(),
    "trade_calendar": TradeCalendarAdapter(),
    "all_stock_snapshot": AllStockSnapshotAdapter(),
    "bar_1d_raw": NotImplementedSourceAdapter(
        dataset_name="bar_1d_raw",
        endpoint="query_history_k_data_plus",
        help_docs=("data/help/获取历史A股K线数据.md", "data/help/估值指标(日频).md"),
        note="Daily raw K-line adapter pending.",
    ),
    "bar_5m_raw": NotImplementedSourceAdapter(
        dataset_name="bar_5m_raw",
        endpoint="query_history_k_data_plus",
        help_docs=("data/help/获取历史A股K线数据.md",),
        note="5-minute raw K-line adapter pending.",
    ),
    "adjust_factor": NotImplementedSourceAdapter(
        dataset_name="adjust_factor",
        endpoint="query_adjust_factor",
        help_docs=("data/help/复权因子.md",),
        note="Adjust factor adapter pending.",
    ),
    "dividend": NotImplementedSourceAdapter(
        dataset_name="dividend",
        endpoint="query_dividend_data",
        help_docs=("data/help/除权除息信息.md",),
        note="Dividend adapter pending.",
    ),
    "profit": NotImplementedSourceAdapter(
        dataset_name="profit",
        endpoint="query_profit_data",
        help_docs=("data/help/季频盈利能力.md",),
        note="Quarterly profit adapter pending.",
    ),
    "operation": NotImplementedSourceAdapter(
        dataset_name="operation",
        endpoint="query_operation_data",
        help_docs=("data/help/季频营运能力.md",),
        note="Quarterly operation adapter pending.",
    ),
    "growth": NotImplementedSourceAdapter(
        dataset_name="growth",
        endpoint="query_growth_data",
        help_docs=("data/help/季频成长能力.md",),
        note="Quarterly growth adapter pending.",
    ),
    "balance": NotImplementedSourceAdapter(
        dataset_name="balance",
        endpoint="query_balance_data",
        help_docs=("data/help/季频偿债能力.md",),
        note="Quarterly balance adapter pending.",
    ),
    "cash_flow": NotImplementedSourceAdapter(
        dataset_name="cash_flow",
        endpoint="query_cash_flow_data",
        help_docs=("data/help/季频现金流量.md",),
        note="Quarterly cash-flow adapter pending.",
    ),
    "dupont": NotImplementedSourceAdapter(
        dataset_name="dupont",
        endpoint="query_dupont_data",
        help_docs=("data/help/季频杜邦指数.md",),
        note="Quarterly dupont adapter pending.",
    ),
    "performance_express": NotImplementedSourceAdapter(
        dataset_name="performance_express",
        endpoint="query_performance_express_report",
        help_docs=("data/help/季频公司业绩快报.md",),
        note="Performance express adapter pending.",
    ),
    "forecast": NotImplementedSourceAdapter(
        dataset_name="forecast",
        endpoint="query_forecast_report",
        help_docs=("data/help/季频公司业绩预告.md",),
        note="Forecast adapter pending.",
    ),
    "deposit_rate": NotImplementedSourceAdapter(
        dataset_name="deposit_rate",
        endpoint="query_deposit_rate_data",
        help_docs=("data/help/存款利率.md",),
        note="Deposit rate adapter pending.",
    ),
    "loan_rate": NotImplementedSourceAdapter(
        dataset_name="loan_rate",
        endpoint="query_loan_rate_data",
        help_docs=("data/help/贷款利率.md",),
        note="Loan rate adapter pending.",
    ),
    "reserve_ratio": NotImplementedSourceAdapter(
        dataset_name="reserve_ratio",
        endpoint="query_required_reserve_ratio_data",
        help_docs=("data/help/存款准备金率.md",),
        note="Reserve ratio adapter pending.",
    ),
    "money_supply_month": NotImplementedSourceAdapter(
        dataset_name="money_supply_month",
        endpoint="query_money_supply_data_month",
        help_docs=("data/help/货币供应量.md",),
        note="Monthly money supply adapter pending.",
    ),
    "money_supply_year": NotImplementedSourceAdapter(
        dataset_name="money_supply_year",
        endpoint="query_money_supply_data_year",
        help_docs=("data/help/货币供应量(年底余额).md",),
        note="Yearly money supply adapter pending.",
    ),
    "industry_snapshot": NotImplementedSourceAdapter(
        dataset_name="industry_snapshot",
        endpoint="query_stock_industry",
        help_docs=("data/help/行业分类.md",),
        note="Industry snapshot adapter pending.",
    ),
    "index_member_snapshot": NotImplementedSourceAdapter(
        dataset_name="index_member_snapshot",
        endpoint="query_index_members",
        help_docs=(
            "data/help/上证50成分股.md",
            "data/help/沪深300成分股.md",
            "data/help/中证500成分股.md",
        ),
        note="Index member adapter pending; needs index-code dispatch.",
    ),
}
