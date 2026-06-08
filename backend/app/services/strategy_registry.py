from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from app.entities.stock_data_context import StockDataContext
from strategies.demo import (
    demo_entry_strategy,
    demo_exit_strategy,
    demo_signal_strategy,
    demo_universe_filter,
)


class SignalStrategyFn(Protocol):
    def __call__(self, context: StockDataContext) -> bool:
        ...


class UniverseFilterFn(Protocol):
    def __call__(self, context: StockDataContext) -> bool:
        ...


@dataclass(frozen=True)
class StrategyRegistration:
    name: str
    signal_strategy: SignalStrategyFn
    entry_strategy: Callable[..., int]
    exit_strategy: Callable[..., int]
    universe_filter: UniverseFilterFn | None = None
    daily_signal_history_limit: int | None = None


STRATEGY_REGISTRY: dict[str, StrategyRegistration] = {
    "demo": StrategyRegistration(
        name="demo",
        signal_strategy=demo_signal_strategy,
        entry_strategy=demo_entry_strategy,
        exit_strategy=demo_exit_strategy,
        universe_filter=demo_universe_filter,
        daily_signal_history_limit=430,
    )
}


def get_strategy(name: str) -> StrategyRegistration | None:
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
