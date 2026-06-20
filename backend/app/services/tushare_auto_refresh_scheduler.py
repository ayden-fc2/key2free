from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta

from app.core.config import settings
from app.services.tushare_asset_service import TushareAssetService


class TushareAutoRefreshScheduler:
    _lock = threading.Lock()
    _thread: threading.Thread | None = None
    _stop_event = threading.Event()
    _last_trigger_date: date | None = None

    @classmethod
    def start(cls) -> None:
        if not settings.auto_tushare_refresh_enabled:
            return
        with cls._lock:
            if cls._thread is not None and cls._thread.is_alive():
                return
            cls._stop_event.clear()
            cls._thread = threading.Thread(target=cls._run, name="tushare-auto-refresh", daemon=True)
            cls._thread.start()

    @classmethod
    def stop(cls) -> None:
        cls._stop_event.set()

    @classmethod
    def _run(cls) -> None:
        while not cls._stop_event.is_set():
            now = datetime.now()
            next_run = cls._next_run_at(now)
            wait_seconds = max(1.0, (next_run - now).total_seconds())
            if cls._stop_event.wait(wait_seconds):
                return
            cls._trigger_once()

    @classmethod
    def _next_run_at(cls, now: datetime) -> datetime:
        run_at = now.replace(
            hour=settings.auto_tushare_refresh_hour,
            minute=settings.auto_tushare_refresh_minute,
            second=0,
            microsecond=0,
        )
        if run_at <= now:
            run_at += timedelta(days=1)
        return run_at

    @classmethod
    def _trigger_once(cls) -> None:
        trigger_day = date.today()
        if cls._last_trigger_date == trigger_day:
            return
        cls._last_trigger_date = trigger_day
        end_date = trigger_day - timedelta(days=1)
        TushareAssetService().start_refresh(
            end_date=end_date,
            skip_stk_mins_5min=False,
        )
