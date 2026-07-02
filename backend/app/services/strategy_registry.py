from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from strategies.small_float_value import (
    SMALL_FLOAT_VALUE_REQUIRED_COLUMNS,
    small_float_value_code_filter,
    small_float_value_lifecycle,
)
from strategies.sharp_rise_pullback_leader import (
    SHARP_RISE_PULLBACK_LEADER_REQUIRED_COLUMNS,
    sharp_rise_pullback_leader_code_filter,
    sharp_rise_pullback_leader_lifecycle,
)
from strategies.sharp_rise_pullback_leader_v2 import (
    sharp_rise_pullback_leader_v2_code_filter,
    sharp_rise_pullback_leader_v2_lifecycle,
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
    signal_period_day: int | None = None
    rebalance_period_day: int | None = None

    @property
    def use_trading_week_clock(self) -> bool:
        return self.trading_clock_period == "W"

    def is_signal_day(self, clock: object) -> bool:
        if self.signal_period_day is not None and hasattr(clock, "is_period_day"):
            return bool(clock.is_period_day(self.signal_period_day))
        return bool(getattr(clock, "is_period_end", False))

    def is_rebalance_day(self, clock: object) -> bool:
        if self.rebalance_period_day is not None and hasattr(clock, "is_period_day"):
            return bool(clock.is_period_day(self.rebalance_period_day))
        return bool(getattr(clock, "is_period_start", False))


STRATEGY_REGISTRY: dict[str, StrategyRegistration] = {
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
        signal_history_window=0,
        trading_clock_period="W",
    ),
    "sharp_rise_pullback_leader": StrategyRegistration(
        name="sharp_rise_pullback_leader",
        lifecycle=sharp_rise_pullback_leader_lifecycle,
        required_columns=SHARP_RISE_PULLBACK_LEADER_REQUIRED_COLUMNS,
        code_filter=sharp_rise_pullback_leader_code_filter,
        signal_required_columns=(
            "name",
            "close",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "ma_10",
            "ma_20",
            "ma_30",
            "pct_chg",
            "is_st",
            "turnover_rate",
        ),
        signal_history_window=200,
    ),
    "sharp_rise_pullback_leader_v2": StrategyRegistration(
        name="sharp_rise_pullback_leader_v2",
        lifecycle=sharp_rise_pullback_leader_v2_lifecycle,
        required_columns=SHARP_RISE_PULLBACK_LEADER_REQUIRED_COLUMNS,
        code_filter=sharp_rise_pullback_leader_v2_code_filter,
        signal_required_columns=(
            "name",
            "close",
            "qfq_open",
            "qfq_high",
            "qfq_low",
            "qfq_close",
            "ma_10",
            "ma_20",
            "ma_30",
            "ma_slope_30",
            "rsi_14",
            "volume_ratio_10",
            "avg_amount_20",
            "pct_chg",
            "is_st",
            "turnover_rate",
        ),
        signal_history_window=200,
    ),
}


def get_strategy(name: str) -> StrategyRegistration | None:
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
