from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SignalStrategyInput:
    code: str
    trade_date: date
    universe: dict[str, Any]
    bars_1d_qfq: list[dict[str, Any]]
    current_bar_1d_qfq: dict[str, Any] | None


def demo_signal_strategy(payload: SignalStrategyInput) -> bool:
    """Demo signal strategy interface. Real strategies return True on signal."""
    return False


def demo_entry_strategy(*_args: Any, **_kwargs: Any) -> int:
    return -1


def demo_exit_strategy(*_args: Any, **_kwargs: Any) -> int:
    return -1

