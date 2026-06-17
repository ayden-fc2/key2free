from __future__ import annotations

from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame
from strategies.algorithms import (
    GoldenBowlConfig,
    resolve_golden_bowl_bottom_bounce_after_ma_bull,
)


CHANNEL_BREAKOUT_POSITION_AMOUNT = 20000.0
CHANNEL_BREAKOUT_MAX_HOLDING_DAYS = 1
CHANNEL_BREAKOUT_MAX_WATCH_DAYS = 1

CHANNEL_LENGTH = 20
CHANNEL_TRIM_EXTREME_COUNT = 2
MIN_MA_BULL_DAYS = 9
MIN_SIGNAL_BODY_RETURN_RATIO = 0.02
MIN_BREAKOUT_TO_MA20_RATIO = 1.03
MAX_CHANNEL_END_TO_BREAKOUT_GAP = 10
GOLDEN_BOWL_MAX_LENGTH = 20
GOLDEN_BOWL_MIN_WIDTH = 2
GOLDEN_BOWL_MIN_DEPTH_RATIO = 0.02
GOLDEN_BOWL_MAX_DEPTH_RATIO = 0.20
GOLDEN_BOWL_RIGHT_CLOSE_TO_LEFT_HIGH_RATIO = 0.98
GOLDEN_BOWL_MAX_ORDER = 2
BOTTOM_BOUNCE_BULLISH_DAYS = 2
BOTTOM_BOUNCE_MAX_BODY_RETURN_RATIO = None
MAX_CLOSE_TO_MA10_DISTANCE_RATIO = 0.02
MIN_MA10_SLOPE_RATIO = 0.0
RECENT_BIG_DROP_LOOKBACK = 5
MAX_RECENT_DROP_RATIO = -0.04
SHORT_OVERHEAT_LOOKBACK = 5
MAX_SHORT_RISE_RATIO = 0.12
LONG_OVERHEAT_LOOKBACK = 10
MAX_LONG_RISE_RATIO = 0.20
PULLBACK_VOLUME_RECENT_DAYS = 3
PULLBACK_VOLUME_BASE_DAYS = 10
MAX_PULLBACK_VOLUME_RATIO = 0.80
MAX_NEXT_OPEN_TO_SIGNAL_CLOSE_RATIO = 1.0

CHANNEL_BREAKOUT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "ma_5",
    "ma_10",
    "ma_20",
)

GOLDEN_BOWL_CONFIG = GoldenBowlConfig(
    channel_length=CHANNEL_LENGTH,
    channel_trim_extreme_count=CHANNEL_TRIM_EXTREME_COUNT,
    max_channel_width_ratio=None,
    max_channel_close_return_ratio=None,
    min_breakout_body_return_ratio=MIN_SIGNAL_BODY_RETURN_RATIO,
    min_breakout_to_channel_upper_ratio=MIN_BREAKOUT_TO_MA20_RATIO,
    max_channel_end_to_breakout_gap=MAX_CHANNEL_END_TO_BREAKOUT_GAP,
    max_left_high_to_channel_end_close_ratio=None,
    max_bowl_order=GOLDEN_BOWL_MAX_ORDER,
    min_next_bowl_left_high_ratio=None,
    max_bowl_width=GOLDEN_BOWL_MAX_LENGTH,
    min_bowl_width=GOLDEN_BOWL_MIN_WIDTH,
    min_bowl_depth_ratio=GOLDEN_BOWL_MIN_DEPTH_RATIO,
    max_bowl_depth_ratio=GOLDEN_BOWL_MAX_DEPTH_RATIO,
    right_close_to_left_high_ratio=GOLDEN_BOWL_RIGHT_CLOSE_TO_LEFT_HIGH_RATIO,
    max_right_close_to_left_high_ratio=None,
    require_right_bullish=False,
    min_bottom_bounce_bullish_days=BOTTOM_BOUNCE_BULLISH_DAYS,
    max_bottom_bounce_body_return_ratio=BOTTOM_BOUNCE_MAX_BODY_RETURN_RATIO,
    require_bottom_bounce_bullish=False,
    require_bottom_bounce_low_non_decreasing=False,
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
    vols = columns["vol"]
    ma_5 = columns["ma_5"]
    ma_10 = columns["ma_10"]
    ma_20 = columns["ma_20"]

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
        if index < LONG_OVERHEAT_LOOKBACK:
            continue
        golden_bowl = resolve_golden_bowl_bottom_bounce_after_ma_bull(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            ma_5=ma_5,
            ma_10=ma_10,
            ma_20=ma_20,
            target_index=index,
            config=GOLDEN_BOWL_CONFIG,
            min_ma_bull_days=MIN_MA_BULL_DAYS,
        )
        if golden_bowl is None:
            continue

        breakout_index = golden_bowl.breakout_index
        left_close_high = golden_bowl.left_close_high
        bottom_low = golden_bowl.bottom_low
        if bottom_low is None or not np.isfinite(bottom_low) or bottom_low <= 0:
            continue
        if golden_bowl.ma_bull_days is None or golden_bowl.ma_bull_days < MIN_MA_BULL_DAYS:
            continue
        ma_bull_end = golden_bowl.ma_bull_end_index
        ma_bull_start = golden_bowl.ma_bull_start_index
        ma5_t = float(ma_5[index])
        ma10_t = float(ma_10[index])
        close_to_ma5 = close_t / ma5_t if np.isfinite(ma5_t) and ma5_t > 0 else None
        close_to_ma10 = close_t / ma10_t if np.isfinite(ma10_t) and ma10_t > 0 else None
        if close_to_ma10 is None or abs(close_to_ma10 - 1.0) > MAX_CLOSE_TO_MA10_DISTANCE_RATIO:
            continue
        ma10_slope_t = (
            ma10_t / float(ma_10[index - 1]) - 1.0
            if index > 0
            and np.isfinite(ma10_t)
            and np.isfinite(float(ma_10[index - 1]))
            and float(ma_10[index - 1]) > 0
            else None
        )
        if ma10_slope_t is None or ma10_slope_t <= MIN_MA10_SLOPE_RATIO:
            continue
        t_return = (
            close_t / float(closes[index - 1]) - 1.0
            if index > 0
            and np.isfinite(float(closes[index - 1]))
            and float(closes[index - 1]) > 0
            else None
        )
        recent_min_return = _min_close_return(
            closes=closes,
            end_index=index - 1,
            lookback=RECENT_BIG_DROP_LOOKBACK,
        )
        short_rise = _window_close_return(
            closes=closes,
            start_index=index - SHORT_OVERHEAT_LOOKBACK,
            end_index=index,
        )
        long_rise = _window_close_return(
            closes=closes,
            start_index=index - LONG_OVERHEAT_LOOKBACK,
            end_index=index,
        )
        pullback_volume_ratio = _volume_ratio(
            vols=vols,
            recent_start=index - PULLBACK_VOLUME_RECENT_DAYS + 1,
            recent_end=index,
            base_start=index - PULLBACK_VOLUME_BASE_DAYS,
            base_end=index - PULLBACK_VOLUME_RECENT_DAYS,
        )
        if recent_min_return is None or recent_min_return <= MAX_RECENT_DROP_RATIO:
            continue
        if short_rise is None or short_rise > MAX_SHORT_RISE_RATIO:
            continue
        if long_rise is None or long_rise > MAX_LONG_RISE_RATIO:
            continue
        if pullback_volume_ratio is None or pullback_volume_ratio > MAX_PULLBACK_VOLUME_RATIO:
            continue
        ma20_breakout_prev = (
            float(ma_20[ma_bull_end])
            if ma_bull_end is not None and ma_bull_end >= 0
            else float("nan")
        )

        results[index] = SignalDecision(
            triggered=True,
            signal_close=close_t,
            stop_losses=(),
            take_profits=(),
            max_watch_days=CHANNEL_BREAKOUT_MAX_WATCH_DAYS,
            extras={
                "pattern": "ma_bull_golden_bowl_ma10_pullback_open_to_open",
                "breakout_date": frame.trade_dates[breakout_index].isoformat(),
                "background": "ma_bull_alignment",
                "ma_bull_start": (
                    None
                    if ma_bull_start is None
                    else frame.trade_dates[ma_bull_start].isoformat()
                ),
                "ma_bull_end": (
                    None
                    if ma_bull_end is None
                    else frame.trade_dates[ma_bull_end].isoformat()
                ),
                "ma_bull_days": golden_bowl.ma_bull_days,
                "ma5_breakout_prev": (
                    None
                    if ma_bull_end is None
                    else float(ma_5[ma_bull_end])
                ),
                "ma10_breakout_prev": (
                    None
                    if ma_bull_end is None
                    else float(ma_10[ma_bull_end])
                ),
                "ma20_breakout_prev": ma20_breakout_prev,
                "bowl_order": golden_bowl.bowl_order,
                "channel_end_to_breakout_gap": None,
                "channel_close_return": None,
                "signal_body_return": float(golden_bowl.breakout_body_return),
                "breakout_ratio": float(golden_bowl.breakout_ratio),
                "left_close_high": float(left_close_high),
                "left_close_high_date": (
                    frame.trade_dates[golden_bowl.left_close_high_index].isoformat()
                ),
                "bowl_trough_close": float(golden_bowl.trough_close),
                "bowl_trough_date": frame.trade_dates[golden_bowl.trough_index].isoformat(),
                "bottom_low": float(bottom_low),
                "bottom_low_date": (
                    None
                    if golden_bowl.bottom_low_index is None
                    else frame.trade_dates[golden_bowl.bottom_low_index].isoformat()
                ),
                "bounce_days": golden_bowl.bounce_days,
                "bounce_body_return_1": golden_bowl.bounce_body_return_1,
                "bounce_body_return_2": golden_bowl.bounce_body_return_2,
                "bottom_bounce_max_body_return_ratio": BOTTOM_BOUNCE_MAX_BODY_RETURN_RATIO,
                "right_close_to_left_high": float(golden_bowl.right_close_ratio),
                "bowl_width": golden_bowl.bowl_width,
                "bowl_depth_ratio": float(golden_bowl.bowl_depth_ratio),
                "close_to_ma5": close_to_ma5,
                "close_to_ma10": close_to_ma10,
                "ma10_slope_t": ma10_slope_t,
                "t_return": t_return,
                "recent_min_return_5": recent_min_return,
                "short_rise_5": short_rise,
                "long_rise_10": long_rise,
                "pullback_volume_ratio": pullback_volume_ratio,
                "max_close_to_ma10_distance_ratio": MAX_CLOSE_TO_MA10_DISTANCE_RATIO,
                "min_ma10_slope_ratio": MIN_MA10_SLOPE_RATIO,
                "recent_big_drop_lookback": RECENT_BIG_DROP_LOOKBACK,
                "max_recent_drop_ratio": MAX_RECENT_DROP_RATIO,
                "short_overheat_lookback": SHORT_OVERHEAT_LOOKBACK,
                "max_short_rise_ratio": MAX_SHORT_RISE_RATIO,
                "long_overheat_lookback": LONG_OVERHEAT_LOOKBACK,
                "max_long_rise_ratio": MAX_LONG_RISE_RATIO,
                "pullback_volume_recent_days": PULLBACK_VOLUME_RECENT_DAYS,
                "pullback_volume_base_days": PULLBACK_VOLUME_BASE_DAYS,
                "max_pullback_volume_ratio": MAX_PULLBACK_VOLUME_RATIO,
                "open_t1_to_close_t": None,
                "open_t1_to_close_t_rule": "filled_after_buy_as_buy_price / signal_close - 1",
                "previous_bowl_signal_date": (
                    None
                    if golden_bowl.previous_signal_index is None
                    else frame.trade_dates[golden_bowl.previous_signal_index].isoformat()
                ),
                "previous_bowl_left_close_high": golden_bowl.previous_left_close_high,
                "channel_end_close": None,
                "left_close_high_to_channel_end_close": None,
                "left_close_high_to_ma20_breakout_prev": (
                    float(left_close_high / ma20_breakout_prev)
                    if np.isfinite(ma20_breakout_prev) and ma20_breakout_prev > 0
                    else None
                ),
                "pullback_close": float(close_t),
                "entry_price_rule": "next_trade_day_open",
                "exit_price_rule": "next_next_trade_day_open",
                "golden_bowl_max_length": GOLDEN_BOWL_MAX_LENGTH,
                "golden_bowl_min_width": GOLDEN_BOWL_MIN_WIDTH,
                "golden_bowl_min_depth_ratio": GOLDEN_BOWL_MIN_DEPTH_RATIO,
                "golden_bowl_max_depth_ratio": GOLDEN_BOWL_MAX_DEPTH_RATIO,
                "golden_bowl_right_close_to_left_high_ratio": (
                    GOLDEN_BOWL_RIGHT_CLOSE_TO_LEFT_HIGH_RATIO
                ),
                "golden_bowl_max_order": GOLDEN_BOWL_MAX_ORDER,
                "bottom_bounce_bullish_days": BOTTOM_BOUNCE_BULLISH_DAYS,
                "min_ma_bull_days": MIN_MA_BULL_DAYS,
                "max_watch_days": CHANNEL_BREAKOUT_MAX_WATCH_DAYS,
                "min_signal_body_return_ratio": MIN_SIGNAL_BODY_RETURN_RATIO,
                "min_breakout_to_ma20_ratio": MIN_BREAKOUT_TO_MA20_RATIO,
                "max_channel_end_to_breakout_gap": None,
                "entry_rule": "t_plus_1_open_not_above_signal_close",
                "max_next_open_to_signal_close_ratio": MAX_NEXT_OPEN_TO_SIGNAL_CLOSE_RATIO,
                "exit_rule": "t_plus_2_open",
            },
        )
    return results


def channel_breakout_entry_strategy(
    *,
    bar: tuple[float, ...],
    watch: Any,
) -> float | None:
    signal_close = _signal_value(watch.signal or {}, "signal_close")
    if not isinstance(signal_close, (int, float)):
        return None
    signal_close = float(signal_close)
    open_price = float(bar[0])
    if not (
        np.isfinite(signal_close)
        and signal_close > 0
        and np.isfinite(open_price)
        and open_price > 0
    ):
        return None
    if open_price > signal_close * MAX_NEXT_OPEN_TO_SIGNAL_CLOSE_RATIO:
        return None
    return open_price


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


def _min_close_return(
    *,
    closes: np.ndarray,
    end_index: int,
    lookback: int,
) -> float | None:
    start = end_index - lookback + 1
    if start <= 0:
        return None
    values: list[float] = []
    for index in range(start, end_index + 1):
        previous = float(closes[index - 1])
        close = float(closes[index])
        if not (np.isfinite(previous) and previous > 0 and np.isfinite(close)):
            return None
        values.append(close / previous - 1.0)
    return min(values) if values else None


def _window_close_return(
    *,
    closes: np.ndarray,
    start_index: int,
    end_index: int,
) -> float | None:
    if start_index < 0 or end_index <= start_index:
        return None
    start_close = float(closes[start_index])
    end_close = float(closes[end_index])
    if not (np.isfinite(start_close) and start_close > 0 and np.isfinite(end_close)):
        return None
    return end_close / start_close - 1.0


def _volume_ratio(
    *,
    vols: np.ndarray,
    recent_start: int,
    recent_end: int,
    base_start: int,
    base_end: int,
) -> float | None:
    if recent_start < 0 or base_start < 0 or recent_end < recent_start or base_end < base_start:
        return None
    recent = np.asarray(vols[recent_start : recent_end + 1], dtype=float)
    base = np.asarray(vols[base_start : base_end + 1], dtype=float)
    if (
        len(recent) == 0
        or len(base) == 0
        or not np.all(np.isfinite(recent))
        or not np.all(np.isfinite(base))
    ):
        return None
    base_avg = float(np.mean(base))
    if base_avg <= 0:
        return None
    return float(np.mean(recent) / base_avg)


def _signal_value(signal: dict[str, Any], key: str) -> Any:
    if key in signal:
        return signal[key]
    extras = signal.get("extras")
    if isinstance(extras, dict):
        return extras.get(key)
    return None

