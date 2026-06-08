from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from app.services.baostock_client import BaoStockClient, BaoStockError, BaoStockResponse


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
    run_id: int | None = None
    repository: Any | None = None


@dataclass(frozen=True)
class AdapterChunk:
    dataset_name: str
    chunk_key: str
    scope: dict[str, Any]


@dataclass(frozen=True)
class SourceAdapterSpec:
    dataset_name: str
    endpoint: str
    help_docs: tuple[str, ...]
    implemented: bool
    note: str


class SourceAdapter(Protocol):
    spec: SourceAdapterSpec

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        ...

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
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

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        raise AdapterNotImplementedError(
            f"{self.spec.dataset_name} adapter is not implemented"
        )

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
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

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        end_date_value = runtime.today + timedelta(days=7)
        start_date_value = runtime.today - timedelta(days=14)
        current_watermark = parse_date(item.get("current_watermark"))
        if current_watermark is not None and current_watermark < end_date_value:
            start_date_value = min(start_date_value, current_watermark + timedelta(days=1))
        if runtime.repository is not None:
            calendar_min_date = (
                runtime.repository.get_dataset_actual_min_date(self.spec.dataset_name)
                or start_date_value
            )
            missing_dates = runtime.repository.get_missing_calendar_dates(
                start_date=calendar_min_date,
                end_date=end_date_value,
                limit=1,
            )
            if missing_dates:
                start_date_value = min(start_date_value, missing_dates[0])
        start_date = start_date_value.isoformat()
        end_date = end_date_value.isoformat()
        return [
            AdapterChunk(
                dataset_name=self.spec.dataset_name,
                chunk_key=f"{start_date}_{end_date}",
                scope={"start_date": start_date, "end_date": end_date},
            )
        ]

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        start_date = chunk.scope["start_date"]
        end_date = chunk.scope["end_date"]
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
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
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

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        return [
            AdapterChunk(
                dataset_name=self.spec.dataset_name,
                chunk_key="full_table",
                scope={"mode": "full_table", "date": runtime.today.isoformat()},
            )
        ]

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
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
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
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

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for all_stock_snapshot")
        if runtime.repository is None:
            raise ValueError("repository is required for all_stock_snapshot")
        start_date = runtime.repository.get_dataset_actual_min_date(self.spec.dataset_name)
        if start_date is None or start_date > runtime.latest_trading_day:
            start_date = runtime.latest_trading_day
        missing_days = runtime.repository.get_missing_snapshot_trading_days(
            start_date=start_date,
            end_date=runtime.latest_trading_day,
            dataset_name=self.spec.dataset_name,
        )
        chunks = [
            AdapterChunk(
                dataset_name=self.spec.dataset_name,
                chunk_key=day.isoformat(),
                scope={"trade_date": day.isoformat(), "repair_missing": True},
            )
            for day in sorted(set(missing_days))
        ]
        if runtime.latest_trading_day not in missing_days:
            day = runtime.latest_trading_day
            chunks.append(
                AdapterChunk(
                    dataset_name=self.spec.dataset_name,
                    chunk_key=day.isoformat(),
                    scope={"trade_date": day.isoformat()},
                )
            )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for all_stock_snapshot")

        day = chunk.scope["trade_date"]
        response = client.query_all_stock(day=day)
        raise_if_error(response)

        now = datetime.now()
        trade_date = parse_date(day)
        rows = [
            {
                "trade_date": trade_date,
                "code": empty_to_none(row.get("code")),
                "code_name": empty_to_none(row.get("code_name")),
                "updated_at": now,
            }
            for row in response.rows
        ]
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=day,
        )


class Bar1dRawAdapter:
    spec = SourceAdapterSpec(
        dataset_name="bar_1d_raw",
        endpoint="query_history_k_data_plus",
        help_docs=("data/help/获取历史A股K线数据.md", "data/help/估值指标(日频).md"),
        implemented=True,
        note="Daily unadjusted K-line chunks for equity/index/ETF assets.",
    )

    fields = (
        "date,code,open,high,low,close,preclose,volume,amount,adjustflag,"
        "turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
    )

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for bar_1d_raw")
        if runtime.repository is None:
            raise ValueError("repository is required for bar_1d_raw")

        asset_universe = self._resolve_asset_universe(item)
        end_date = runtime.latest_trading_day
        current_watermark = parse_date(item.get("current_watermark"))
        chunks = self._repair_chunks(
            item=item,
            runtime=runtime,
            current_watermark=current_watermark,
        )
        if current_watermark is not None and current_watermark >= end_date:
            return chunks

        for asset in asset_universe:
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            start_date = self._resolve_start_date(asset, current_watermark)
            chunk_end_date = self._resolve_end_date(asset, end_date)
            if start_date > chunk_end_date:
                continue
            scope = {
                "code": str(code),
                "start_date": start_date.isoformat(),
                "end_date": chunk_end_date.isoformat(),
            }
            chunks.append(
                AdapterChunk(
                    dataset_name=self.spec.dataset_name,
                    chunk_key=_stable_scope_key(scope),
                    scope=scope,
                )
            )
        return chunks

    def _repair_chunks(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        current_watermark: date | None,
    ) -> list[AdapterChunk]:
        if current_watermark is None or runtime.repository is None:
            return []
        issues = runtime.repository.get_daily_source_coverage_issues(
            dataset_name=self.spec.dataset_name,
            end_date=current_watermark,
        )
        repair_days = [item["trade_date"] for item in issues]
        if not repair_days:
            return []
        chunks = []
        for asset in self._resolve_asset_universe(item):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            ipo_date = parse_date(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = parse_date(asset.get("out_date"))
            eligible_days = [
                day
                for day in repair_days
                if day >= ipo_date and (out_date is None or day <= out_date)
            ]
            for chunk_start, chunk_end in _group_contiguous_dates(eligible_days):
                scope = {
                    "code": str(code),
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "repair_missing": True,
                }
                chunks.append(
                    AdapterChunk(
                        dataset_name=self.spec.dataset_name,
                        chunk_key=_stable_scope_key(scope),
                        scope=scope,
                    )
                )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError("run_id is required for bar_1d_raw")

        code = chunk.scope["code"]
        start_date_text = chunk.scope["start_date"]
        end_date_text = chunk.scope["end_date"]

        response = client.query_history_k_data_plus(
            code=code,
            fields=self.fields,
            start_date=start_date_text,
            end_date=end_date_text,
            frequency="d",
            adjustflag="3",
        )
        raise_if_error(response)

        now = datetime.now()
        rows = []
        for row in response.rows:
            trade_date = parse_date(row.get("date"))
            rows.append(
                {
                    "trade_date": trade_date,
                    "trade_year": None if trade_date is None else trade_date.year,
                    "code": empty_to_none(row.get("code")),
                    "open": parse_float(row.get("open")),
                    "high": parse_float(row.get("high")),
                    "low": parse_float(row.get("low")),
                    "close": parse_float(row.get("close")),
                    "preclose": parse_float(row.get("preclose")),
                    "volume": parse_int(row.get("volume")),
                    "amount": parse_float(row.get("amount")),
                    "adjustflag": parse_int(row.get("adjustflag")),
                    "turn": parse_float(row.get("turn")),
                    "tradestatus": parse_int(row.get("tradestatus")),
                    "pct_chg": parse_float(row.get("pctChg")),
                    "pe_ttm": parse_float(row.get("peTTM")),
                    "pb_mrq": parse_float(row.get("pbMRQ")),
                    "ps_ttm": parse_float(row.get("psTTM")),
                    "pcf_ncf_ttm": parse_float(row.get("pcfNcfTTM")),
                    "is_st": parse_int(row.get("isST")),
                    "ingest_run_id": runtime.run_id,
                    "loaded_at": now,
                }
            )

        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=end_date_text,
        )

    def fallback_chunks(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        failed_chunk: AdapterChunk,
    ) -> list[AdapterChunk]:
        start_date = parse_date(failed_chunk.scope.get("start_date"))
        end_date = parse_date(failed_chunk.scope.get("end_date"))
        code = empty_to_none(failed_chunk.scope.get("code"))
        if start_date is None or end_date is None or code is None:
            return []
        if start_date.year == end_date.year:
            return []

        chunks = []
        for year in range(start_date.year, end_date.year + 1):
            chunk_start = max(start_date, date(year, 1, 1))
            chunk_end = min(end_date, date(year, 12, 31))
            scope = {
                "code": str(code),
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
            }
            chunks.append(
                AdapterChunk(
                    dataset_name=self.spec.dataset_name,
                    chunk_key=_stable_scope_key(scope),
                    scope=scope,
                )
            )
        return chunks

    def _resolve_asset_universe(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        code = empty_to_none(item.get("code"))
        if code is not None:
            return [
                {
                    "code": str(code),
                    "ipo_date": item.get("start_date"),
                    "out_date": item.get("end_date"),
                }
            ]
        asset_universe = item.get("asset_universe")
        if not isinstance(asset_universe, list) or not asset_universe:
            raise ValueError("bar_1d_raw requires a non-empty asset_universe")
        return asset_universe

    def _resolve_start_date(
        self,
        asset: dict[str, Any],
        current_watermark: date | None,
    ) -> date:
        start_date = parse_date(asset.get("ipo_date")) or date(1990, 12, 19)
        if current_watermark is not None:
            start_date = max(start_date, current_watermark + timedelta(days=1))
        return start_date

    def _resolve_end_date(self, asset: dict[str, Any], latest_trading_day: date) -> date:
        out_date = parse_date(asset.get("out_date"))
        if out_date is None:
            return latest_trading_day
        return min(out_date, latest_trading_day)


class Bar5mRawAdapter:
    spec = SourceAdapterSpec(
        dataset_name="bar_5m_raw",
        endpoint="query_history_k_data_plus",
        help_docs=("data/help/获取历史A股K线数据.md",),
        implemented=True,
        note="5-minute unadjusted K-line chunks for equity/ETF assets.",
    )

    fields = "date,time,code,open,high,low,close,volume,amount,adjustflag"

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for bar_5m_raw")
        if runtime.repository is None:
            raise ValueError("repository is required for bar_5m_raw")

        end_date = runtime.latest_trading_day
        current_watermark = parse_date(item.get("current_watermark"))
        chunks = self._repair_chunks(
            item=item,
            runtime=runtime,
            current_watermark=current_watermark,
        )
        if current_watermark is not None and current_watermark >= end_date:
            return chunks

        window_start = max(_years_ago(end_date, 5), date(1990, 12, 19))
        if current_watermark is not None:
            window_start = max(window_start, current_watermark + timedelta(days=1))

        for asset in _resolve_asset_universe(item, "bar_5m_raw"):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            start_date = max(parse_date(asset.get("ipo_date")) or window_start, window_start)
            chunk_end_date = _resolve_asset_end_date(asset, end_date)
            for chunk_start, chunk_end in _split_year_windows(start_date, chunk_end_date):
                scope = {
                    "code": str(code),
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                }
                chunks.append(
                    AdapterChunk(
                        dataset_name=self.spec.dataset_name,
                        chunk_key=_stable_scope_key(scope),
                        scope=scope,
                    )
                )
        return chunks

    def _repair_chunks(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        current_watermark: date | None,
    ) -> list[AdapterChunk]:
        if current_watermark is None or runtime.repository is None:
            return []
        issues = runtime.repository.get_daily_source_coverage_issues(
            dataset_name=self.spec.dataset_name,
            end_date=current_watermark,
        )
        repair_days = [item["trade_date"] for item in issues]
        if not repair_days:
            return []
        chunks = []
        for asset in _resolve_asset_universe(item, "bar_5m_raw"):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            ipo_date = parse_date(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = parse_date(asset.get("out_date"))
            eligible_days = [
                day
                for day in repair_days
                if day >= ipo_date and (out_date is None or day <= out_date)
            ]
            for chunk_start, chunk_end in _group_contiguous_dates(eligible_days):
                scope = {
                    "code": str(code),
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "repair_missing": True,
                }
                chunks.append(
                    AdapterChunk(
                        dataset_name=self.spec.dataset_name,
                        chunk_key=_stable_scope_key(scope),
                        scope=scope,
                    )
                )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError("run_id is required for bar_5m_raw")

        response = client.query_history_k_data_plus(
            code=chunk.scope["code"],
            fields=self.fields,
            start_date=chunk.scope["start_date"],
            end_date=chunk.scope["end_date"],
            frequency="5",
            adjustflag="3",
        )
        raise_if_error(response)

        now = datetime.now()
        rows = []
        for row in response.rows:
            trade_date = parse_date(row.get("date"))
            time_raw = empty_to_none(row.get("time"))
            rows.append(
                {
                    "trade_date": trade_date,
                    "trade_year": None if trade_date is None else trade_date.year,
                    "code": empty_to_none(row.get("code")),
                    "time_raw": time_raw,
                    "bar_time": parse_baostock_bar_time(time_raw),
                    "open": parse_float(row.get("open")),
                    "high": parse_float(row.get("high")),
                    "low": parse_float(row.get("low")),
                    "close": parse_float(row.get("close")),
                    "volume": parse_int(row.get("volume")),
                    "amount": parse_float(row.get("amount")),
                    "adjustflag": parse_int(row.get("adjustflag")),
                    "ingest_run_id": runtime.run_id,
                    "loaded_at": now,
                }
            )

        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=_max_watermark(item.get("current_watermark"), chunk.scope["end_date"]),
        )

    def fallback_chunks(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        failed_chunk: AdapterChunk,
    ) -> list[AdapterChunk]:
        start_date = parse_date(failed_chunk.scope.get("start_date"))
        end_date = parse_date(failed_chunk.scope.get("end_date"))
        code = empty_to_none(failed_chunk.scope.get("code"))
        if start_date is None or end_date is None or code is None:
            return []
        if _quarter_key(start_date) == _quarter_key(end_date):
            return []
        chunks = []
        for chunk_start, chunk_end in _split_quarter_windows(start_date, end_date):
            scope = {
                "code": str(code),
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
            }
            chunks.append(
                AdapterChunk(
                    dataset_name=self.spec.dataset_name,
                    chunk_key=_stable_scope_key(scope),
                    scope=scope,
                )
            )
        return chunks


class AdjustFactorAdapter:
    spec = SourceAdapterSpec(
        dataset_name="adjust_factor",
        endpoint="query_adjust_factor",
        help_docs=("data/help/复权因子.md",),
        implemented=True,
        note="Adjust-factor chunks for equity/index/ETF assets with rolling lookback.",
    )

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for adjust_factor")
        end_date = runtime.latest_trading_day
        current_watermark = parse_date(item.get("current_watermark"))
        if current_watermark is not None and current_watermark >= end_date:
            window_start = current_watermark - timedelta(days=365)
        elif current_watermark is not None:
            window_start = current_watermark - timedelta(days=365)
        else:
            window_start = date(1990, 12, 19)

        chunks = []
        for asset in _resolve_asset_universe(item, "adjust_factor"):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            start_date = max(parse_date(asset.get("ipo_date")) or window_start, window_start)
            chunk_end_date = _resolve_asset_end_date(asset, end_date)
            if start_date > chunk_end_date:
                continue
            scope = {
                "code": str(code),
                "start_date": start_date.isoformat(),
                "end_date": chunk_end_date.isoformat(),
            }
            chunks.append(
                AdapterChunk(
                    dataset_name=self.spec.dataset_name,
                    chunk_key=_stable_scope_key(scope),
                    scope=scope,
                )
            )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError("run_id is required for adjust_factor")
        response = client.query_adjust_factor(
            code=chunk.scope["code"],
            start_date=chunk.scope["start_date"],
            end_date=chunk.scope["end_date"],
        )
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "code": empty_to_none(row.get("code")),
                "divid_operate_date": parse_date(row.get("dividOperateDate")),
                "fore_adjust_factor": parse_float(row.get("foreAdjustFactor")),
                "back_adjust_factor": parse_float(row.get("backAdjustFactor")),
                "adjust_factor": parse_float(row.get("adjustFactor")),
                "ingest_run_id": runtime.run_id,
                "loaded_at": now,
            }
            for row in response.rows
        ]
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=chunk.scope["end_date"],
        )


class DividendAdapter:
    spec = SourceAdapterSpec(
        dataset_name="dividend",
        endpoint="query_dividend_data",
        help_docs=("data/help/除权除息信息.md",),
        implemented=True,
        note="Dividend chunks for equity assets by code/year/year_type.",
    )

    year_types = ("report", "operate")
    lookback_years = 3

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for dividend")
        current_watermark = parse_date(item.get("current_watermark"))
        latest_year = runtime.latest_trading_day.year

        chunks = []
        for asset in _resolve_asset_universe(item, "dividend"):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            ipo_date = parse_date(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = parse_date(asset.get("out_date"))
            start_year = ipo_date.year
            if current_watermark is not None:
                start_year = max(start_year, current_watermark.year - self.lookback_years)
            end_year = latest_year if out_date is None else min(out_date.year, latest_year)
            if start_year > end_year:
                continue
            for year in range(start_year, end_year + 1):
                for year_type in self.year_types:
                    scope = {"code": str(code), "year": year, "year_type": year_type}
                    chunks.append(
                        AdapterChunk(
                            dataset_name=self.spec.dataset_name,
                            chunk_key=_stable_scope_key(scope),
                            scope=scope,
                        )
                    )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError("run_id is required for dividend")
        response = client.query_dividend_data(
            code=chunk.scope["code"],
            year=int(chunk.scope["year"]),
            year_type=chunk.scope["year_type"],
        )
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "code": empty_to_none(row.get("code")),
                "query_year": int(chunk.scope["year"]),
                "query_year_type": chunk.scope["year_type"],
                "divid_pre_notice_date": parse_date(row.get("dividPreNoticeDate")),
                "divid_agm_pum_date": parse_date(row.get("dividAgmPumDate")),
                "divid_plan_announce_date": parse_date(row.get("dividPlanAnnounceDate")),
                "divid_plan_date": parse_date(row.get("dividPlanDate")),
                "divid_regist_date": parse_date(row.get("dividRegistDate")),
                "divid_operate_date": parse_date(row.get("dividOperateDate")),
                "divid_pay_date": parse_date(row.get("dividPayDate")),
                "divid_stock_market_date": parse_date(row.get("dividStockMarketDate")),
                "divid_cash_ps_before_tax": parse_float(row.get("dividCashPsBeforeTax")),
                "divid_cash_ps_after_tax": parse_float_or_none(row.get("dividCashPsAfterTax")),
                "divid_stocks_ps": parse_float(row.get("dividStocksPs")),
                "divid_cash_stock": empty_to_none(row.get("dividCashStock")),
                "divid_reserve_to_stock_ps": parse_float(row.get("dividReserveToStockPs")),
                "ingest_run_id": runtime.run_id,
                "loaded_at": now,
            }
            for row in response.rows
        ]
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=_max_watermark(
                item.get("current_watermark"),
                runtime.latest_trading_day.isoformat() if runtime.latest_trading_day else None,
            ),
        )


@dataclass(frozen=True)
class QuarterlyFinancialDatasetConfig:
    dataset_name: str
    endpoint: str
    help_doc: str
    note: str
    field_map: tuple[tuple[str, str], ...]


class QuarterlyFinancialAdapter:
    lookback_quarters = 8

    def __init__(self, config: QuarterlyFinancialDatasetConfig) -> None:
        self.config = config
        self.spec = SourceAdapterSpec(
            dataset_name=config.dataset_name,
            endpoint=config.endpoint,
            help_docs=(config.help_doc,),
            implemented=True,
            note=config.note,
        )

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError(f"latest_trading_day is required for {self.spec.dataset_name}")

        latest_quarter_end = _latest_completed_quarter_end(runtime.latest_trading_day)
        current_watermark = parse_date(item.get("current_watermark"))
        if current_watermark is None:
            base_start = date(1990, 12, 31)
        else:
            base_start = min(
                _quarter_end_for_date(current_watermark),
                _shift_quarter_end(
                    latest_quarter_end,
                    -(self.lookback_quarters - 1),
                ),
            )

        chunks = []
        for asset in _resolve_asset_universe(item, self.spec.dataset_name):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            ipo_date = parse_date(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = parse_date(asset.get("out_date"))
            start_quarter_end = max(_quarter_end_for_date(ipo_date), base_start)
            end_quarter_end = latest_quarter_end
            if out_date is not None:
                end_quarter_end = min(end_quarter_end, _quarter_end_for_date(out_date))
            if start_quarter_end > end_quarter_end:
                continue
            for year, quarter in _iter_quarters(start_quarter_end, end_quarter_end):
                scope = {"code": str(code), "year": year, "quarter": quarter}
                chunks.append(
                    AdapterChunk(
                        dataset_name=self.spec.dataset_name,
                        chunk_key=_stable_scope_key(scope),
                        scope=scope,
                    )
                )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError(f"run_id is required for {self.spec.dataset_name}")

        year = int(chunk.scope["year"])
        quarter = int(chunk.scope["quarter"])
        response = getattr(client, self.config.endpoint)(
            code=chunk.scope["code"],
            year=year,
            quarter=quarter,
        )
        raise_if_error(response)

        now = datetime.now()
        rows = []
        for row in response.rows:
            stat_date = parse_date(row.get("statDate"))
            fiscal_year = derive_fiscal_year(stat_date)
            fiscal_quarter = derive_fiscal_quarter(stat_date)
            source_row = {
                "code": empty_to_none(row.get("code")),
                "pub_date": parse_date(row.get("pubDate")),
                "stat_date": stat_date,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
            }
            for source_field, baostock_field in self.config.field_map:
                source_row[source_field] = parse_float(row.get(baostock_field))
            source_row["ingest_run_id"] = runtime.run_id
            source_row["loaded_at"] = now
            rows.append(source_row)

        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=_quarter_end(year, quarter).isoformat(),
        )


@dataclass(frozen=True)
class AnnouncementDatasetConfig:
    dataset_name: str
    endpoint: str
    help_doc: str
    note: str
    pub_date_field: str
    stat_date_field: str
    update_date_field: str | None
    text_field_map: tuple[tuple[str, str], ...] = ()
    numeric_field_map: tuple[tuple[str, str], ...] = ()


class AnnouncementAdapter:
    lookback_years = 2

    def __init__(self, config: AnnouncementDatasetConfig) -> None:
        self.config = config
        self.spec = SourceAdapterSpec(
            dataset_name=config.dataset_name,
            endpoint=config.endpoint,
            help_docs=(config.help_doc,),
            implemented=True,
            note=config.note,
        )

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError(f"latest_trading_day is required for {self.spec.dataset_name}")

        current_watermark = parse_date(item.get("current_watermark"))
        if current_watermark is None:
            window_start = date(1990, 12, 19)
        else:
            window_start = _years_ago(current_watermark, self.lookback_years)
        window_end = runtime.latest_trading_day
        if window_start > window_end:
            return []

        chunks = []
        for asset in _resolve_asset_universe(item, self.spec.dataset_name):
            code = empty_to_none(asset.get("code"))
            if code is None:
                continue
            ipo_date = parse_date(asset.get("ipo_date")) or date(1990, 12, 19)
            out_date = parse_date(asset.get("out_date"))
            start_date = max(ipo_date, window_start)
            end_date = window_end if out_date is None else min(out_date, window_end)
            for chunk_start, chunk_end in _split_year_windows(start_date, end_date):
                scope = {
                    "code": str(code),
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                }
                chunks.append(
                    AdapterChunk(
                        dataset_name=self.spec.dataset_name,
                        chunk_key=_stable_scope_key(scope),
                        scope=scope,
                    )
                )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError(f"run_id is required for {self.spec.dataset_name}")

        response = getattr(client, self.config.endpoint)(
            code=chunk.scope["code"],
            start_date=chunk.scope["start_date"],
            end_date=chunk.scope["end_date"],
        )
        raise_if_error(response)

        now = datetime.now()
        rows = []
        for row in response.rows:
            stat_date = parse_date(row.get(self.config.stat_date_field))
            source_row = {
                "code": empty_to_none(row.get("code")),
                "pub_date": parse_date(row.get(self.config.pub_date_field)),
                "stat_date": stat_date,
                "fiscal_year": derive_fiscal_year(stat_date),
                "fiscal_quarter": derive_fiscal_quarter(stat_date),
            }
            if self.config.update_date_field is not None:
                source_row["performance_exp_update_date"] = parse_date(
                    row.get(self.config.update_date_field)
                )
            for source_field, baostock_field in self.config.text_field_map:
                source_row[source_field] = empty_to_none(row.get(baostock_field))
            for source_field, baostock_field in self.config.numeric_field_map:
                source_row[source_field] = parse_float(row.get(baostock_field))
            source_row["ingest_run_id"] = runtime.run_id
            source_row["loaded_at"] = now
            rows.append(source_row)

        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=_max_watermark(
                item.get("current_watermark"),
                chunk.scope["end_date"],
            ),
        )


@dataclass(frozen=True)
class MacroSmallTableConfig:
    dataset_name: str
    endpoint: str
    help_doc: str
    note: str
    start_date: str
    end_date_getter: str
    watermark_field: str
    date_field_map: tuple[tuple[str, str], ...] = ()
    int_field_map: tuple[tuple[str, str], ...] = ()
    numeric_field_map: tuple[tuple[str, str], ...] = ()
    derive_stat_date: str | None = None
    extra_params: dict[str, Any] | None = None


class MacroSmallTableAdapter:
    def __init__(self, config: MacroSmallTableConfig) -> None:
        self.config = config
        self.spec = SourceAdapterSpec(
            dataset_name=config.dataset_name,
            endpoint=config.endpoint,
            help_docs=(config.help_doc,),
            implemented=True,
            note=config.note,
        )

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        request_end_date = self._resolve_request_end_date(runtime)
        start_date, end_date = self._resolve_scope_dates(request_end_date)
        scope = {
            "request_start_date": self.config.start_date,
            "request_end_date": request_end_date,
            "start_date": start_date,
            "end_date": end_date,
        }
        return [
            AdapterChunk(
                dataset_name=self.spec.dataset_name,
                chunk_key=_stable_scope_key(scope),
                scope=scope,
            )
        ]

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        if runtime.run_id is None:
            raise ValueError(f"run_id is required for {self.spec.dataset_name}")

        params = {
            "start_date": chunk.scope["request_start_date"],
            "end_date": chunk.scope["request_end_date"],
        }
        if self.config.extra_params:
            params.update(self.config.extra_params)
        response = getattr(client, self.config.endpoint)(**params)
        raise_if_error(response)

        now = datetime.now()
        rows = []
        for row in response.rows:
            source_row: dict[str, Any] = {}
            for source_field, baostock_field in self.config.date_field_map:
                source_row[source_field] = parse_date(row.get(baostock_field))
            for source_field, baostock_field in self.config.int_field_map:
                source_row[source_field] = parse_int(row.get(baostock_field))
            for source_field, baostock_field in self.config.numeric_field_map:
                source_row[source_field] = parse_float(row.get(baostock_field))
            if self.config.derive_stat_date == "month":
                source_row["stat_date"] = derive_month_stat_date(
                    source_row.get("stat_year"),
                    source_row.get("stat_month"),
                )
            elif self.config.derive_stat_date == "year":
                source_row["stat_date"] = derive_year_stat_date(
                    source_row.get("stat_year"),
                )
            source_row["ingest_run_id"] = runtime.run_id
            source_row["loaded_at"] = now
            rows.append(source_row)

        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=_resolve_rows_watermark(
                rows,
                self.config.watermark_field,
                item.get("current_watermark"),
            ),
        )

    def _resolve_request_end_date(self, runtime: AdapterRuntime) -> str:
        if self.config.end_date_getter == "latest_trading_day":
            if runtime.latest_trading_day is None:
                raise ValueError(f"latest_trading_day is required for {self.spec.dataset_name}")
            return runtime.latest_trading_day.isoformat()
        if self.config.end_date_getter == "latest_year_month":
            target = runtime.latest_trading_day or runtime.today
            return f"{target.year}-{target.month:02d}"
        if self.config.end_date_getter == "latest_year":
            target = runtime.latest_trading_day or runtime.today
            return str(target.year)
        raise ValueError(f"unsupported end_date_getter: {self.config.end_date_getter}")

    def _resolve_scope_dates(self, request_end_date: str) -> tuple[str, str]:
        if self.config.end_date_getter == "latest_year_month":
            start_date = parse_year_month_date(self.config.start_date)
            end_date = parse_year_month_date(request_end_date)
            if start_date is None or end_date is None:
                raise ValueError(f"{self.spec.dataset_name} requires year-month dates")
            return start_date.isoformat(), _month_end(end_date).isoformat()
        if self.config.end_date_getter == "latest_year":
            start_year = parse_int(self.config.start_date)
            end_year = parse_int(request_end_date)
            if start_year is None or end_year is None:
                raise ValueError(f"{self.spec.dataset_name} requires year dates")
            return date(start_year, 12, 31).isoformat(), date(end_year, 12, 31).isoformat()
        return self.config.start_date, request_end_date


class IndustrySnapshotAdapter:
    spec = SourceAdapterSpec(
        dataset_name="industry_snapshot",
        endpoint="query_stock_industry",
        help_docs=("data/help/行业分类.md",),
        implemented=True,
        note="Single-date industry classification snapshot.",
    )

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for industry_snapshot")
        day = runtime.latest_trading_day.isoformat()
        return [
            AdapterChunk(
                dataset_name=self.spec.dataset_name,
                chunk_key=day,
                scope={"update_date": day},
            )
        ]

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        response = client.query_stock_industry(date=chunk.scope["update_date"])
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "update_date": parse_date(row.get("updateDate")),
                "code": empty_to_none(row.get("code")),
                "code_name": empty_to_none(row.get("code_name")),
                "industry": empty_to_none(row.get("industry")),
                "industry_classification": empty_to_none(
                    row.get("industryClassification")
                ),
                "updated_at": now,
            }
            for row in response.rows
        ]
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=chunk.scope["update_date"],
        )


class IndexMemberSnapshotAdapter:
    spec = SourceAdapterSpec(
        dataset_name="index_member_snapshot",
        endpoint="query_index_members",
        help_docs=(
            "data/help/上证50成分股.md",
            "data/help/沪深300成分股.md",
            "data/help/中证500成分股.md",
        ),
        implemented=True,
        note="Single-date index member snapshots for SZ50, HS300, and ZZ500.",
    )

    index_map = {
        "sh.000016": "上证50",
        "sh.000300": "沪深300",
        "sh.000905": "中证500",
    }

    def plan(
        self,
        *,
        item: dict[str, Any],
        runtime: AdapterRuntime,
    ) -> list[AdapterChunk]:
        if runtime.latest_trading_day is None:
            raise ValueError("latest_trading_day is required for index_member_snapshot")
        day = runtime.latest_trading_day.isoformat()
        chunks = []
        for index_code in self.index_map:
            scope = {"index_code": index_code, "update_date": day}
            chunks.append(
                AdapterChunk(
                    dataset_name=self.spec.dataset_name,
                    chunk_key=_stable_scope_key(scope),
                    scope=scope,
                )
            )
        return chunks

    def fetch(
        self,
        *,
        client: BaoStockClient,
        item: dict[str, Any],
        runtime: AdapterRuntime,
        chunk: AdapterChunk,
    ) -> AdapterResult:
        index_code = chunk.scope["index_code"]
        response = client.query_index_members(
            index_code=index_code,
            date=chunk.scope["update_date"],
        )
        raise_if_error(response)

        now = datetime.now()
        rows = [
            {
                "index_code": index_code,
                "index_name": self.index_map[index_code],
                "update_date": parse_date(row.get("updateDate")),
                "code": empty_to_none(row.get("code")),
                "code_name": empty_to_none(row.get("code_name")),
                "updated_at": now,
            }
            for row in response.rows
        ]
        return AdapterResult(
            dataset_name=chunk.dataset_name,
            chunk_key=chunk.chunk_key,
            scope=chunk.scope,
            rows=rows,
            watermark=chunk.scope["update_date"],
        )


def raise_if_error(response: BaoStockResponse) -> None:
    if response.error_code != "0":
        raise BaoStockError(
            f"{response.error_code} {response.error_msg}",
            error_code=response.error_code,
            error_msg=response.error_msg,
        )


def parse_date(value: Any) -> date | None:
    value = empty_to_none(value)
    if value is None:
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def parse_int(value: Any) -> int | None:
    value = empty_to_none(value)
    if value is None:
        return None
    return int(float(str(value)))


def parse_float(value: Any) -> float | None:
    value = empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in {"-", "—", "–", "－"}:
            return None
        value = value.replace("—", "-").replace("–", "-").replace("－", "-")
    return float(value)


def parse_float_or_none(value: Any) -> float | None:
    try:
        return parse_float(value)
    except ValueError:
        return None


def parse_baostock_bar_time(value: Any) -> datetime | None:
    value = empty_to_none(value)
    if value is None:
        return None
    text = str(value)
    if len(text) < 14:
        return None
    return datetime.strptime(text[:14], "%Y%m%d%H%M%S")


def parse_year_month_date(value: Any) -> date | None:
    value = empty_to_none(value)
    if value is None:
        return None
    return datetime.strptime(str(value), "%Y-%m").date()


def derive_fiscal_year(stat_date: date | None) -> int | None:
    if stat_date is None:
        return None
    return stat_date.year


def derive_fiscal_quarter(stat_date: date | None) -> int | None:
    if stat_date is None:
        return None
    return _quarter_key(stat_date)[1]


def derive_month_stat_date(stat_year: Any, stat_month: Any) -> date | None:
    if stat_year is None or stat_month is None:
        return None
    return date(int(stat_year), int(stat_month), 1)


def derive_year_stat_date(stat_year: Any) -> date | None:
    if stat_year is None:
        return None
    return date(int(stat_year), 12, 31)


def empty_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _stable_scope_key(scope: dict[str, Any]) -> str:
    parts = [f'"{key}":"{scope[key]}"' for key in sorted(scope)]
    return "{" + ",".join(parts) + "}"


def _max_watermark(*values: Any) -> str:
    dates = [parsed for value in values if (parsed := parse_date(value)) is not None]
    if not dates:
        raise ValueError("watermark candidate is required")
    return max(dates).isoformat()


def _resolve_rows_watermark(
    rows: list[dict[str, Any]],
    field_name: str,
    fallback: Any,
) -> str:
    values = [row.get(field_name) for row in rows]
    if fallback is not None:
        values.append(fallback)
    dates = [value for value in values if isinstance(value, date)]
    if dates:
        return max(dates).isoformat()
    return _max_watermark(*values)


def _resolve_asset_universe(item: dict[str, Any], dataset_name: str) -> list[dict[str, Any]]:
    code = empty_to_none(item.get("code"))
    if code is not None:
        return [
            {
                "code": str(code),
                "ipo_date": item.get("start_date"),
                "out_date": item.get("end_date"),
            }
        ]
    asset_universe = item.get("asset_universe")
    if not isinstance(asset_universe, list) or not asset_universe:
        raise ValueError(f"{dataset_name} requires a non-empty asset_universe")
    return asset_universe


def _resolve_asset_end_date(asset: dict[str, Any], latest_trading_day: date) -> date:
    out_date = parse_date(asset.get("out_date"))
    if out_date is None:
        return latest_trading_day
    return min(out_date, latest_trading_day)


def _years_ago(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def _split_year_windows(start_date: date, end_date: date) -> list[tuple[date, date]]:
    if start_date > end_date:
        return []
    windows = []
    for year in range(start_date.year, end_date.year + 1):
        windows.append(
            (
                max(start_date, date(year, 1, 1)),
                min(end_date, date(year, 12, 31)),
            )
        )
    return windows


def _group_contiguous_dates(days: list[date]) -> list[tuple[date, date]]:
    sorted_days = sorted(set(days))
    if not sorted_days:
        return []
    ranges = []
    start = sorted_days[0]
    previous = sorted_days[0]
    for day in sorted_days[1:]:
        if day == previous + timedelta(days=1):
            previous = day
            continue
        ranges.append((start, previous))
        start = day
        previous = day
    ranges.append((start, previous))
    return ranges


def _quarter_key(day: date) -> tuple[int, int]:
    return day.year, (day.month - 1) // 3 + 1


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _quarter_end_for_date(day: date) -> date:
    year, quarter = _quarter_key(day)
    return _quarter_end(year, quarter)


def _month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def _latest_completed_quarter_end(day: date) -> date:
    quarter_end = _quarter_end_for_date(day)
    if quarter_end <= day:
        return quarter_end
    year, quarter = _quarter_key(day)
    quarter -= 1
    if quarter == 0:
        year -= 1
        quarter = 4
    return _quarter_end(year, quarter)


def _shift_quarter_end(day: date, offset: int) -> date:
    year, quarter = _quarter_key(day)
    index = year * 4 + quarter - 1 + offset
    target_year = index // 4
    target_quarter = index % 4 + 1
    return _quarter_end(target_year, target_quarter)


def _iter_quarters(start_quarter_end: date, end_quarter_end: date) -> list[tuple[int, int]]:
    if start_quarter_end > end_quarter_end:
        return []
    year, quarter = _quarter_key(start_quarter_end)
    end_year, end_quarter = _quarter_key(end_quarter_end)
    quarters = []
    while (year, quarter) <= (end_year, end_quarter):
        quarters.append((year, quarter))
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return quarters


def _split_quarter_windows(start_date: date, end_date: date) -> list[tuple[date, date]]:
    if start_date > end_date:
        return []
    windows = []
    year, quarter = _quarter_key(start_date)
    while True:
        quarter_start = date(year, (quarter - 1) * 3 + 1, 1)
        quarter_end = _quarter_end(year, quarter)
        chunk_start = max(start_date, quarter_start)
        chunk_end = min(end_date, quarter_end)
        if chunk_start <= chunk_end:
            windows.append((chunk_start, chunk_end))
        if quarter_end >= end_date:
            break
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return windows


ADAPTER_REGISTRY: dict[str, SourceAdapter] = {
    "security_master": SecurityMasterAdapter(),
    "trade_calendar": TradeCalendarAdapter(),
    "all_stock_snapshot": AllStockSnapshotAdapter(),
    "bar_1d_raw": Bar1dRawAdapter(),
    "bar_5m_raw": Bar5mRawAdapter(),
    "adjust_factor": AdjustFactorAdapter(),
    "dividend": DividendAdapter(),
    "profit": QuarterlyFinancialAdapter(
        QuarterlyFinancialDatasetConfig(
            dataset_name="profit",
            endpoint="query_profit_data",
            help_doc="data/help/季频盈利能力.md",
            note="Quarterly profit chunks for equity assets by code/year/quarter.",
            field_map=(
                ("roe_avg", "roeAvg"),
                ("np_margin", "npMargin"),
                ("gp_margin", "gpMargin"),
                ("net_profit", "netProfit"),
                ("eps_ttm", "epsTTM"),
                ("mb_revenue", "MBRevenue"),
                ("total_share", "totalShare"),
                ("liqa_share", "liqaShare"),
            ),
        )
    ),
    "operation": QuarterlyFinancialAdapter(
        QuarterlyFinancialDatasetConfig(
            dataset_name="operation",
            endpoint="query_operation_data",
            help_doc="data/help/季频营运能力.md",
            note="Quarterly operation chunks for equity assets by code/year/quarter.",
            field_map=(
                ("nr_turn_ratio", "NRTurnRatio"),
                ("nr_turn_days", "NRTurnDays"),
                ("inv_turn_ratio", "INVTurnRatio"),
                ("inv_turn_days", "INVTurnDays"),
                ("ca_turn_ratio", "CATurnRatio"),
                ("asset_turn_ratio", "AssetTurnRatio"),
            ),
        )
    ),
    "growth": QuarterlyFinancialAdapter(
        QuarterlyFinancialDatasetConfig(
            dataset_name="growth",
            endpoint="query_growth_data",
            help_doc="data/help/季频成长能力.md",
            note="Quarterly growth chunks for equity assets by code/year/quarter.",
            field_map=(
                ("yoy_equity", "YOYEquity"),
                ("yoy_asset", "YOYAsset"),
                ("yoyni", "YOYNI"),
                ("yoyeps_basic", "YOYEPSBasic"),
                ("yoypni", "YOYPNI"),
            ),
        )
    ),
    "balance": QuarterlyFinancialAdapter(
        QuarterlyFinancialDatasetConfig(
            dataset_name="balance",
            endpoint="query_balance_data",
            help_doc="data/help/季频偿债能力.md",
            note="Quarterly balance chunks for equity assets by code/year/quarter.",
            field_map=(
                ("current_ratio", "currentRatio"),
                ("quick_ratio", "quickRatio"),
                ("cash_ratio", "cashRatio"),
                ("yoy_liability", "YOYLiability"),
                ("liability_to_asset", "liabilityToAsset"),
                ("asset_to_equity", "assetToEquity"),
            ),
        )
    ),
    "cash_flow": QuarterlyFinancialAdapter(
        QuarterlyFinancialDatasetConfig(
            dataset_name="cash_flow",
            endpoint="query_cash_flow_data",
            help_doc="data/help/季频现金流量.md",
            note="Quarterly cash-flow chunks for equity assets by code/year/quarter.",
            field_map=(
                ("ca_to_asset", "CAToAsset"),
                ("nca_to_asset", "NCAToAsset"),
                ("tangible_asset_to_asset", "tangibleAssetToAsset"),
                ("ebit_to_interest", "ebitToInterest"),
                ("cfo_to_or", "CFOToOR"),
                ("cfo_to_np", "CFOToNP"),
                ("cfo_to_gr", "CFOToGr"),
            ),
        )
    ),
    "dupont": QuarterlyFinancialAdapter(
        QuarterlyFinancialDatasetConfig(
            dataset_name="dupont",
            endpoint="query_dupont_data",
            help_doc="data/help/季频杜邦指数.md",
            note="Quarterly dupont chunks for equity assets by code/year/quarter.",
            field_map=(
                ("dupont_roe", "dupontROE"),
                ("dupont_asset_sto_equity", "dupontAssetStoEquity"),
                ("dupont_asset_turn", "dupontAssetTurn"),
                ("dupont_pnitoni", "dupontPnitoni"),
                ("dupont_nitogr", "dupontNitogr"),
                ("dupont_tax_burden", "dupontTaxBurden"),
                ("dupont_intburden", "dupontIntburden"),
                ("dupont_ebittogr", "dupontEbittogr"),
            ),
        )
    ),
    "performance_express": AnnouncementAdapter(
        AnnouncementDatasetConfig(
            dataset_name="performance_express",
            endpoint="query_performance_express_report",
            help_doc="data/help/季频公司业绩快报.md",
            note="Performance express chunks for equity assets by code/date window.",
            pub_date_field="performanceExpPubDate",
            stat_date_field="performanceExpStatDate",
            update_date_field="performanceExpUpdateDate",
            numeric_field_map=(
                ("performance_express_total_asset", "performanceExpressTotalAsset"),
                ("performance_express_net_asset", "performanceExpressNetAsset"),
                ("performance_express_eps_chg_pct", "performanceExpressEPSChgPct"),
                ("performance_express_roe_wa", "performanceExpressROEWa"),
                ("performance_express_eps_diluted", "performanceExpressEPSDiluted"),
                ("performance_express_gryoy", "performanceExpressGRYOY"),
                ("performance_express_opyoy", "performanceExpressOPYOY"),
            ),
        )
    ),
    "forecast": AnnouncementAdapter(
        AnnouncementDatasetConfig(
            dataset_name="forecast",
            endpoint="query_forecast_report",
            help_doc="data/help/季频公司业绩预告.md",
            note="Forecast chunks for equity assets by code/date window.",
            pub_date_field="profitForcastExpPubDate",
            stat_date_field="profitForcastExpStatDate",
            update_date_field=None,
            text_field_map=(
                ("profit_forcast_type", "profitForcastType"),
                ("profit_forcast_abstract", "profitForcastAbstract"),
            ),
            numeric_field_map=(
                ("profit_forcast_chg_pct_up", "profitForcastChgPctUp"),
                ("profit_forcast_chg_pct_dwn", "profitForcastChgPctDwn"),
            ),
        )
    ),
    "deposit_rate": MacroSmallTableAdapter(
        MacroSmallTableConfig(
            dataset_name="deposit_rate",
            endpoint="query_deposit_rate_data",
            help_doc="data/help/存款利率.md",
            note="Small full-table deposit rate refresh.",
            start_date="1990-01-01",
            end_date_getter="latest_trading_day",
            watermark_field="pub_date",
            date_field_map=(("pub_date", "pubDate"),),
            numeric_field_map=(
                ("demand_deposit_rate", "demandDepositRate"),
                ("fixed_deposit_rate3_month", "fixedDepositRate3Month"),
                ("fixed_deposit_rate6_month", "fixedDepositRate6Month"),
                ("fixed_deposit_rate1_year", "fixedDepositRate1Year"),
                ("fixed_deposit_rate2_year", "fixedDepositRate2Year"),
                ("fixed_deposit_rate3_year", "fixedDepositRate3Year"),
                ("fixed_deposit_rate5_year", "fixedDepositRate5Year"),
                ("installment_fixed_deposit_rate1_year", "installmentFixedDepositRate1Year"),
                ("installment_fixed_deposit_rate3_year", "installmentFixedDepositRate3Year"),
                ("installment_fixed_deposit_rate5_year", "installmentFixedDepositRate5Year"),
            ),
        )
    ),
    "loan_rate": MacroSmallTableAdapter(
        MacroSmallTableConfig(
            dataset_name="loan_rate",
            endpoint="query_loan_rate_data",
            help_doc="data/help/贷款利率.md",
            note="Small full-table loan rate refresh.",
            start_date="1990-01-01",
            end_date_getter="latest_trading_day",
            watermark_field="pub_date",
            date_field_map=(("pub_date", "pubDate"),),
            numeric_field_map=(
                ("loan_rate6_month", "loanRate6Month"),
                ("loan_rate6_month_to1_year", "loanRate6MonthTo1Year"),
                ("loan_rate1_year_to3_year", "loanRate1YearTo3Year"),
                ("loan_rate3_year_to5_year", "loanRate3YearTo5Year"),
                ("loan_rate_above5_year", "loanRateAbove5Year"),
                ("mortgate_rate_below5_year", "mortgateRateBelow5Year"),
                ("mortgate_rate_above5_year", "mortgateRateAbove5Year"),
            ),
        )
    ),
    "reserve_ratio": MacroSmallTableAdapter(
        MacroSmallTableConfig(
            dataset_name="reserve_ratio",
            endpoint="query_required_reserve_ratio_data",
            help_doc="data/help/存款准备金率.md",
            note="Small full-table reserve ratio refresh.",
            start_date="1990-01-01",
            end_date_getter="latest_trading_day",
            watermark_field="effective_date",
            date_field_map=(
                ("pub_date", "pubDate"),
                ("effective_date", "effectiveDate"),
            ),
            numeric_field_map=(
                ("big_institutions_ratio_pre", "bigInstitutionsRatioPre"),
                ("big_institutions_ratio_after", "bigInstitutionsRatioAfter"),
                ("medium_institutions_ratio_pre", "mediumInstitutionsRatioPre"),
                ("medium_institutions_ratio_after", "mediumInstitutionsRatioAfter"),
            ),
            extra_params={"year_type": "1"},
        )
    ),
    "money_supply_month": MacroSmallTableAdapter(
        MacroSmallTableConfig(
            dataset_name="money_supply_month",
            endpoint="query_money_supply_data_month",
            help_doc="data/help/货币供应量.md",
            note="Small full-table monthly money supply refresh.",
            start_date="1990-01",
            end_date_getter="latest_year_month",
            watermark_field="stat_date",
            int_field_map=(
                ("stat_year", "statYear"),
                ("stat_month", "statMonth"),
            ),
            numeric_field_map=(
                ("m0_month", "m0Month"),
                ("m0_yoy", "m0YOY"),
                ("m0_chain_relative", "m0ChainRelative"),
                ("m1_month", "m1Month"),
                ("m1_yoy", "m1YOY"),
                ("m1_chain_relative", "m1ChainRelative"),
                ("m2_month", "m2Month"),
                ("m2_yoy", "m2YOY"),
                ("m2_chain_relative", "m2ChainRelative"),
            ),
            derive_stat_date="month",
        )
    ),
    "money_supply_year": MacroSmallTableAdapter(
        MacroSmallTableConfig(
            dataset_name="money_supply_year",
            endpoint="query_money_supply_data_year",
            help_doc="data/help/货币供应量(年底余额).md",
            note="Small full-table yearly money supply refresh.",
            start_date="1990",
            end_date_getter="latest_year",
            watermark_field="stat_date",
            int_field_map=(("stat_year", "statYear"),),
            numeric_field_map=(
                ("m0_year", "m0Year"),
                ("m0_year_yoy", "m0YearYOY"),
                ("m1_year", "m1Year"),
                ("m1_year_yoy", "m1YearYOY"),
                ("m2_year", "m2Year"),
                ("m2_year_yoy", "m2YearYOY"),
            ),
            derive_stat_date="year",
        )
    ),
    "industry_snapshot": IndustrySnapshotAdapter(),
    "index_member_snapshot": IndexMemberSnapshotAdapter(),
}
