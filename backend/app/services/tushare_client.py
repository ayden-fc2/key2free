from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import tushare as ts


TUSHARE_TOKEN = os.getenv(
    "TUSHARE_TOKEN",
    "5607915ec5b89d0366856311822399cfb4af896842e2296b697dbff2",
)
TUSHARE_HTTP_URL = os.getenv("TUSHARE_HTTP_URL", "https://minitick.top/").rstrip("/")
TUSHARE_MCP_URL = os.getenv(
    "TUSHARE_MCP_URL",
    f"https://minitick.top/mcp?token={TUSHARE_TOKEN}",
)
TUSHARE_TIMEOUT_SECONDS = int(os.getenv("TUSHARE_TIMEOUT_SECONDS", "30"))


@lru_cache(maxsize=1)
def get_tushare_pro() -> Any:
    pro = ts.pro_api(TUSHARE_TOKEN, timeout=TUSHARE_TIMEOUT_SECONDS)
    pro._DataApi__http_url = TUSHARE_HTTP_URL
    return pro


def reset_tushare_pro() -> None:
    get_tushare_pro.cache_clear()


def pro_bar(**kwargs: Any) -> Any:
    return ts.pro_bar(api=get_tushare_pro(), **kwargs)
