from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import os
from queue import Empty, Queue
import socket
from threading import Thread
from typing import Any, Iterator

import baostock as bs


@dataclass(frozen=True)
class BaoStockResponse:
    error_code: str
    error_msg: str
    fields: list[str]
    rows: list[dict[str, Any]]


class BaoStockError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        error_msg: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.error_msg = error_msg


class BaoStockTimeoutError(BaoStockError):
    def __init__(self, message: str, *, worker_thread: Thread) -> None:
        super().__init__(message)
        self.worker_thread = worker_thread


class BaoStockClient(AbstractContextManager["BaoStockClient"]):
    DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0

    def __enter__(self) -> "BaoStockClient":
        self.reconnect()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        bs.logout()

    def reconnect(self) -> None:
        try:
            bs.logout()
        except Exception:
            pass
        socket.setdefaulttimeout(self._request_timeout_seconds())
        login_result = self._run_with_timeout(bs.login)
        if login_result.error_code != "0":
            raise BaoStockError(
                f"BaoStock login failed: {login_result.error_code} {login_result.error_msg}",
                error_code=login_result.error_code,
                error_msg=login_result.error_msg,
            )

    def query_trade_dates(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_trade_dates,
            start_date=start_date,
            end_date=end_date,
        )

    def query_stock_basic(self) -> BaoStockResponse:
        return self._query_with_timeout(bs.query_stock_basic)

    def query_all_stock(self, *, day: str) -> BaoStockResponse:
        return self._query_with_timeout(bs.query_all_stock, day=day)

    def query_history_k_data_plus(
        self,
        *,
        code: str,
        fields: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjustflag: str = "3",
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_history_k_data_plus,
            code=code,
            fields=fields,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjustflag=adjustflag,
        )

    def query_adjust_factor(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_adjust_factor,
            code=code,
            start_date=start_date,
            end_date=end_date,
        )

    def query_dividend_data(
        self,
        *,
        code: str,
        year: int,
        year_type: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_dividend_data,
            code=code,
            year=year,
            yearType=year_type,
        )

    def query_profit_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_profit_data,
            code=code,
            year=year,
            quarter=quarter,
        )

    def query_operation_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_operation_data,
            code=code,
            year=year,
            quarter=quarter,
        )

    def query_growth_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_growth_data,
            code=code,
            year=year,
            quarter=quarter,
        )

    def query_balance_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_balance_data,
            code=code,
            year=year,
            quarter=quarter,
        )

    def query_cash_flow_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_cash_flow_data,
            code=code,
            year=year,
            quarter=quarter,
        )

    def query_dupont_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_dupont_data,
            code=code,
            year=year,
            quarter=quarter,
        )

    def query_performance_express_report(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_performance_express_report,
            code=code,
            start_date=start_date,
            end_date=end_date,
        )

    def query_forecast_report(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_forecast_report,
            code=code,
            start_date=start_date,
            end_date=end_date,
        )

    def query_deposit_rate_data(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_deposit_rate_data,
            start_date=start_date,
            end_date=end_date,
        )

    def query_loan_rate_data(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_loan_rate_data,
            start_date=start_date,
            end_date=end_date,
        )

    def query_required_reserve_ratio_data(
        self,
        *,
        start_date: str,
        end_date: str,
        year_type: str = "0",
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_required_reserve_ratio_data,
            start_date=start_date,
            end_date=end_date,
            yearType=year_type,
        )

    def query_money_supply_data_month(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_money_supply_data_month,
            start_date=start_date,
            end_date=end_date,
        )

    def query_money_supply_data_year(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        return self._query_with_timeout(
            bs.query_money_supply_data_year,
            start_date=start_date,
            end_date=end_date,
        )

    def query_stock_industry(
        self,
        *,
        date: str,
        code: str = "",
    ) -> BaoStockResponse:
        return self._query_with_timeout(bs.query_stock_industry, code=code, date=date)

    def query_index_members(
        self,
        *,
        index_code: str,
        date: str,
    ) -> BaoStockResponse:
        endpoint_map = {
            "sh.000016": bs.query_sz50_stocks,
            "sh.000300": bs.query_hs300_stocks,
            "sh.000905": bs.query_zz500_stocks,
        }
        endpoint = endpoint_map.get(index_code)
        if endpoint is None:
            raise BaoStockError(f"unsupported index_code: {index_code}")
        return self._query_with_timeout(endpoint, date=date)

    def _query_with_timeout(self, query_fn: Any, **kwargs: Any) -> BaoStockResponse:
        return self._run_with_timeout(lambda: self._collect_result(query_fn(**kwargs)))

    def _run_with_timeout(self, call: Any) -> Any:
        timeout_seconds = self._request_timeout_seconds()
        result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def target() -> None:
            try:
                result_queue.put((True, call()))
            except Exception as exc:
                result_queue.put((False, exc))

        thread = Thread(target=target, daemon=True)
        thread.start()
        try:
            succeeded, value = result_queue.get(timeout=timeout_seconds)
        except Empty as exc:
            raise BaoStockTimeoutError(
                f"BaoStock request timed out after {timeout_seconds:g}s",
                worker_thread=thread,
            ) from exc
        if succeeded:
            return value
        raise value

    def _request_timeout_seconds(self) -> float:
        raw_value = os.getenv("BAOSTOCK_REQUEST_TIMEOUT_SECONDS")
        if raw_value is None or raw_value.strip() == "":
            return self.DEFAULT_REQUEST_TIMEOUT_SECONDS
        try:
            return max(float(raw_value), 1.0)
        except ValueError:
            return self.DEFAULT_REQUEST_TIMEOUT_SECONDS

    def _collect_result(self, result: Any) -> BaoStockResponse:
        rows = []
        while result.error_code == "0" and result.next():
            rows.append(dict(zip(result.fields, result.get_row_data())))

        return BaoStockResponse(
            error_code=result.error_code,
            error_msg=result.error_msg,
            fields=list(result.fields),
            rows=rows,
        )


def baostock_session() -> Iterator[BaoStockClient]:
    with BaoStockClient() as client:
        yield client
