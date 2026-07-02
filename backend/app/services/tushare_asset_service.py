from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import baostock as bs
import pandas as pd

from app.repositories.tushare_repository import TushareRepository
from app.services.tushare_client import get_tushare_pro, reset_tushare_pro


RETRY_DELAYS_SECONDS = (10, 60, 180)
MAX_CALL_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1
STK_MINS_CALL_INTERVAL_SECONDS = float(os.getenv("TUSHARE_STK_MINS_CALL_INTERVAL_SECONDS", "0.2"))
TUSHARE_STK_MINS_MAX_ROWS = int(os.getenv("TUSHARE_STK_MINS_MAX_ROWS", "8000"))
BAOSTOCK_STK_MINS_MAX_ROWS = int(os.getenv("BAOSTOCK_STK_MINS_MAX_ROWS", "200000"))
RUNNING_TASK_STALE_AFTER_SECONDS = int(os.getenv("TUSHARE_RUNNING_TASK_STALE_AFTER_SECONDS", "1800"))


@dataclass(frozen=True)
class TushareRefreshStartResult:
    ok: bool
    task_id: int | None
    message: str


class TushareAssetService:
    _lock = threading.Lock()
    _thread: threading.Thread | None = None

    def __init__(self) -> None:
        self.repository = TushareRepository()
        self._baostock_logged_in = False

    def list_watermarks(self) -> list[dict[str, Any]]:
        return self.repository.get_watermarks()

    def get_refresh_task(self, task_id: int | None = None) -> dict[str, Any] | None:
        return self.repository.get_refresh_task(task_id)

    def finish_running_tasks(self, message: str) -> int:
        return self.repository.finish_running_refresh_tasks(message)

    def finish_stale_running_tasks(self, message: str) -> int:
        stale_task_ids = [
            task["id"]
            for task in self.repository.get_running_refresh_tasks()
            if self._is_stale_running_task(task)
        ]
        return self.repository.finish_refresh_tasks(stale_task_ids, message)

    def start_refresh(self, *, end_date: date, skip_stk_mins_5min: bool = False) -> TushareRefreshStartResult:
        self.repository.ensure_tables()
        self.finish_stale_running_tasks(
            "found a stale running Tushare refresh task and marked it as error.",
        )
        with self._lock:
            running = self.repository.get_running_refresh_task()
            if running is not None:
                return TushareRefreshStartResult(
                    ok=False,
                    task_id=running["id"],
                    message="tushare refresh task is already running",
                )
            task_id = self.repository.create_refresh_task(owner_pid=os.getpid())
            thread = threading.Thread(
                target=self._run_refresh_task,
                kwargs={
                    "task_id": task_id,
                    "end_date": end_date,
                    "skip_stk_mins_5min": skip_stk_mins_5min,
                },
                daemon=True,
            )
            self._thread = thread
            thread.start()
        return TushareRefreshStartResult(
            ok=True,
            task_id=task_id,
            message="tushare refresh task started",
        )

    def _run_refresh_task(self, *, task_id: int, end_date: date, skip_stk_mins_5min: bool = False) -> None:
        try:
            self._append_log(
                task_id,
                f"start Tushare asset refresh, end_date={end_date}, skip_stk_mins_5min={skip_stk_mins_5min}",
            )
            if not self._refresh_trade_cal(task_id=task_id, end_date=end_date):
                return
            if not self._refresh_index_basic(task_id=task_id):
                return
            if not self._refresh_index_daily(task_id=task_id, end_date=end_date):
                return
            if not self._refresh_index_dailybasic(task_id=task_id, end_date=end_date):
                return
            if not self._refresh_by_trade_dates(
                task_id=task_id,
                asset_table_name="tushare.bak_basic",
                fetcher=lambda day: get_tushare_pro().bak_basic(trade_date=self._format_tushare_date(day)),
                writer=self.repository.upsert_bak_basic,
                end_date=end_date,
            ):
                return
            if not self._refresh_by_trade_dates(
                task_id=task_id,
                asset_table_name="tushare.adj_factor",
                fetcher=lambda day: get_tushare_pro().adj_factor(trade_date=self._format_tushare_date(day)),
                writer=self.repository.upsert_adj_factor,
                end_date=end_date,
            ):
                return
            if not self._refresh_by_trade_dates(
                task_id=task_id,
                asset_table_name="tushare.daily",
                fetcher=lambda day: get_tushare_pro().daily(trade_date=self._format_tushare_date(day)),
                writer=self.repository.upsert_daily,
                end_date=end_date,
            ):
                return
            if skip_stk_mins_5min:
                self._append_log(task_id, "tushare.stk_mins_5min skipped by request")
            else:
                if not self._refresh_stk_mins_5min(task_id=task_id, end_date=end_date):
                    return
            daily_basic_fields = (
                "ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,"
                "pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,"
                "free_share,total_mv,circ_mv"
            )
            if not self._refresh_by_trade_dates(
                task_id=task_id,
                asset_table_name="tushare.daily_basic",
                fetcher=lambda day: get_tushare_pro().daily_basic(
                    ts_code="",
                    trade_date=self._format_tushare_date(day),
                    fields=daily_basic_fields,
                ),
                writer=self.repository.upsert_daily_basic,
                end_date=end_date,
            ):
                return
            if not self._refresh_stock_daily_technical(
                task_id=task_id,
                end_date=end_date,
                skip_stk_mins_5min=skip_stk_mins_5min,
            ):
                return
            self._append_log(task_id, "Tushare asset refresh completed")
            self.repository.update_refresh_task(task_id=task_id, status="success", finished=True)
        except Exception as exc:
            self._fail_task(task_id, f"refresh task failed: {type(exc).__name__}: {exc}")

    def refresh_index_dailybasic_only(self, *, end_date: date) -> int:
        self.repository.ensure_tables()
        task_id = self.repository.create_refresh_task(owner_pid=os.getpid())
        try:
            self._append_log(task_id, f"start Tushare index_dailybasic refresh only, end_date={end_date}")
            ok = self._refresh_index_dailybasic(task_id=task_id, end_date=end_date)
            self.repository.update_refresh_task(
                task_id=task_id,
                status="success" if ok else "error",
                finished=True,
            )
            return task_id
        except Exception as exc:
            self._fail_task(task_id, f"index_dailybasic refresh failed: {type(exc).__name__}: {exc}")
            return task_id

    def _refresh_index_basic(self, *, task_id: int) -> bool:
        asset_table_name = "tushare.index_basic"
        existing_count = self.repository.get_index_basic_count()
        missing_codes = self.repository.get_missing_index_basic_ts_codes()
        if existing_count > 0 and not missing_codes:
            self.repository.update_watermark(
                asset_table_name,
                self.repository.index_basic_watermark(),
                earliest_trusted_watermark=self.repository.index_basic_watermark(),
            )
            self._append_log(task_id, f"{asset_table_name} static pool already covered rows={existing_count}")
            return True
        if missing_codes:
            self._append_log(
                task_id,
                f"{asset_table_name} static pool missing keep codes={','.join(missing_codes)}; refreshing",
            )

        frames = []
        markets = self.repository.index_basic_markets()
        index_basic_fields = (
            "ts_code,name,fullname,market,publisher,index_type,category,"
            "base_date,base_point,list_date,weight_rule,desc,exp_date"
        )
        self.repository.update_refresh_task(
            task_id=task_id,
            current_asset_table_name=asset_table_name,
            current_watermark=self.repository.get_watermark(asset_table_name),
        )
        for market in markets:
            frame = self._call_with_retries(
                task_id=task_id,
                asset_table_name=asset_table_name,
                scope=market,
                fetcher=lambda market=market: get_tushare_pro().index_basic(
                    market=market,
                    fields=index_basic_fields,
                ),
            )
            if frame is None:
                self.repository.update_watermark(
                    asset_table_name,
                    self.repository.index_basic_watermark(),
                    earliest_trusted_watermark=self.repository.index_basic_watermark(),
                    issue_scope=market,
                    issue_message=f"{market} retries exhausted",
                )
                self._append_log(task_id, f"{asset_table_name} {market} retries exhausted; skipped")
                continue
            frames.append(frame)
        if not frames:
            self.repository.update_watermark(
                asset_table_name,
                self.repository.index_basic_watermark(),
                earliest_trusted_watermark=self.repository.index_basic_watermark(),
                issue_scope="all",
                issue_message="index_basic returned no market frames",
            )
            self._append_log(task_id, f"{asset_table_name} returned no market frames")
            return True
        row_count = self.repository.upsert_index_basic(pd.concat(frames, ignore_index=True))
        self.repository.update_watermark(
            asset_table_name,
            self.repository.index_basic_watermark(),
            earliest_trusted_watermark=self.repository.index_basic_watermark(),
        )
        self._append_log(
            task_id,
            (
                f"{asset_table_name} success rows={row_count} "
                f"keep_codes={len(self.repository.index_keep_ts_codes())}"
            ),
        )
        return True

    def _refresh_index_daily(self, *, task_id: int, end_date: date) -> bool:
        asset_table_name = "tushare.index_daily"
        watermark = self.repository.get_refresh_start_watermark(asset_table_name)
        missing_range = self.repository.get_index_daily_missing_date_range(end_date=end_date)
        start_watermark = watermark
        if missing_range is not None:
            start_watermark = min(start_watermark, missing_range[0] - timedelta(days=1))
        trade_dates = self.repository.get_open_trade_dates_after(start_watermark, end_date)
        self._append_log(task_id, f"{asset_table_name} pending open trade dates={len(trade_dates)}")
        if not trade_dates:
            return True

        uncovered_dates: list[date] = []
        for trade_day in trade_dates:
            coverage = self.repository.get_index_daily_day_coverage(trade_day)
            if (
                coverage["expected_code_count"] > 0
                and coverage["existing_code_count"] >= coverage["expected_code_count"]
            ):
                next_watermark = max(watermark, trade_day)
                self.repository.update_watermark(asset_table_name, next_watermark)
                watermark = next_watermark
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {self._format_tushare_date(trade_day)} already covered "
                        f"codes={coverage['existing_code_count']}/{coverage['expected_code_count']} "
                        f"rows={coverage['existing_row_count']}; watermark advanced"
                    ),
                )
                continue
            uncovered_dates.append(trade_day)

        if not uncovered_dates:
            return True

        ts_codes = self.repository.get_index_daily_ts_codes()
        if not ts_codes:
            issue_message = "index_basic static pool is empty"
            self.repository.update_watermark(
                asset_table_name,
                uncovered_dates[-1],
                issue_scope=f"{uncovered_dates[0]}->{uncovered_dates[-1]}",
                issue_message=issue_message,
            )
            self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
            return True

        start_date = uncovered_dates[0]
        end_uncovered_date = uncovered_dates[-1]
        start_text = self._format_tushare_date(start_date)
        end_text = self._format_tushare_date(end_uncovered_date)
        total_rows = 0
        failed_count = 0
        for index, ts_code in enumerate(ts_codes, start=1):
            self.repository.update_refresh_task(
                task_id=task_id,
                current_asset_table_name=asset_table_name,
                current_watermark=watermark,
            )
            frame = self._call_with_retries(
                task_id=task_id,
                asset_table_name=asset_table_name,
                scope=f"{ts_code} {start_text}->{end_text}",
                fetcher=lambda code=ts_code: get_tushare_pro().index_daily(
                    ts_code=code,
                    start_date=start_text,
                    end_date=end_text,
                ),
            )
            if frame is None:
                failed_count += 1
                continue
            total_rows += self.repository.upsert_index_daily(frame)
            if index % 200 == 0:
                self._append_log(
                    task_id,
                    f"{asset_table_name} progress {index}/{len(ts_codes)} rows={total_rows}",
                )

        if total_rows <= 0:
            self._append_log(
                task_id,
                (
                    f"{asset_table_name} {start_text}->{end_text} all codes failed "
                    f"failed_codes={failed_count}/{len(ts_codes)}; "
                    "watermark not advanced, will retry on next refresh"
                ),
            )
            return True

        for trade_day in uncovered_dates:
            coverage = self.repository.get_index_daily_day_coverage(trade_day)
            if (
                coverage["expected_code_count"] > 0
                and coverage["existing_code_count"] >= coverage["expected_code_count"]
            ):
                next_watermark = max(watermark, trade_day)
                self.repository.update_watermark(asset_table_name, next_watermark)
                watermark = next_watermark
                continue
            issue_message = (
                f"partial coverage codes={coverage['existing_code_count']}/"
                f"{coverage['expected_code_count']} rows={coverage['existing_row_count']}"
            )
            self.repository.update_watermark(
                asset_table_name,
                max(watermark, trade_day),
                issue_scope=self._format_tushare_date(trade_day),
                issue_message=issue_message,
            )
            watermark = max(watermark, trade_day)
            self._append_log(task_id, f"{asset_table_name} {trade_day} {issue_message}; watermark advanced")
        self._append_log(
            task_id,
            (
                f"{asset_table_name} {start_text}->{end_text} success rows={total_rows} "
                f"codes={len(ts_codes)} failed_codes={failed_count}"
            ),
        )
        return True

    def _refresh_index_dailybasic(self, *, task_id: int, end_date: date) -> bool:
        asset_table_name = "tushare.index_dailybasic"
        watermark = self.repository.get_refresh_start_watermark(asset_table_name)
        missing_range = self.repository.get_index_dailybasic_missing_date_range(end_date=end_date)
        start_watermark = watermark
        if missing_range is not None:
            start_watermark = min(start_watermark, missing_range[0] - timedelta(days=1))
        trade_dates = self.repository.get_open_trade_dates_after(start_watermark, end_date)
        self._append_log(task_id, f"{asset_table_name} pending open trade dates={len(trade_dates)}")
        if not trade_dates:
            return True

        uncovered_dates: list[date] = []
        for trade_day in trade_dates:
            coverage = self.repository.get_index_dailybasic_day_coverage(trade_day)
            if (
                coverage["expected_code_count"] > 0
                and coverage["existing_code_count"] >= coverage["expected_code_count"]
            ):
                next_watermark = max(watermark, trade_day)
                self.repository.update_watermark(asset_table_name, next_watermark)
                watermark = next_watermark
                continue
            uncovered_dates.append(trade_day)

        if not uncovered_dates:
            return True

        fields = (
            "ts_code,trade_date,total_mv,float_mv,total_share,float_share,"
            "free_share,turnover_rate,turnover_rate_f,pe,pe_ttm,pb"
        )
        ts_codes = self.repository.index_dailybasic_ts_codes()
        start_date = uncovered_dates[0]
        end_uncovered_date = uncovered_dates[-1]
        total_rows = 0
        failed_count = 0
        for index, ts_code in enumerate(ts_codes, start=1):
            code_failed = False
            for window_start, window_end in self._iter_year_windows(start_date, end_uncovered_date):
                start_text = self._format_tushare_date(window_start)
                end_text = self._format_tushare_date(window_end)
                self.repository.update_refresh_task(
                    task_id=task_id,
                    current_asset_table_name=asset_table_name,
                    current_watermark=watermark,
                )
                frame = self._call_with_retries(
                    task_id=task_id,
                    asset_table_name=asset_table_name,
                    scope=f"{ts_code} {start_text}->{end_text}",
                    fetcher=lambda code=ts_code, start=start_text, end=end_text: get_tushare_pro().index_dailybasic(
                        ts_code=code,
                        start_date=start,
                        end_date=end,
                        fields=fields,
                    ),
                )
                if frame is None:
                    code_failed = True
                    continue
                total_rows += self.repository.upsert_index_dailybasic(frame)
            if code_failed:
                failed_count += 1
            self._append_log(
                task_id,
                f"{asset_table_name} progress {index}/{len(ts_codes)} {ts_code} rows={total_rows}",
            )

        if total_rows <= 0:
            start_text = self._format_tushare_date(start_date)
            end_text = self._format_tushare_date(end_uncovered_date)
            self._append_log(
                task_id,
                (
                    f"{asset_table_name} {start_text}->{end_text} all codes failed "
                    f"failed_codes={failed_count}/{len(ts_codes)}; "
                    "watermark not advanced, will retry on next refresh"
                ),
            )
            return True

        for trade_day in uncovered_dates:
            coverage = self.repository.get_index_dailybasic_day_coverage(trade_day)
            if (
                coverage["expected_code_count"] > 0
                and coverage["existing_code_count"] >= coverage["expected_code_count"]
            ):
                next_watermark = max(watermark, trade_day)
                self.repository.update_watermark(asset_table_name, next_watermark)
                watermark = next_watermark
                continue
            issue_message = (
                f"partial coverage codes={coverage['existing_code_count']}/"
                f"{coverage['expected_code_count']} rows={coverage['existing_row_count']}"
            )
            next_watermark = max(watermark, trade_day)
            self.repository.update_watermark(
                asset_table_name,
                next_watermark,
                issue_scope=self._format_tushare_date(trade_day),
                issue_message=issue_message,
            )
            watermark = next_watermark
            self._append_log(task_id, f"{asset_table_name} {trade_day} {issue_message}; watermark advanced")
        self._append_log(
            task_id,
            (
                f"{asset_table_name} {self._format_tushare_date(start_date)}->"
                f"{self._format_tushare_date(end_uncovered_date)} success rows={total_rows} "
                f"codes={len(ts_codes)} failed_codes={failed_count}"
            ),
        )
        return True

    def _refresh_trade_cal(self, *, task_id: int, end_date: date) -> bool:
        asset_table_name = "tushare.trade_cal"
        watermark = self.repository.get_refresh_start_watermark(asset_table_name)
        if watermark >= end_date:
            self._append_log(task_id, f"{asset_table_name} watermark already at {watermark}")
            return True

        for window_start, window_end in self._iter_year_windows(watermark + timedelta(days=1), end_date):
            start_text = self._format_tushare_date(window_start)
            end_text = self._format_tushare_date(window_end)
            self.repository.update_refresh_task(
                task_id=task_id,
                current_asset_table_name=asset_table_name,
                current_watermark=watermark,
            )
            coverage = self.repository.get_trade_cal_window_coverage(window_start, window_end)
            if coverage["existing_day_count"] >= coverage["expected_day_count"]:
                self.repository.update_watermark(asset_table_name, window_end)
                watermark = window_end
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {start_text}->{end_text} already covered "
                        f"days={coverage['existing_day_count']}/{coverage['expected_day_count']} "
                        f"rows={coverage['existing_row_count']}; watermark advanced"
                    ),
                )
                continue
            frame = self._call_with_retries(
                task_id=task_id,
                asset_table_name=asset_table_name,
                scope=f"{start_text}->{end_text}",
                fetcher=lambda: get_tushare_pro().trade_cal(
                    exchange="",
                    start_date=start_text,
                    end_date=end_text,
                ),
            )
            if frame is None:
                self._append_log(
                    task_id,
                    f"{asset_table_name} {start_text}->{end_text} retries exhausted; watermark not advanced, will retry on next refresh",
                )
                break
            row_count = self.repository.upsert_trade_cal(frame)
            if row_count <= 0:
                self._append_log(
                    task_id,
                    f"{asset_table_name} {start_text}->{end_text} returned 0 rows; watermark not advanced, will retry on next refresh",
                )
                break
            self.repository.update_watermark(asset_table_name, window_end)
            watermark = window_end
            self._append_log(task_id, f"{asset_table_name} {start_text}->{end_text} success rows={row_count}")
        return True

    def _refresh_by_trade_dates(
        self,
        *,
        task_id: int,
        asset_table_name: str,
        fetcher: Callable[[date], pd.DataFrame],
        writer: Callable[[pd.DataFrame], int],
        end_date: date,
    ) -> bool:
        watermark = self.repository.get_refresh_start_watermark(asset_table_name)
        trade_dates = self.repository.get_open_trade_dates_after(watermark, end_date)
        self._append_log(task_id, f"{asset_table_name} pending open trade dates={len(trade_dates)}, stock_universe=SH/SZ excluding BJ")
        for trade_day in trade_dates:
            trade_date_text = self._format_tushare_date(trade_day)
            self.repository.update_refresh_task(
                task_id=task_id,
                current_asset_table_name=asset_table_name,
                current_watermark=watermark,
            )
            coverage = self.repository.get_daily_asset_day_coverage(asset_table_name, trade_day)
            if self._is_daily_asset_covered(asset_table_name, coverage):
                self.repository.update_watermark(asset_table_name, trade_day)
                watermark = trade_day
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {trade_date_text} already covered "
                        f"codes={coverage['existing_code_count']}/{coverage['expected_code_count']} "
                        f"rows={coverage['existing_row_count']} "
                        f"table_rows={coverage['table_row_count']}; watermark advanced"
                    ),
                )
                continue
            frame = self._call_with_retries(
                task_id=task_id,
                asset_table_name=asset_table_name,
                scope=trade_date_text,
                fetcher=lambda day=trade_day: fetcher(day),
            )
            if frame is None:
                self._append_log(
                    task_id,
                    f"{asset_table_name} {trade_date_text} retries exhausted; watermark not advanced, will retry on next refresh",
                )
                break
            row_count = writer(frame)
            if row_count <= 0:
                self._append_log(
                    task_id,
                    f"{asset_table_name} {trade_date_text} returned 0 rows; watermark not advanced, will retry on next refresh",
                )
                break
            self.repository.update_watermark(asset_table_name, trade_day)
            watermark = trade_day
            self._append_log(task_id, f"{asset_table_name} {trade_date_text} success rows={row_count}")
        return True

    def _is_daily_asset_covered(self, asset_table_name: str, coverage: dict[str, int]) -> bool:
        existing_code_count = coverage["existing_code_count"]
        expected_code_count = coverage["expected_code_count"]
        existing_row_count = coverage["existing_row_count"]
        if asset_table_name == "tushare.daily":
            return existing_code_count > 0 and existing_row_count > 0
        if coverage["table_row_count"] > 0:
            return True
        return expected_code_count > 0 and existing_code_count >= expected_code_count

    def _refresh_stock_daily_technical(
        self,
        *,
        task_id: int,
        end_date: date,
        skip_stk_mins_5min: bool = False,
    ) -> bool:
        asset_table_name = "tushare.stock_daily_technical"
        base_assets = [
            "tushare.bak_basic",
            "tushare.adj_factor",
            "tushare.daily",
            "tushare.daily_basic",
        ]
        target_watermark = self.repository.get_min_watermark(base_assets)
        if target_watermark is None:
            self.repository.update_watermark(
                asset_table_name,
                end_date,
                issue_scope=str(end_date),
                issue_message="base asset watermarks are not ready",
            )
            self._append_log(task_id, f"{asset_table_name} skipped: base asset watermarks are not ready")
            return True
        target_watermark = min(target_watermark, end_date)
        self.repository.update_refresh_task(
            task_id=task_id,
            current_asset_table_name=asset_table_name,
            current_watermark=self.repository.get_watermark(asset_table_name),
        )
        self._append_log(
            task_id,
            (
                f"{asset_table_name} rebuild snapshot target_watermark={target_watermark}, "
                "source=daily assets only"
            ),
        )
        row_count = self.repository.rebuild_stock_daily_technical(
            target_watermark=target_watermark,
            progress=lambda message: self._append_log(task_id, message),
        )
        if row_count <= 0:
            self.repository.update_watermark(
                asset_table_name,
                target_watermark,
                issue_scope=str(target_watermark),
                issue_message="snapshot rebuild returned 0 rows",
            )
            self._append_log(task_id, f"{asset_table_name} returned 0 rows; watermark advanced with issue")
            return True
        self.repository.update_watermark(asset_table_name, target_watermark)
        self._append_log(task_id, f"{asset_table_name} success rows={row_count}")
        return True

    def _call_with_retries(
        self,
        *,
        task_id: int,
        asset_table_name: str,
        scope: str,
        fetcher: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame | None:
        for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
            try:
                frame = fetcher()
                if not isinstance(frame, pd.DataFrame):
                    raise RuntimeError(f"unexpected tushare response type: {type(frame).__name__}")
                return frame
            except Exception as exc:
                reset_tushare_pro()
                if attempt >= MAX_CALL_ATTEMPTS:
                    self._append_log(
                        task_id,
                        (
                            f"{asset_table_name} {scope} attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    )
                    return None
                delay = RETRY_DELAYS_SECONDS[attempt - 1]
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {scope} attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: "
                        f"{type(exc).__name__}: {exc}; retry after {delay}s"
                    ),
                )
                time.sleep(delay)
        return None

    def _refresh_stk_mins_5min(self, *, task_id: int, end_date: date) -> bool:
        asset_table_name = "tushare.stk_mins_5min"
        watermark = self.repository.get_refresh_start_watermark(asset_table_name)
        trade_dates = self.repository.get_open_trade_dates_after(watermark, end_date)
        self._append_log(
            task_id,
            (
                f"{asset_table_name} pending open trade dates={len(trade_dates)}, "
                "source=baostock, fallback=tushare, stock_universe=SH/SZ excluding BJ"
            ),
        )
        if not trade_dates:
            return True

        uncovered_dates: list[date] = []
        for trade_day in trade_dates:
            trade_date_text = self._format_tushare_date(trade_day)
            self.repository.update_refresh_task(
                task_id=task_id,
                current_asset_table_name=asset_table_name,
                current_watermark=watermark,
            )
            ts_codes = self.repository.get_daily_ts_codes(trade_day)
            if not ts_codes:
                issue_message = f"{trade_date_text} has no daily ts_codes"
                self.repository.update_watermark(
                    asset_table_name,
                    trade_day,
                    issue_scope=trade_date_text,
                    issue_message=issue_message,
                )
                watermark = trade_day
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
                continue
            coverage = self.repository.get_stk_mins_5min_day_coverage(trade_day)
            if (
                coverage["expected_code_count"] > 0
                and coverage["existing_code_count"] >= coverage["expected_code_count"]
            ):
                self.repository.update_watermark(asset_table_name, trade_day)
                watermark = trade_day
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {trade_date_text} already covered "
                        f"codes={coverage['existing_code_count']}/{coverage['expected_code_count']} "
                        f"rows={coverage['existing_row_count']}; watermark advanced"
                    ),
                )
                continue
            uncovered_dates.append(trade_day)

        if not uncovered_dates:
            return True

        start_date = uncovered_dates[0]
        end_uncovered_date = uncovered_dates[-1]
        ts_codes = self.repository.get_daily_ts_codes_between(start_date, end_uncovered_date)
        if not ts_codes:
            issue_message = f"{start_date}->{end_uncovered_date} has no daily ts_codes"
            self.repository.update_watermark(
                asset_table_name,
                end_uncovered_date,
                issue_scope=f"{start_date}->{end_uncovered_date}",
                issue_message=issue_message,
            )
            self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
            return True

        start_text = self._format_tushare_date(start_date)
        end_text = self._format_tushare_date(end_uncovered_date)
        all_ts_code_count = len(ts_codes)
        covered_ts_codes = self.repository.get_stk_mins_5min_covered_ts_codes_between(
            start_date,
            end_uncovered_date,
            ts_codes,
        )
        if covered_ts_codes:
            ts_codes = [ts_code for ts_code in ts_codes if ts_code not in covered_ts_codes]
        if not ts_codes:
            self._append_log(
                task_id,
                (
                    f"{asset_table_name} {start_text}->{end_text} all range codes already covered "
                    f"codes={all_ts_code_count}; verify watermarks"
                ),
            )
            for trade_day in uncovered_dates:
                coverage = self.repository.get_stk_mins_5min_day_coverage(trade_day)
                if (
                    coverage["expected_code_count"] > 0
                    and coverage["existing_code_count"] >= coverage["expected_code_count"]
                ):
                    self.repository.update_watermark(asset_table_name, trade_day)
                    watermark = trade_day
                    continue
                trade_date_text = self._format_tushare_date(trade_day)
                issue_message = (
                    f"partial coverage codes={coverage['existing_code_count']}/"
                    f"{coverage['expected_code_count']} rows={coverage['existing_row_count']}"
                )
                self.repository.update_watermark(
                    asset_table_name,
                    trade_day,
                    issue_scope=trade_date_text,
                    issue_message=issue_message,
                )
                watermark = trade_day
                self._append_log(task_id, f"{asset_table_name} {trade_date_text} {issue_message}; watermark advanced")
            return True
        total_rows = 0
        failed_count = 0
        fallback_count = 0
        self._append_log(
            task_id,
            (
                f"{asset_table_name} {start_text}->{end_text} begin range refresh "
                f"open_dates={len(uncovered_dates)} codes={len(ts_codes)}/{all_ts_code_count} "
                f"skipped_codes={len(covered_ts_codes)} source=baostock fallback=tushare stock_universe=SH/SZ excluding BJ"
            ),
        )
        try:
            for index, ts_code in enumerate(ts_codes, start=1):
                self.repository.update_refresh_task(
                    task_id=task_id,
                    current_asset_table_name=asset_table_name,
                    current_watermark=watermark,
                )
                frame, source_name = self._call_stk_mins_5min_range_with_retries(
                    task_id=task_id,
                    asset_table_name=asset_table_name,
                    scope=f"{ts_code} {start_text}->{end_text}",
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_uncovered_date,
                )
                if frame is None:
                    failed_count += 1
                    continue
                if source_name == "tushare":
                    fallback_count += 1
                total_rows += self.repository.upsert_stk_mins_5min(frame)
                if index % 10 == 0:
                    self._append_log(
                        task_id,
                        (
                            f"{asset_table_name} {start_text}->{end_text} progress "
                            f"{index}/{len(ts_codes)} rows={total_rows} "
                            f"failed_codes={failed_count} fallback_codes={fallback_count}"
                        ),
                    )
        finally:
            self._logout_baostock()

        if total_rows <= 0:
            self._append_log(
                task_id,
                (
                    f"{asset_table_name} {start_text}->{end_text} all codes failed "
                    f"failed_codes={failed_count}/{len(ts_codes)}; "
                    "watermark not advanced, will retry on next refresh"
                ),
            )
            return True

        for trade_day in uncovered_dates:
            trade_date_text = self._format_tushare_date(trade_day)
            coverage = self.repository.get_stk_mins_5min_day_coverage(trade_day)
            if (
                coverage["expected_code_count"] > 0
                and coverage["existing_code_count"] >= coverage["expected_code_count"]
            ):
                self.repository.update_watermark(asset_table_name, trade_day)
                watermark = trade_day
                continue
            issue_message = (
                f"partial coverage codes={coverage['existing_code_count']}/"
                f"{coverage['expected_code_count']} rows={coverage['existing_row_count']}"
            )
            self.repository.update_watermark(
                asset_table_name,
                trade_day,
                issue_scope=trade_date_text,
                issue_message=issue_message,
            )
            watermark = trade_day
            self._append_log(task_id, f"{asset_table_name} {trade_date_text} {issue_message}; watermark advanced")
        self._append_log(
            task_id,
            (
                f"{asset_table_name} {start_text}->{end_text} success rows={total_rows} "
                f"codes={len(ts_codes)} failed_codes={failed_count} fallback_codes={fallback_count}"
            ),
        )
        return True

    def _call_stk_mins_5min_range_with_retries(
        self,
        *,
        task_id: int,
        asset_table_name: str,
        scope: str,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame | None, str | None]:
        use_tushare_fallback = False
        for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
            source_name = "tushare" if use_tushare_fallback else "baostock"
            try:
                if use_tushare_fallback:
                    frame = self._fetch_tushare_stk_mins_5min_range(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                    )
                else:
                    frame = self._fetch_baostock_stk_mins_5min_range(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                    )
                if not isinstance(frame, pd.DataFrame):
                    raise RuntimeError(f"unexpected {source_name} response type: {type(frame).__name__}")
                return frame, source_name
            except Exception as exc:
                if use_tushare_fallback:
                    reset_tushare_pro()
                if attempt >= MAX_CALL_ATTEMPTS:
                    self._append_log(
                        task_id,
                        (
                            f"{asset_table_name} {scope} source={source_name} "
                            f"attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: {type(exc).__name__}: {exc}"
                        ),
                    )
                    return None, source_name
                if not use_tushare_fallback and attempt >= 3:
                    use_tushare_fallback = True
                    self._append_log(
                        task_id,
                        (
                            f"{asset_table_name} {scope} source=baostock "
                            f"attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: {type(exc).__name__}: {exc}; "
                            "fallback to tushare"
                        ),
                    )
                    continue
                delay = RETRY_DELAYS_SECONDS[attempt - 1]
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {scope} source={source_name} "
                        f"attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: {type(exc).__name__}: {exc}; "
                        f"retry after {delay}s"
                    ),
                )
                time.sleep(delay)
        return None, None

    def _fetch_tushare_stk_mins_5min_range(
        self,
        *,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        frame = get_tushare_pro().stk_mins(
            ts_code=ts_code,
            freq="5min",
            start_date=self._format_minute_start(start_date),
            end_date=self._format_minute_end(end_date),
        )
        if not isinstance(frame, pd.DataFrame):
            raise RuntimeError(f"unexpected tushare response type: {type(frame).__name__}")
        if len(frame) >= TUSHARE_STK_MINS_MAX_ROWS:
            raise RuntimeError(
                f"tushare stk_mins returned {len(frame)} rows, reaches max limit {TUSHARE_STK_MINS_MAX_ROWS}"
            )
        return frame

    def _fetch_baostock_stk_mins_5min_range(
        self,
        *,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        self._ensure_baostock_login()
        query = bs.query_history_k_data_plus(
            self._to_baostock_code(ts_code),
            "date,time,code,open,high,low,close,volume,amount,adjustflag",
            start_date=f"{start_date:%Y-%m-%d}",
            end_date=f"{end_date:%Y-%m-%d}",
            frequency="5",
            adjustflag="3",
        )
        if query.error_code != "0":
            raise RuntimeError(f"baostock query failed: {query.error_code} {query.error_msg}")
        frame = self._baostock_5min_query_to_tushare_shape(query, ts_code)
        if len(frame) >= BAOSTOCK_STK_MINS_MAX_ROWS:
            raise RuntimeError(
                f"baostock stk_mins returned {len(frame)} rows, reaches max limit {BAOSTOCK_STK_MINS_MAX_ROWS}"
            )
        return frame

    def _call_stk_mins_5min_with_retries(
        self,
        *,
        task_id: int,
        asset_table_name: str,
        scope: str,
        ts_code: str,
        trade_day: date,
        use_baostock_source: bool,
    ) -> tuple[pd.DataFrame | None, bool]:
        for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
            source_name = "baostock" if use_baostock_source else "tushare"
            try:
                if use_baostock_source:
                    frame = self._fetch_baostock_stk_mins_5min(ts_code=ts_code, trade_day=trade_day)
                else:
                    frame = get_tushare_pro().stk_mins(
                        ts_code=ts_code,
                        freq="5min",
                        start_date=self._format_minute_start(trade_day),
                        end_date=self._format_minute_end(trade_day),
                    )
                if not isinstance(frame, pd.DataFrame):
                    raise RuntimeError(f"unexpected {source_name} response type: {type(frame).__name__}")
                return frame, use_baostock_source
            except Exception as exc:
                if not use_baostock_source:
                    reset_tushare_pro()
                if attempt >= MAX_CALL_ATTEMPTS:
                    self._append_log(
                        task_id,
                        (
                            f"{asset_table_name} {scope} source={source_name} "
                            f"attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: {type(exc).__name__}: {exc}"
                        ),
                    )
                    return None, use_baostock_source
                if not use_baostock_source and attempt >= 2:
                    use_baostock_source = True
                    self._append_log(
                        task_id,
                        (
                            f"{asset_table_name} {scope} source=tushare "
                            f"attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: {type(exc).__name__}: {exc}; "
                            "switch subsequent 5min fetches to baostock"
                        ),
                    )
                    continue
                delay = RETRY_DELAYS_SECONDS[attempt - 1]
                self._append_log(
                    task_id,
                    (
                        f"{asset_table_name} {scope} source={source_name} "
                        f"attempt {attempt}/{MAX_CALL_ATTEMPTS} failed: {type(exc).__name__}: {exc}; "
                        f"retry after {delay}s"
                    ),
                )
                time.sleep(delay)
        return None, use_baostock_source

    def _fetch_baostock_stk_mins_5min(self, *, ts_code: str, trade_day: date) -> pd.DataFrame:
        return self._fetch_baostock_stk_mins_5min_range(
            ts_code=ts_code,
            start_date=trade_day,
            end_date=trade_day,
        )

    def _baostock_5min_query_to_tushare_shape(self, query: Any, ts_code: str) -> pd.DataFrame:
        rows = []
        while query.next():
            rows.append(query.get_row_data())
        if not rows:
            return pd.DataFrame(
                columns=["ts_code", "trade_time", "open", "close", "high", "low", "vol", "amount"],
            )
        frame = pd.DataFrame(rows, columns=query.fields)
        trade_time = pd.to_datetime(frame["time"].astype(str).str.slice(0, 14), format="%Y%m%d%H%M%S")
        return pd.DataFrame(
            {
                "ts_code": ts_code,
                "trade_time": trade_time.dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": pd.to_numeric(frame["open"], errors="coerce"),
                "close": pd.to_numeric(frame["close"], errors="coerce"),
                "high": pd.to_numeric(frame["high"], errors="coerce"),
                "low": pd.to_numeric(frame["low"], errors="coerce"),
                "vol": pd.to_numeric(frame["volume"], errors="coerce"),
                "amount": pd.to_numeric(frame["amount"], errors="coerce"),
            },
        )

    def _ensure_baostock_login(self) -> None:
        if self._baostock_logged_in:
            return
        login_result = bs.login()
        if login_result.error_code != "0":
            raise RuntimeError(f"baostock login failed: {login_result.error_code} {login_result.error_msg}")
        self._baostock_logged_in = True

    def _logout_baostock(self) -> None:
        if not self._baostock_logged_in:
            return
        bs.logout()
        self._baostock_logged_in = False

    def _to_baostock_code(self, ts_code: str) -> str:
        parts = ts_code.split(".", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"invalid Tushare ts_code: {ts_code}")
        symbol, exchange = parts
        exchange_prefix = {
            "SH": "sh",
            "SZ": "sz",
            "BJ": "bj",
        }.get(exchange.upper())
        if exchange_prefix is None:
            raise ValueError(f"unsupported Baostock exchange for ts_code: {ts_code}")
        return f"{exchange_prefix}.{symbol}"

    def _fail_task(self, task_id: int, message: str) -> None:
        self._append_log(task_id, message)
        self.repository.update_refresh_task(task_id=task_id, status="error", finished=True)

    def _is_stale_running_task(self, task: dict[str, Any]) -> bool:
        owner_pid = task.get("owner_pid")
        if owner_pid is not None:
            return not self._is_process_alive(int(owner_pid))

        updated_at_text = task.get("updated_at")
        if not updated_at_text:
            return True
        try:
            updated_at = datetime.fromisoformat(str(updated_at_text))
        except ValueError:
            return True
        return (datetime.now() - updated_at).total_seconds() > RUNNING_TASK_STALE_AFTER_SECONDS

    def _is_process_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _append_log(self, task_id: int, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repository.update_refresh_task(
            task_id=task_id,
            append_log=f"[{timestamp}] {message}\n",
        )

    def _iter_year_windows(self, start_date: date, end_date: date) -> list[tuple[date, date]]:
        if start_date > end_date:
            return []
        windows = []
        current = start_date
        while current <= end_date:
            window_end = min(end_date, date(current.year, 12, 31))
            windows.append((current, window_end))
            current = window_end + timedelta(days=1)
        return windows

    def _format_tushare_date(self, value: date) -> str:
        return value.strftime("%Y%m%d")

    def _format_minute_start(self, value: date) -> str:
        return f"{value:%Y-%m-%d} 09:00:00"

    def _format_minute_end(self, value: date) -> str:
        return f"{value:%Y-%m-%d} 15:30:00"
