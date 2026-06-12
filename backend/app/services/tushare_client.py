from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import tushare as ts


TUSHARE_TOKEN = os.getenv(
    "TUSHARE_TOKEN",
    "yHKDrJkUIrQkXgMOWWToyuUesKYbtCRKprrYXRXDCOdfhjrMEnpyybZNFmmtQpaf",
)
TUSHARE_HTTP_URL = os.getenv("TUSHARE_HTTP_URL", "https://dailyfetch.top/")
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
