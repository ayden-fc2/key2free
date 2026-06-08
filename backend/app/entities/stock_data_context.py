from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class StockDataContext:
    code: str
    trade_date: date
    universe: dict[str, Any]
    bars_1d_qfq: list[dict[str, Any]]
