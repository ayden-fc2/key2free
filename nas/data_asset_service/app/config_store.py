from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any

from app.services.tushare_client import configure_tushare_client


DEFAULT_CONFIG = {
    "tushare_token": os.getenv("TUSHARE_TOKEN", ""),
    "tushare_http_url": os.getenv("TUSHARE_HTTP_URL", "https://minitick.top/"),
    "tushare_mcp_url": os.getenv("TUSHARE_MCP_URL") or None,
    "tushare_timeout_seconds": int(os.getenv("TUSHARE_TIMEOUT_SECONDS", "30")),
    "schedule_enabled": os.getenv("NAS_REFRESH_SCHEDULE_ENABLED", "true").lower()
    in {"1", "true", "yes", "on"},
    "schedule_hour": int(os.getenv("NAS_REFRESH_HOUR", "2")),
    "schedule_minute": int(os.getenv("NAS_REFRESH_MINUTE", "30")),
    "advertised_host": os.getenv("NAS_ADVERTISED_HOST", "192.168.1.62"),
    "advertised_port": int(os.getenv("NAS_ADVERTISED_PORT", "18080")),
}


class ServiceConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        configured_path = os.getenv("SERVICE_CONFIG_PATH", "/app/data/config/service_config.json")
        self.path = Path(path or configured_path)
        self._lock = RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            values = dict(DEFAULT_CONFIG)
            if self.path.exists():
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    values.update(stored)
            return values

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            values = self.load()
            values.update({key: value for key, value in updates.items() if value is not None})
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(values, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
            return values

    def public(self) -> dict[str, Any]:
        values = self.load()
        token = str(values.get("tushare_token") or "")
        return {
            "tushare_token_masked": self._mask_token(token),
            "tushare_token_configured": bool(token),
            "tushare_http_url": values["tushare_http_url"],
            # The generated MCP URL embeds the token as a query parameter.
            "tushare_mcp_url": None,
            "tushare_timeout_seconds": int(values["tushare_timeout_seconds"]),
            "schedule_enabled": bool(values["schedule_enabled"]),
            "schedule_hour": int(values["schedule_hour"]),
            "schedule_minute": int(values["schedule_minute"]),
            "advertised_host": values["advertised_host"],
            "advertised_port": int(values["advertised_port"]),
        }

    def apply_tushare_config(self) -> bool:
        values = self.load()
        token = str(values.get("tushare_token") or "").strip()
        http_url = str(values.get("tushare_http_url") or "").strip()
        if not token or not http_url:
            return False
        configure_tushare_client(
            token=token,
            http_url=http_url,
            mcp_url=values.get("tushare_mcp_url"),
            timeout_seconds=int(values.get("tushare_timeout_seconds") or 30),
        )
        return True

    @staticmethod
    def _mask_token(token: str) -> str:
        if not token:
            return ""
        if len(token) <= 8:
            return "*" * len(token)
        return f"{token[:4]}{'*' * (len(token) - 8)}{token[-4:]}"


service_config_store = ServiceConfigStore()
