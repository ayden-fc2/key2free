from __future__ import annotations

import os
from functools import lru_cache
from threading import RLock
from typing import Any

import tushare as ts


TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
TUSHARE_HTTP_URL = os.getenv("TUSHARE_HTTP_URL", "https://minitick.top/").rstrip("/")
TUSHARE_MCP_URL = os.getenv(
    "TUSHARE_MCP_URL",
    f"{TUSHARE_HTTP_URL}/mcp" + (f"?token={TUSHARE_TOKEN}" if TUSHARE_TOKEN else ""),
)
TUSHARE_TIMEOUT_SECONDS = int(os.getenv("TUSHARE_TIMEOUT_SECONDS", "30"))
_CONFIG_LOCK = RLock()


def configure_tushare_client(
    *,
    token: str,
    http_url: str,
    mcp_url: str | None = None,
    timeout_seconds: int = 30,
) -> None:
    """Apply runtime credentials and reset the cached Tushare client."""
    normalized_token = token.strip()
    normalized_http_url = http_url.strip().rstrip("/")
    if not normalized_token:
        raise ValueError("Tushare token must not be empty")
    if not normalized_http_url:
        raise ValueError("Tushare HTTP URL must not be empty")
    if timeout_seconds <= 0:
        raise ValueError("Tushare timeout must be positive")

    global TUSHARE_TOKEN, TUSHARE_HTTP_URL, TUSHARE_MCP_URL, TUSHARE_TIMEOUT_SECONDS
    with _CONFIG_LOCK:
        TUSHARE_TOKEN = normalized_token
        TUSHARE_HTTP_URL = normalized_http_url
        TUSHARE_MCP_URL = (mcp_url or f"{normalized_http_url}/mcp?token={normalized_token}").strip()
        TUSHARE_TIMEOUT_SECONDS = int(timeout_seconds)
        get_tushare_pro.cache_clear()


def get_tushare_client_config(*, include_token: bool = False) -> dict[str, Any]:
    with _CONFIG_LOCK:
        return {
            "token": TUSHARE_TOKEN if include_token else _mask_token(TUSHARE_TOKEN),
            "token_configured": bool(TUSHARE_TOKEN),
            "http_url": TUSHARE_HTTP_URL,
            "mcp_url": TUSHARE_MCP_URL,
            "timeout_seconds": TUSHARE_TIMEOUT_SECONDS,
        }


def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}{'*' * (len(token) - 8)}{token[-4:]}"


@lru_cache(maxsize=1)
def get_tushare_pro() -> Any:
    with _CONFIG_LOCK:
        if not TUSHARE_TOKEN:
            raise RuntimeError("Tushare token is not configured")
        pro = ts.pro_api(TUSHARE_TOKEN, timeout=TUSHARE_TIMEOUT_SECONDS)
        pro._DataApi__http_url = TUSHARE_HTTP_URL
        return pro


def reset_tushare_pro() -> None:
    get_tushare_pro.cache_clear()


def pro_bar(**kwargs: Any) -> Any:
    return ts.pro_bar(api=get_tushare_pro(), **kwargs)
