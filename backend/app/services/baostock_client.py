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
