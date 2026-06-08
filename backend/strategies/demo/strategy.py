from __future__ import annotations

from typing import Any

from app.entities.stock_data_context import StockDataContext


def demo_signal_strategy(context: StockDataContext) -> bool:
    """Demo signal strategy interface. Real strategies return True on signal."""
    return False


def demo_entry_strategy(*_args: Any, **_kwargs: Any) -> int:
    return -1


def demo_exit_strategy(*_args: Any, **_kwargs: Any) -> int:
    return -1
