from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from strategies.demo import (
    SMALL_FLOAT_VALUE_REQUIRED_COLUMNS as DEMO_REQUIRED_COLUMNS,
    demo_code_filter,
    demo_lifecycle,
)
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
    signal_required_columns: tuple[str, ...] | None = None
    signal_history_window: int = 200
    signal_index_codes: tuple[str, ...] = ()
    trading_clock_period: str | None = None

    @property
    def use_trading_week_clock(self) -> bool:
        return self.trading_clock_period == "W"


STRATEGY_REGISTRY: dict[str, StrategyRegistration] = {
    "demo": StrategyRegistration(
        name="demo",
        lifecycle=demo_lifecycle,
        required_columns=DEMO_REQUIRED_COLUMNS,
        code_filter=demo_code_filter,
        signal_required_columns=(
            "name",
            "list_date",
            "close",
            "qfq_close",
            "is_st",
            "eps",
            "total_mv",
            "circ_mv",
        ),
        signal_history_window=200,
    ),
    "small_float_value": StrategyRegistration(
        name="small_float_value",
        lifecycle=small_float_value_lifecycle,
        required_columns=SMALL_FLOAT_VALUE_REQUIRED_COLUMNS,
        code_filter=small_float_value_code_filter,
        signal_required_columns=(
            "name",
            "list_date",
            "close",
            "is_st",
            "eps",
            "circ_mv",
        ),
        signal_history_window=20,
        trading_clock_period="W",
    ),
}


def get_strategy(name: str) -> StrategyRegistration | None:
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
