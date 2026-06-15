from __future__ import annotations

from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame
from strategies.algorithms import detect_trend_channel_consolidation


CHANNEL_BREAKOUT_POSITION_FRACTION = 1.0 / 4.0
CHANNEL_BREAKOUT_MAX_HOLDING_DAYS = 1
CHANNEL_BREAKOUT_MAX_WATCH_DAYS = 12

CHANNEL_LENGTH = 20
CHANNEL_TRIM_EXTREME_COUNT = 2
MAX_CHANNEL_WIDTH_RATIO = 0.06
MAX_CHANNEL_CLOSE_RETURN_RATIO = 0.08
MIN_SIGNAL_BODY_RETURN_RATIO = 0.06
MIN_BREAKOUT_TO_CHANNEL_UPPER_RATIO = 1.03
MAX_RUNUP_DAYS = 5
ENTRY_TRIGGER_TO_LEFT_CLOSE_HIGH_RATIO = 1.01
ENTRY_BUY_PRICE_TO_PREV_MA10_FLOOR_RATIO = 1.03
ENTRY_BUY_PRICE_TO_PREV_MA10_CEILING_RATIO = 1.10
MAX_LEFT_CLOSE_HIGH_TO_CHANNEL_END_CLOSE_RATIO = 1.12

CHANNEL_BREAKOUT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_pct_14",
    "volume_ratio_20",
    "ma_10",
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
        prev_close = float(closes[index - 1])
        if not (np.isfinite(close_t) and np.isfinite(prev_close)):
            continue
        if close_t >= prev_close:
            continue

        breakout = _resolve_breakout_before_pullback(
            frame=frame,
            index=index,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            atr_pct_14=atr_pct_14,
            volume_ratio_20=volume_ratio_20,
        )
        if breakout is None:
            continue

        (
            breakout_index,
            channel,
            channel_close_return,
            signal_body_return,
            breakout_ratio,
            left_close_high,
            left_close_high_index,
        ) = breakout
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
                "channel_close_return": float(channel_close_return),
                "signal_body_return": float(signal_body_return),
                "breakout_ratio": float(breakout_ratio),
                "left_close_high": float(left_close_high),
                "left_close_high_date": frame.trade_dates[left_close_high_index].isoformat(),
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
                "entry_buy_price_to_prev_ma10_floor_ratio": (
                    ENTRY_BUY_PRICE_TO_PREV_MA10_FLOOR_RATIO
                ),
                "entry_buy_price_to_prev_ma10_ceiling_ratio": (
                    ENTRY_BUY_PRICE_TO_PREV_MA10_CEILING_RATIO
                ),
                "max_runup_days": MAX_RUNUP_DAYS,
                "max_watch_days": CHANNEL_BREAKOUT_MAX_WATCH_DAYS,
                "max_channel_width_ratio": MAX_CHANNEL_WIDTH_RATIO,
                "max_channel_close_return_ratio": MAX_CHANNEL_CLOSE_RETURN_RATIO,
                "min_signal_body_return_ratio": MIN_SIGNAL_BODY_RETURN_RATIO,
                "min_breakout_to_channel_upper_ratio": MIN_BREAKOUT_TO_CHANNEL_UPPER_RATIO,
                "entry_rule": "watch_intraday_left_close_high_retest",
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
    prev_ma10 = float(bar[6]) if len(bar) > 6 else float("nan")
    if not (
        np.isfinite(prev_ma10)
        and prev_ma10 > 0
    ):
        return None
    buy_to_prev_ma10 = buy_price / prev_ma10
    if not (
        ENTRY_BUY_PRICE_TO_PREV_MA10_FLOOR_RATIO
        <= buy_to_prev_ma10
        <= ENTRY_BUY_PRICE_TO_PREV_MA10_CEILING_RATIO
    ):
        return None
    return buy_price


def _resolve_breakout_before_pullback(
    *,
    frame: StockDailyFrame,
    index: int,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr_pct_14: np.ndarray | None,
    volume_ratio_20: np.ndarray | None,
) -> tuple[Any, ...] | None:
    first_breakout = max(CHANNEL_LENGTH, index - MAX_RUNUP_DAYS)
    for breakout_index in range(index - 1, first_breakout - 1, -1):
        if not _is_first_close_pullback(closes=closes, start_index=breakout_index, end_index=index):
            continue

        open_b = float(opens[breakout_index])
        close_b = float(closes[breakout_index])
        if not (np.isfinite(open_b) and np.isfinite(close_b) and open_b > 0):
            continue
        signal_body_return = (close_b - open_b) / open_b
        if signal_body_return < MIN_SIGNAL_BODY_RETURN_RATIO:
            continue

        channel_start = breakout_index - CHANNEL_LENGTH
        channel = detect_trend_channel_consolidation(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            start_index=channel_start,
            length=CHANNEL_LENGTH,
            trim_extreme_count=CHANNEL_TRIM_EXTREME_COUNT,
            max_channel_width_ratio=MAX_CHANNEL_WIDTH_RATIO,
            atr_pct_14=atr_pct_14,
            volume_ratio_20=volume_ratio_20,
        )
        if channel is None or channel.end_index != breakout_index - 1:
            continue

        channel_first_close = float(closes[channel.start_index])
        channel_last_close = float(closes[channel.end_index])
        if not (
            np.isfinite(channel_first_close)
            and np.isfinite(channel_last_close)
            and channel_first_close > 0
        ):
            continue
        channel_close_return = channel_last_close / channel_first_close - 1.0
        if channel_close_return > MAX_CHANNEL_CLOSE_RETURN_RATIO:
            continue

        breakout_ratio = (
            close_b / channel.upper_line_end
            if channel.upper_line_end > 0
            else float("nan")
        )
        if not (
            np.isfinite(breakout_ratio)
            and breakout_ratio >= MIN_BREAKOUT_TO_CHANNEL_UPPER_RATIO
        ):
            continue

        close_window = np.asarray(closes[breakout_index:index], dtype=float)
        if len(close_window) == 0 or not np.all(np.isfinite(close_window)):
            continue
        left_offset = int(np.argmax(close_window))
        left_close_high = float(close_window[left_offset])
        left_close_high_index = breakout_index + left_offset
        if not (np.isfinite(left_close_high) and float(closes[index]) < left_close_high):
            continue

        return (
            breakout_index,
            channel,
            channel_close_return,
            signal_body_return,
            breakout_ratio,
            left_close_high,
            left_close_high_index,
        )
    return None


def _is_first_close_pullback(
    *,
    closes: np.ndarray,
    start_index: int,
    end_index: int,
) -> bool:
    if start_index < 0 or end_index <= start_index:
        return False
    close_values = np.asarray(closes[start_index : end_index + 1], dtype=float)
    if len(close_values) < 2 or not np.all(np.isfinite(close_values)):
        return False
    runup_values = close_values[:-1]
    if len(runup_values) >= 2 and np.any(np.diff(runup_values) < 0):
        return False
    return close_values[-1] < close_values[-2]


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
