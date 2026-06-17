from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import pandas as pd

from app.repositories.tushare_repository import TushareRepository
from app.services.tushare_client import get_tushare_pro, reset_tushare_pro


RETRY_DELAYS_SECONDS = (10, 60, 180)
MAX_CALL_ATTEMPTS = len(RETRY_DELAYS_SECONDS) + 1
STK_MINS_CALL_INTERVAL_SECONDS = float(os.getenv("TUSHARE_STK_MINS_CALL_INTERVAL_SECONDS", "0.2"))


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

    def list_watermarks(self) -> list[dict[str, Any]]:
        return self.repository.get_watermarks()

    def get_refresh_task(self, task_id: int | None = None) -> dict[str, Any] | None:
        return self.repository.get_refresh_task(task_id)

    def finish_running_tasks(self, message: str) -> int:
        return self.repository.finish_running_refresh_tasks(message)

    def start_refresh(self, *, end_date: date, skip_stk_mins_5min: bool = False) -> TushareRefreshStartResult:
        self.repository.ensure_tables()
        with self._lock:
            running = self.repository.get_running_refresh_task()
            if running is not None:
                return TushareRefreshStartResult(
                    ok=False,
                    task_id=running["id"],
                    message="tushare refresh task is already running",
                )
            task_id = self.repository.create_refresh_task()
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
                issue_message = f"{start_text}->{end_text} retries exhausted"
                self.repository.update_watermark(
                    asset_table_name,
                    window_end,
                    issue_scope=f"{start_text}->{end_text}",
                    issue_message=issue_message,
                )
                watermark = window_end
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
                continue
            row_count = self.repository.upsert_trade_cal(frame)
            if row_count <= 0:
                issue_message = f"{start_text}->{end_text} returned 0 rows"
                self.repository.update_watermark(
                    asset_table_name,
                    window_end,
                    issue_scope=f"{start_text}->{end_text}",
                    issue_message=issue_message,
                )
                watermark = window_end
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
                continue
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
        self._append_log(task_id, f"{asset_table_name} pending open trade dates={len(trade_dates)}")
        for trade_day in trade_dates:
            trade_date_text = self._format_tushare_date(trade_day)
            self.repository.update_refresh_task(
                task_id=task_id,
                current_asset_table_name=asset_table_name,
                current_watermark=watermark,
            )
            frame = self._call_with_retries(
                task_id=task_id,
                asset_table_name=asset_table_name,
                scope=trade_date_text,
                fetcher=lambda day=trade_day: fetcher(day),
            )
            if frame is None:
                issue_message = f"{trade_date_text} retries exhausted"
                self.repository.update_watermark(
                    asset_table_name,
                    trade_day,
                    issue_scope=trade_date_text,
                    issue_message=issue_message,
                )
                watermark = trade_day
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
                continue
            row_count = writer(frame)
            if row_count <= 0:
                issue_message = f"{trade_date_text} returned 0 rows"
                self.repository.update_watermark(
                    asset_table_name,
                    trade_day,
                    issue_scope=trade_date_text,
                    issue_message=issue_message,
                )
                watermark = trade_day
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
                continue
            self.repository.update_watermark(asset_table_name, trade_day)
            watermark = trade_day
            self._append_log(task_id, f"{asset_table_name} {trade_date_text} success rows={row_count}")
        return True

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
        if not skip_stk_mins_5min:
            base_assets.append("tushare.stk_mins_5min")
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
                f"skip_stk_mins_5min={skip_stk_mins_5min}"
            ),
        )
        row_count = self.repository.rebuild_stock_daily_technical(
            target_watermark=target_watermark,
            include_min5_close=not skip_stk_mins_5min,
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
                f"call_interval={STK_MINS_CALL_INTERVAL_SECONDS}s"
            ),
        )
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
            row_count = 0
            failed_count = 0
            for index, ts_code in enumerate(ts_codes, start=1):
                frame = self._call_with_retries(
                    task_id=task_id,
                    asset_table_name=asset_table_name,
                    scope=f"{trade_date_text} {ts_code}",
                    fetcher=lambda code=ts_code, day=trade_day: get_tushare_pro().stk_mins(
                        ts_code=code,
                        freq="5min",
                        start_date=self._format_minute_start(day),
                        end_date=self._format_minute_end(day),
                    ),
                )
                if frame is None:
                    failed_count += 1
                    if row_count <= 0:
                        break
                    continue
                written_rows = self.repository.upsert_stk_mins_5min(frame)
                row_count += written_rows
                if STK_MINS_CALL_INTERVAL_SECONDS > 0:
                    time.sleep(STK_MINS_CALL_INTERVAL_SECONDS)
                if index % 500 == 0:
                    self._append_log(
                        task_id,
                        f"{asset_table_name} {trade_date_text} progress {index}/{len(ts_codes)} rows={row_count}",
                    )
            if row_count <= 0:
                issue_message = f"{trade_date_text} returned 0 rows, failed_codes={failed_count}/{len(ts_codes)}"
                self.repository.update_watermark(
                    asset_table_name,
                    trade_day,
                    issue_scope=trade_date_text,
                    issue_message=issue_message,
                )
                watermark = trade_day
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
                continue
            if failed_count > 0:
                issue_message = f"{trade_date_text} partial failures={failed_count}/{len(ts_codes)}"
                self.repository.update_watermark(
                    asset_table_name,
                    trade_day,
                    issue_scope=trade_date_text,
                    issue_message=issue_message,
                )
                self._append_log(task_id, f"{asset_table_name} {issue_message}; watermark advanced with issue")
            else:
                self.repository.update_watermark(asset_table_name, trade_day)
            watermark = trade_day
            self._append_log(
                task_id,
                f"{asset_table_name} {trade_date_text} success rows={row_count} codes={len(ts_codes)}",
            )
        return True

    def _fail_task(self, task_id: int, message: str) -> None:
        self._append_log(task_id, message)
        self.repository.update_refresh_task(task_id=task_id, status="error", finished=True)

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
