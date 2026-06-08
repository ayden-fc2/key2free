from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from 策略.demo import (
    demo_entry_strategy,
    demo_exit_strategy,
    demo_signal_strategy,
)
from 策略.demo.strategy import SignalStrategyInput


class SignalStrategyFn(Protocol):
    def __call__(self, payload: SignalStrategyInput) -> bool:
        ...


@dataclass(frozen=True)
class StrategyRegistration:
    name: str
    signal_strategy: SignalStrategyFn
    entry_strategy: Callable[..., int]
    exit_strategy: Callable[..., int]


STRATEGY_REGISTRY: dict[str, StrategyRegistration] = {
    "demo": StrategyRegistration(
        name="demo",
        signal_strategy=demo_signal_strategy,
        entry_strategy=demo_entry_strategy,
        exit_strategy=demo_exit_strategy,
    )
}


def get_strategy(name: str) -> StrategyRegistration | None:
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
