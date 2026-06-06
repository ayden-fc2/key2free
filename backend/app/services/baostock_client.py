from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Iterator

import baostock as bs


@dataclass(frozen=True)
class BaoStockResponse:
    error_code: str
    error_msg: str
    fields: list[str]
    rows: list[dict[str, Any]]


class BaoStockError(RuntimeError):
    pass


class BaoStockClient(AbstractContextManager["BaoStockClient"]):
    def __enter__(self) -> "BaoStockClient":
        login_result = bs.login()
        if login_result.error_code != "0":
            raise BaoStockError(
                f"BaoStock login failed: {login_result.error_code} {login_result.error_msg}"
            )
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        bs.logout()

    def query_trade_dates(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_trade_dates(start_date=start_date, end_date=end_date)
        return self._collect_result(result)

    def query_stock_basic(self) -> BaoStockResponse:
        result = bs.query_stock_basic()
        return self._collect_result(result)

    def query_all_stock(self, *, day: str) -> BaoStockResponse:
        result = bs.query_all_stock(day=day)
        return self._collect_result(result)

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
        result = bs.query_history_k_data_plus(
            code=code,
            fields=fields,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            adjustflag=adjustflag,
        )
        return self._collect_result(result)

    def query_adjust_factor(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_adjust_factor(
            code=code,
            start_date=start_date,
            end_date=end_date,
        )
        return self._collect_result(result)

    def query_dividend_data(
        self,
        *,
        code: str,
        year: int,
        year_type: str,
    ) -> BaoStockResponse:
        result = bs.query_dividend_data(
            code=code,
            year=year,
            yearType=year_type,
        )
        return self._collect_result(result)

    def query_profit_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        result = bs.query_profit_data(code=code, year=year, quarter=quarter)
        return self._collect_result(result)

    def query_operation_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        result = bs.query_operation_data(code=code, year=year, quarter=quarter)
        return self._collect_result(result)

    def query_growth_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        result = bs.query_growth_data(code=code, year=year, quarter=quarter)
        return self._collect_result(result)

    def query_balance_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        result = bs.query_balance_data(code=code, year=year, quarter=quarter)
        return self._collect_result(result)

    def query_cash_flow_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        result = bs.query_cash_flow_data(code=code, year=year, quarter=quarter)
        return self._collect_result(result)

    def query_dupont_data(
        self,
        *,
        code: str,
        year: int,
        quarter: int,
    ) -> BaoStockResponse:
        result = bs.query_dupont_data(code=code, year=year, quarter=quarter)
        return self._collect_result(result)

    def query_performance_express_report(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_performance_express_report(
            code=code,
            start_date=start_date,
            end_date=end_date,
        )
        return self._collect_result(result)

    def query_forecast_report(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_forecast_report(
            code=code,
            start_date=start_date,
            end_date=end_date,
        )
        return self._collect_result(result)

    def query_deposit_rate_data(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_deposit_rate_data(start_date=start_date, end_date=end_date)
        return self._collect_result(result)

    def query_loan_rate_data(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_loan_rate_data(start_date=start_date, end_date=end_date)
        return self._collect_result(result)

    def query_required_reserve_ratio_data(
        self,
        *,
        start_date: str,
        end_date: str,
        year_type: str = "0",
    ) -> BaoStockResponse:
        result = bs.query_required_reserve_ratio_data(
            start_date=start_date,
            end_date=end_date,
            yearType=year_type,
        )
        return self._collect_result(result)

    def query_money_supply_data_month(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_money_supply_data_month(
            start_date=start_date,
            end_date=end_date,
        )
        return self._collect_result(result)

    def query_money_supply_data_year(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> BaoStockResponse:
        result = bs.query_money_supply_data_year(
            start_date=start_date,
            end_date=end_date,
        )
        return self._collect_result(result)

    def query_stock_industry(
        self,
        *,
        date: str,
        code: str = "",
    ) -> BaoStockResponse:
        result = bs.query_stock_industry(code=code, date=date)
        return self._collect_result(result)

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
        result = endpoint(date=date)
        return self._collect_result(result)

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
