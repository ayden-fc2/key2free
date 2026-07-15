from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone

from .asset_runtime import nas_asset_runtime
from .config_store import service_config_store
from .operation_log import operation_log_store


SHANGHAI_TIMEZONE = timezone(timedelta(hours=8))


class NightlyRefreshScheduler:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._reload_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="nas-nightly-asset-refresh",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._reload_event.set()

    def notify_config_changed(self) -> None:
        self._reload_event.set()

    def status(self) -> dict[str, object]:
        config = service_config_store.load()
        next_run = self._next_run_at(datetime.now(SHANGHAI_TIMEZONE), config)
        return {
            "enabled": bool(config["schedule_enabled"]),
            "hour": int(config["schedule_hour"]),
            "minute": int(config["schedule_minute"]),
            "timezone": "Asia/Shanghai",
            "next_run_at": None if next_run is None else next_run.isoformat(),
            "thread_alive": self._thread is not None and self._thread.is_alive(),
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._reload_event.clear()
            config = service_config_store.load()
            now = datetime.now(SHANGHAI_TIMEZONE)
            next_run = self._next_run_at(now, config)
            wait_seconds = 60.0 if next_run is None else max(1.0, (next_run - now).total_seconds())
            if self._reload_event.wait(wait_seconds):
                continue
            if self._stop_event.is_set():
                return
            trigger_day = datetime.now(SHANGHAI_TIMEZONE).date()
            try:
                nas_asset_runtime.start_refresh(
                    end_date=trigger_day - timedelta(days=1),
                    source="schedule",
                    skip_stk_mins_5min=False,
                )
            except Exception as exc:
                operation_log_store.append(
                    operation="asset_refresh",
                    status="error",
                    source="schedule",
                    message=f"scheduler failed: {type(exc).__name__}: {exc}",
                    details={"trigger_day": str(trigger_day)},
                )

    @staticmethod
    def _next_run_at(now: datetime, config: dict[str, object]) -> datetime | None:
        if not config["schedule_enabled"]:
            return None
        run_at = now.replace(
            hour=int(config["schedule_hour"]),
            minute=int(config["schedule_minute"]),
            second=0,
            microsecond=0,
        )
        if run_at <= now:
            run_at += timedelta(days=1)
        return run_at


nightly_refresh_scheduler = NightlyRefreshScheduler()
