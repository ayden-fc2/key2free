from __future__ import annotations

from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame
from strategies.algorithms import GoldenBowlConfig, resolve_golden_bowl


CHANNEL_BREAKOUT_POSITION_AMOUNT = 20000.0
CHANNEL_BREAKOUT_MAX_HOLDING_DAYS = 1
CHANNEL_BREAKOUT_MAX_WATCH_DAYS = 3

CHANNEL_LENGTH = 20
CHANNEL_TRIM_EXTREME_COUNT = 2
MAX_CHANNEL_WIDTH_RATIO = 0.06
MAX_CHANNEL_CLOSE_RETURN_RATIO = 0.08
MIN_SIGNAL_BODY_RETURN_RATIO = 0.06
MIN_BREAKOUT_TO_CHANNEL_UPPER_RATIO = 1.03
MAX_CHANNEL_END_TO_BREAKOUT_GAP = 10
GOLDEN_BOWL_MAX_LENGTH = 12
GOLDEN_BOWL_MIN_WIDTH = 3
GOLDEN_BOWL_MIN_DEPTH_RATIO = 0.03
GOLDEN_BOWL_MAX_DEPTH_RATIO = 0.20
GOLDEN_BOWL_RIGHT_CLOSE_TO_LEFT_HIGH_RATIO = 0.98
ENTRY_TRIGGER_TO_LEFT_CLOSE_HIGH_RATIO = 1.01
MAX_LEFT_CLOSE_HIGH_TO_CHANNEL_END_CLOSE_RATIO = 1.12

CHANNEL_BREAKOUT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_pct_14",
    "volume_ratio_20",
)

GOLDEN_BOWL_CONFIG = GoldenBowlConfig(
    channel_length=CHANNEL_LENGTH,
    channel_trim_extreme_count=CHANNEL_TRIM_EXTREME_COUNT,
    max_channel_width_ratio=MAX_CHANNEL_WIDTH_RATIO,
    max_channel_close_return_ratio=MAX_CHANNEL_CLOSE_RETURN_RATIO,
    min_breakout_body_return_ratio=MIN_SIGNAL_BODY_RETURN_RATIO,
    min_breakout_to_channel_upper_ratio=MIN_BREAKOUT_TO_CHANNEL_UPPER_RATIO,
    max_channel_end_to_breakout_gap=MAX_CHANNEL_END_TO_BREAKOUT_GAP,
    max_left_high_to_channel_end_close_ratio=MAX_LEFT_CLOSE_HIGH_TO_CHANNEL_END_CLOSE_RATIO,
    max_bowl_width=GOLDEN_BOWL_MAX_LENGTH,
    min_bowl_width=GOLDEN_BOWL_MIN_WIDTH,
    min_bowl_depth_ratio=GOLDEN_BOWL_MIN_DEPTH_RATIO,
    max_bowl_depth_ratio=GOLDEN_BOWL_MAX_DEPTH_RATIO,
    right_close_to_left_high_ratio=GOLDEN_BOWL_RIGHT_CLOSE_TO_LEFT_HIGH_RATIO,
    require_right_bullish=True,
)

def channel_breakout_code_filter(code: str) -> bool:
    """Keep main-board common A-share codes; date-sensitive ST checks run later."""
    value = code.lower()
    if value.startswith("sh.688") or value.startswith("sz.300") or value.startswith("sz.301"):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


def channel_breakout_batch_signal_strategy(
    frame: StockDailyFrame,
    target_indices: list[int],
) -> dict[int, SignalDecision]:
    if not target_indices or len(frame) == 0:
        return {}

    columns = frame.columns
    opens = columns["qfq_open"]
    highs = columns["qfq_high"]
    lows = columns["qfq_low"]
    closes = columns["qfq_close"]
    atr_pct_14 = columns.get("atr_pct_14")
    volume_ratio_20 = columns.get("volume_ratio_20")

    with np.errstate(invalid="ignore", divide="ignore"):
        st_blocked = _st_blocked_series(columns)

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if index < CHANNEL_LENGTH + 1 or st_blocked[index]:
            continue

        close_t = float(closes[index])
        open_t = float(opens[index])
        if not (np.isfinite(close_t) and np.isfinite(open_t)):
            continue
        if close_t <= open_t:
            continue

        golden_bowl = resolve_golden_bowl(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            target_index=index,
            config=GOLDEN_BOWL_CONFIG,
            atr_pct_14=atr_pct_14,
            volume_ratio_20=volume_ratio_20,
        )
        if golden_bowl is None:
            continue

        breakout_index = golden_bowl.breakout_index
        channel = golden_bowl.channel
        left_close_high = golden_bowl.left_close_high
        channel_end_close = float(closes[channel.end_index])
        if not (
            np.isfinite(channel_end_close)
            and channel_end_close > 0
            and left_close_high
            <= channel_end_close * MAX_LEFT_CLOSE_HIGH_TO_CHANNEL_END_CLOSE_RATIO
        ):
            continue
        entry_trigger_price = left_close_high * ENTRY_TRIGGER_TO_LEFT_CLOSE_HIGH_RATIO

        results[index] = SignalDecision(
            triggered=True,
            signal_close=close_t,
            stop_losses=(),
            take_profits=(),
            max_watch_days=CHANNEL_BREAKOUT_MAX_WATCH_DAYS,
            extras={
                "pattern": "channel_breakout_pullback_retest",
                "breakout_date": frame.trade_dates[breakout_index].isoformat(),
                "channel_start": frame.trade_dates[channel.start_index].isoformat(),
                "channel_end": frame.trade_dates[channel.end_index].isoformat(),
                "channel_length": channel.length,
                "channel_slope": channel.slope,
                "channel_width_ratio": channel.channel_width_ratio,
                "channel_upper_line_end": channel.upper_line_end,
                "channel_lower_line_end": channel.lower_line_end,
                "channel_in_channel_ratio": channel.in_channel_ratio,
                "channel_exception_count": channel.exception_count,
                "channel_end_to_breakout_gap": golden_bowl.channel_end_to_breakout_gap,
                "channel_close_return": float(golden_bowl.channel_close_return),
                "signal_body_return": float(golden_bowl.breakout_body_return),
                "breakout_ratio": float(golden_bowl.breakout_ratio),
                "left_close_high": float(left_close_high),
                "left_close_high_date": (
                    frame.trade_dates[golden_bowl.left_close_high_index].isoformat()
                ),
                "bowl_trough_close": float(golden_bowl.trough_close),
                "bowl_trough_date": frame.trade_dates[golden_bowl.trough_index].isoformat(),
                "right_close_to_left_high": float(golden_bowl.right_close_ratio),
                "bowl_width": golden_bowl.bowl_width,
                "bowl_depth_ratio": float(golden_bowl.bowl_depth_ratio),
                "channel_end_close": float(channel_end_close),
                "left_close_high_to_channel_end_close": float(
                    left_close_high / channel_end_close
                ),
                "max_left_close_high_to_channel_end_close_ratio": (
                    MAX_LEFT_CLOSE_HIGH_TO_CHANNEL_END_CLOSE_RATIO
                ),
                "pullback_close": float(close_t),
                "entry_trigger_price": float(entry_trigger_price),
                "entry_trigger_to_left_close_high_ratio": (
                    ENTRY_TRIGGER_TO_LEFT_CLOSE_HIGH_RATIO
                ),
                "golden_bowl_max_length": GOLDEN_BOWL_MAX_LENGTH,
                "golden_bowl_min_width": GOLDEN_BOWL_MIN_WIDTH,
                "golden_bowl_min_depth_ratio": GOLDEN_BOWL_MIN_DEPTH_RATIO,
                "golden_bowl_max_depth_ratio": GOLDEN_BOWL_MAX_DEPTH_RATIO,
                "golden_bowl_right_close_to_left_high_ratio": (
                    GOLDEN_BOWL_RIGHT_CLOSE_TO_LEFT_HIGH_RATIO
                ),
                "max_watch_days": CHANNEL_BREAKOUT_MAX_WATCH_DAYS,
                "max_channel_width_ratio": MAX_CHANNEL_WIDTH_RATIO,
                "max_channel_close_return_ratio": MAX_CHANNEL_CLOSE_RETURN_RATIO,
                "min_signal_body_return_ratio": MIN_SIGNAL_BODY_RETURN_RATIO,
                "min_breakout_to_channel_upper_ratio": MIN_BREAKOUT_TO_CHANNEL_UPPER_RATIO,
                "max_channel_end_to_breakout_gap": MAX_CHANNEL_END_TO_BREAKOUT_GAP,
                "entry_rule": "watch_3d_intraday_left_close_high_retest",
                "exit_rule": "next_trade_day_open",
            },
        )
    return results


def channel_breakout_entry_strategy(
    *,
    bar: tuple[float, ...],
    watch: Any,
) -> float | None:
    signal = watch.signal or {}
    entry_trigger_price = _signal_value(signal, "entry_trigger_price")
    if not isinstance(entry_trigger_price, (int, float)):
        return None
    trigger = float(entry_trigger_price)
    if not (np.isfinite(trigger) and trigger > 0):
        return None

    open_price = float(bar[0])
    high_price = float(bar[1])
    if not (np.isfinite(open_price) and np.isfinite(high_price)):
        return None
    if high_price < trigger:
        return None
    buy_price = open_price if open_price >= trigger else trigger
    return buy_price


def _st_blocked_series(columns: dict[str, Any]) -> np.ndarray:
    is_st = columns.get("is_st")
    names = columns.get("name")
    size = len(columns["qfq_close"])
    blocked = np.zeros(size, dtype=bool)
    if is_st is not None:
        blocked |= np.nan_to_num(np.asarray(is_st, dtype=float), nan=0.0) == 1.0
    if names is not None:
        for position, name in enumerate(names):
            if name is None:
                continue
            text = str(name)
            if "st" in text.lower() or "*" in text:
                blocked[position] = True
    return blocked


def _signal_value(signal: dict[str, Any], key: str) -> Any:
    if key in signal:
        return signal[key]
    extras = signal.get("extras")
    if isinstance(extras, dict):
        return extras.get(key)
    return None
