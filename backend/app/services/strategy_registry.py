from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from strategies.small_float_value import (
    SMALL_FLOAT_VALUE_REQUIRED_COLUMNS,
    small_float_value_code_filter,
    small_float_value_lifecycle,
)


@dataclass(frozen=True)
class StrategyRegistration:
    name: str
    lifecycle: object
    required_columns: tuple[str, ...] = ()
    code_filter: Callable[[str], bool] | None = None


STRATEGY_REGISTRY: dict[str, StrategyRegistration] = {
    "small_float_value": StrategyRegistration(
        name="small_float_value",
        lifecycle=small_float_value_lifecycle,
        required_columns=SMALL_FLOAT_VALUE_REQUIRED_COLUMNS,
        code_filter=small_float_value_code_filter,
    ),
}


def get_strategy(name: str) -> StrategyRegistration | None:
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
