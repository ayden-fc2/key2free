from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.entities.stock_data_context import SignalDecision, StockDataContext


HISTORY_WINDOW = 430
MAX_WATCH_DAYS = 2
MA20_WINDOW = 20
MA20_SLOPE_WINDOW = 10
MAX_MA20_SLOPE_IMPROVING_DAYS = 5
MIN_MA20_SLOPE_IMPROVING_STEPS = 3
MA30_WINDOW = 30
MA30_SLOPE_WINDOW = 10
MA30_STRUCTURE_DAYS = 400
MIN_MA30_TURN_POINTS = 5
MAX_MA30_TURN_POINTS = 10
RECENT_TURN_POINTS = 5
RECENT_LOW_COUNT = 4
MIN_LOW_STRUCTURE_SPAN_DAYS = 144
STRUCTURE_NOISE_ATR_MULTIPLE = 1.0
RECENT_SUPPORT_LOOKBACK = 6
RECENT_LOW_MAX_ABOVE_L4_ATR_MULTIPLE = 1.0
RECENT_LOW_MAX_BELOW_L4_ATR_MULTIPLE = 1.618
POST_L4_CLOSE_MAX_BELOW_L4_ATR_MULTIPLE = 1.0
CURRENT_CLOSE_MAX_ABOVE_L4_STRONG_ATR_MULTIPLE = 1.618
CURRENT_CLOSE_MAX_ABOVE_L4_NORMAL_ATR_MULTIPLE = 1.0
CURRENT_CLOSE_MAX_ABOVE_RECENT_LOW_ATR_MULTIPLE = 1.2
ATR30_WINDOW = 30

ATR14_WINDOW = 14
VOLUME_AVG_WINDOW = 10
VOLUME_AVG_MIN_RATIO = 0.8
LONG_BODY_MIN_RATIO = 0.8
LONG_BODY_ATR_MULTIPLE = 0.618
SMALL_CANDLE_ATR_MULTIPLE = 0.6
BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO = 0.618
PIERCING_CURRENT_BODY_MIN_RATIO = 0.618

MACD_DIVERGENCE_LOOKBACK = 120
PIVOT_NEIGHBOR_WINDOW = 3
MIN_PRICE_HIGHER_HIGH_RATIO = 0.01
MIN_MACD_WEAKEN_RATIO = 0.05
MACD_ZERO_EPSILON = 1e-9

LOW_CHANGE_FLAT = "震"
LOW_CHANGE_RISE = "涨"
LOW_CHANGE_FALL = "跌"

ALLOWED_LOW_PATTERNS = {
    (LOW_CHANGE_FLAT, LOW_CHANGE_FLAT, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FALL, LOW_CHANGE_FLAT, LOW_CHANGE_RISE),
    (LOW_CHANGE_FALL, LOW_CHANGE_RISE, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FALL, LOW_CHANGE_RISE, LOW_CHANGE_RISE),
    (LOW_CHANGE_FLAT, LOW_CHANGE_RISE, LOW_CHANGE_RISE),
    (LOW_CHANGE_RISE, LOW_CHANGE_FLAT, LOW_CHANGE_RISE),
    (LOW_CHANGE_RISE, LOW_CHANGE_RISE, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FLAT, LOW_CHANGE_FLAT, LOW_CHANGE_RISE),
    (LOW_CHANGE_RISE, LOW_CHANGE_FLAT, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FLAT, LOW_CHANGE_RISE, LOW_CHANGE_FLAT),
    (LOW_CHANGE_RISE, LOW_CHANGE_RISE, LOW_CHANGE_RISE),
}
@dataclass(frozen=True)
class _TrendSignalContext:
    l4_low: float
    l4_atr30: float
    l3_l4_high: float


def demo_signal_strategy(context: StockDataContext) -> SignalDecision:
    if not _passes_universe_filter(context):
        return SignalDecision(triggered=False)
    trend_context = _resolve_trend_signal_context(context.bars_1d_qfq)
    if trend_context is None:
        return SignalDecision(triggered=False)
    if not _passes_kline_filter(context.bars_1d_qfq):
        return SignalDecision(triggered=False)
    return SignalDecision(
        triggered=True,
        min_stop_loss=trend_context.l4_low - trend_context.l4_atr30,
        reference_take_profit=trend_context.l3_l4_high - 1.618 * trend_context.l4_atr30,
        signal_atr30=trend_context.l4_atr30,
        ideal_buy_price=trend_context.l4_low + trend_context.l4_atr30,
        max_watch_days=MAX_WATCH_DAYS,
    )


def demo_universe_filter(context: StockDataContext) -> bool:
    return _passes_universe_filter(context)


def demo_entry_strategy(
    *,
    open_price: Any,
    close_price: Any,
    high_price: Any,
    low_price: Any,
    min_stop_loss: Any,
    reference_take_profit: Any,
    signal_atr30: Any,
    ideal_buy_price: Any,
) -> float | int:
    open_value = _to_float(open_price)
    high_value = _to_float(high_price)
    low_value = _to_float(low_price)
    ideal_buy_value = _to_float(ideal_buy_price)
    if open_value is None or high_value is None or low_value is None or ideal_buy_value is None:
        return -1
    if open_value <= 0 or high_value <= 0 or low_value <= 0 or ideal_buy_value <= 0:
        return -1
    if open_value > ideal_buy_value:
        return open_value
    if _is_price_inside_range(ideal_buy_value, low_value, high_value):
        return ideal_buy_value
    return -1


def demo_exit_strategy(
    *,
    open_price: Any,
    close_price: Any,
    high_price: Any,
    low_price: Any,
    buy_date: Any,
    min_stop_loss: Any,
    reference_take_profit: Any,
    signal_atr30: Any,
) -> float | int:
    open_value = _to_float(open_price)
    high_value = _to_float(high_price)
    low_value = _to_float(low_price)
    min_stop_value = _to_float(min_stop_loss)
    take_profit_value = _to_float(reference_take_profit)
    atr_value = _to_float(signal_atr30)
    if open_value is None or high_value is None or low_value is None:
        return -1
    if open_value <= 0 or high_value <= 0 or low_value <= 0:
        return -1

    if min_stop_value is not None and _is_price_inside_range(min_stop_value, low_value, high_value):
        return min_stop_value
    if take_profit_value is not None and _is_price_inside_range(take_profit_value, low_value, high_value):
        return take_profit_value
    if atr_value is not None and atr_value > 0:
        atr_stop = open_value - atr_value * 0.618
        if _is_price_inside_range(atr_stop, low_value, high_value):
            return atr_stop
    return -1


def _is_price_inside_range(price: float, low_value: float, high_value: float) -> bool:
    return price > 0 and low_value <= price <= high_value


def _passes_universe_filter(context: StockDataContext) -> bool:
    code = context.code.lower()
    code_name = str(context.universe.get("code_name") or "")
    security_type = context.universe.get("security_type")
    list_status = context.universe.get("list_status")

    if security_type != 1 or list_status != 1:
        return False
    if code.startswith("sh.688") or code.startswith("sz.300") or code.startswith("sz.301"):
        return False
    if "st" in code_name.lower() or "＊" in code_name or "*" in code_name:
        return False
    return code.startswith("sh.6") or code.startswith("sz.0")


def _passes_trend_filter(bars: list[dict[str, Any]]) -> bool:
    return _resolve_trend_signal_context(bars) is not None


def _resolve_trend_signal_context(bars: list[dict[str, Any]]) -> _TrendSignalContext | None:
    if len(bars) < HISTORY_WINDOW:
        return None

    window_bars = bars[-HISTORY_WINDOW:]
    closes = [_to_float(item.get("close")) for item in window_bars]
    highs = [_to_float(item.get("high")) for item in window_bars]
    lows = [_to_float(item.get("low")) for item in window_bars]
    if any(value is None for value in closes):
        return None
    if any(value is None for value in highs):
        return None
    if any(value is None for value in lows):
        return None

    ma30 = _moving_average(closes, MA30_WINDOW)
    atr30 = _average_true_range(highs, lows, closes, ATR30_WINDOW)
    ma30_points = [
        (index, value)
        for index, value in enumerate(ma30)
        if value is not None
    ]
    if len(ma30_points) < MA30_STRUCTURE_DAYS:
        return None

    ma30_points = ma30_points[-MA30_STRUCTURE_DAYS:]
    ma30_indices = [item[0] for item in ma30_points]
    ma30_values = [item[1] for item in ma30_points]
    ma30_slopes = _rolling_linear_slopes(ma30_values, MA30_SLOPE_WINDOW)
    turn_positions = _find_negative_to_positive_turn_points(ma30_slopes)
    if not (MIN_MA30_TURN_POINTS <= len(turn_positions) <= MAX_MA30_TURN_POINTS):
        return None

    recent_turn_indices = [ma30_indices[position] for position in turn_positions[-RECENT_TURN_POINTS:]]
    low_points = _extract_interval_low_points(
        lows=lows,
        atr30=atr30,
        turn_indices=recent_turn_indices,
    )
    if low_points is None:
        return None
    if low_points[-1][0] - low_points[0][0] < MIN_LOW_STRUCTURE_SPAN_DAYS:
        return None

    low_pattern = _classify_low_changes(low_points)
    if low_pattern not in ALLOWED_LOW_PATTERNS:
        return None

    if not _is_recent_low_inside_last_structure_low_zone(lows, low_points[-1]):
        return None
    if not _is_current_close_near_l4(lows, closes, low_points[-1], low_pattern):
        return None
    if not _is_post_l4_price_above_support(lows, closes, low_points[-1]):
        return None
    if not _is_recent_ma20_slope_improving(closes):
        return None

    l3_index = low_points[-2][0]
    l4_index, l4_low, l4_atr30 = low_points[-1]
    l3_l4_high = _max_between(highs, l3_index, l4_index)
    if l3_l4_high is None:
        return None
    return _TrendSignalContext(
        l4_low=l4_low,
        l4_atr30=l4_atr30,
        l3_l4_high=l3_l4_high,
    )


def _extract_interval_low_points(
    *,
    lows: list[float | None],
    atr30: list[float | None],
    turn_indices: list[int],
) -> list[tuple[int, float, float]] | None:
    if len(turn_indices) != RECENT_TURN_POINTS:
        return None

    low_points: list[tuple[int, float, float]] = []
    for start_index, end_index in zip(turn_indices, turn_indices[1:]):
        segment = lows[start_index : end_index + 1]
        if len(segment) < 2 or any(value is None for value in segment):
            return None
        local_index, low_value = min(
            enumerate(segment),
            key=lambda item: item[1] if item[1] is not None else float("inf"),
        )
        low_index = start_index + local_index
        low_atr = atr30[low_index]
        if low_value is None or low_atr is None or low_atr <= 0:
            return None
        low_points.append((low_index, low_value, low_atr))

    return low_points if len(low_points) == RECENT_LOW_COUNT else None


def _classify_low_changes(low_points: list[tuple[int, float, float]]) -> tuple[str, ...]:
    if len(low_points) != RECENT_LOW_COUNT:
        return tuple()

    changes: list[str] = []
    for (_previous_index, previous_low, _previous_atr), (_next_index, next_low, next_atr) in zip(
        low_points,
        low_points[1:],
    ):
        delta = next_low - previous_low
        threshold = next_atr * STRUCTURE_NOISE_ATR_MULTIPLE
        if delta > threshold:
            changes.append(LOW_CHANGE_RISE)
        elif delta < -threshold:
            changes.append(LOW_CHANGE_FALL)
        else:
            changes.append(LOW_CHANGE_FLAT)
    return tuple(changes)


def _is_recent_low_inside_last_structure_low_zone(
    lows: list[float | None],
    last_low_point: tuple[int, float, float],
) -> bool:
    _low_index, low_value, low_atr = last_low_point
    recent_low = _resolve_recent_low(lows)
    if recent_low is None:
        return False
    lower_bound = low_value - low_atr * RECENT_LOW_MAX_BELOW_L4_ATR_MULTIPLE
    upper_bound = low_value + low_atr * RECENT_LOW_MAX_ABOVE_L4_ATR_MULTIPLE
    return lower_bound <= recent_low <= upper_bound


def _is_current_close_near_l4(
    lows: list[float | None],
    closes: list[float | None],
    last_low_point: tuple[int, float, float],
    low_pattern: tuple[str, ...],
) -> bool:
    current_close = closes[-1] if closes else None
    if current_close is None:
        return False
    _low_index, low_value, low_atr = last_low_point
    recent_low = _resolve_recent_low(lows)
    if recent_low is None:
        return False
    upper_multiple = (
        CURRENT_CLOSE_MAX_ABOVE_L4_STRONG_ATR_MULTIPLE
        if _low_pattern_rise_count(low_pattern) >= 2
        else CURRENT_CLOSE_MAX_ABOVE_L4_NORMAL_ATR_MULTIPLE
    )
    return (
        current_close <= low_value + low_atr * upper_multiple
        and current_close <= recent_low + low_atr * CURRENT_CLOSE_MAX_ABOVE_RECENT_LOW_ATR_MULTIPLE
    )


def _resolve_recent_low(lows: list[float | None]) -> float | None:
    recent_lows = lows[-RECENT_SUPPORT_LOOKBACK:]
    if len(recent_lows) < RECENT_SUPPORT_LOOKBACK or any(value is None for value in recent_lows):
        return None
    return min(value for value in recent_lows if value is not None)


def _max_between(values: list[float | None], start_index: int, end_index: int) -> float | None:
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    segment = values[start_index : end_index + 1]
    if not segment or any(value is None for value in segment):
        return None
    return max(value for value in segment if value is not None)


def _is_post_l4_price_above_support(
    lows: list[float | None],
    closes: list[float | None],
    last_low_point: tuple[int, float, float],
) -> bool:
    low_index, low_value, low_atr = last_low_point
    post_l4_lows = lows[low_index:]
    post_l4_closes = closes[low_index:]
    if not post_l4_lows or not post_l4_closes:
        return False
    if any(value is None for value in post_l4_lows):
        return False
    if any(value is None for value in post_l4_closes):
        return False
    low_lower_bound = low_value - low_atr * RECENT_LOW_MAX_BELOW_L4_ATR_MULTIPLE
    close_lower_bound = low_value - low_atr * POST_L4_CLOSE_MAX_BELOW_L4_ATR_MULTIPLE
    return (
        min(value for value in post_l4_lows if value is not None) >= low_lower_bound
        and min(value for value in post_l4_closes if value is not None) >= close_lower_bound
    )


def _low_pattern_rise_count(low_pattern: tuple[str, ...]) -> int:
    return sum(1 for item in low_pattern if item == LOW_CHANGE_RISE)


def _is_recent_ma20_slope_improving(closes: list[float | None]) -> bool:
    ma20 = _moving_average(closes, MA20_WINDOW)
    slopes = _rolling_linear_slopes(ma20, MA20_SLOPE_WINDOW)
    recent_slopes = slopes[-MAX_MA20_SLOPE_IMPROVING_DAYS:]
    if len(recent_slopes) < MAX_MA20_SLOPE_IMPROVING_DAYS:
        return False
    if any(value is None for value in recent_slopes):
        return False

    improving_steps = 0
    for previous, current in zip(recent_slopes, recent_slopes[1:]):
        if previous is None or current is None:
            return False
        if current > previous:
            improving_steps += 1
    return improving_steps >= MIN_MA20_SLOPE_IMPROVING_STEPS


def _passes_kline_filter(bars: list[dict[str, Any]]) -> bool:
    min_bars = max(ATR14_WINDOW + 1, VOLUME_AVG_WINDOW + 1, 5)
    if len(bars) < min_bars:
        return False

    opens = [_to_float(item.get("open")) for item in bars]
    highs = [_to_float(item.get("high")) for item in bars]
    lows = [_to_float(item.get("low")) for item in bars]
    closes = [_to_float(item.get("close")) for item in bars]
    volumes = [_to_float(item.get("volume")) for item in bars]
    if any(value is None for value in opens[-min_bars:]):
        return False
    if any(value is None for value in highs[-min_bars:]):
        return False
    if any(value is None for value in lows[-min_bars:]):
        return False
    if any(value is None for value in closes[-min_bars:]):
        return False
    if any(value is None for value in volumes[-min_bars:]):
        return False

    atr14 = _average_true_range(highs, lows, closes, ATR14_WINDOW)
    candles = [
        _build_candle(
            open_value=open_value,
            high_value=high_value,
            low_value=low_value,
            close_value=close_value,
        )
        for open_value, high_value, low_value, close_value in zip(opens, highs, lows, closes)
    ]
    if any(candle is None for candle in candles[-5:]):
        return False

    current_index = len(candles) - 1
    current_atr = atr14[current_index]
    if current_atr is None or current_atr <= 0:
        return False

    return (
        _is_dragonfly_doji(candles, volumes, current_index)
        or _is_hammer(candles, volumes, current_index)
        or _is_morning_star(candles, atr14, current_index)
        or _is_bullish_engulfing(candles, atr14, current_index)
        or _is_fairy_guide(candles, atr14, current_index)
    )


def _build_candle(
    *,
    open_value: float | None,
    high_value: float | None,
    low_value: float | None,
    close_value: float | None,
) -> dict[str, float] | None:
    if open_value is None or high_value is None or low_value is None or close_value is None:
        return None
    total = high_value - low_value
    if total <= 0:
        return None
    body = abs(close_value - open_value)
    upper_shadow = high_value - max(open_value, close_value)
    lower_shadow = min(open_value, close_value) - low_value
    return {
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "total": total,
        "body": body,
        "upper_shadow": max(upper_shadow, 0.0),
        "lower_shadow": max(lower_shadow, 0.0),
    }


def _is_bullish(candle: dict[str, float]) -> bool:
    return candle["close"] > candle["open"]


def _is_bearish(candle: dict[str, float]) -> bool:
    return candle["close"] < candle["open"]


def _body_ratio(candle: dict[str, float]) -> float:
    return candle["body"] / candle["total"] if candle["total"] > 0 else 0.0


def _is_long_body(
    candle: dict[str, float],
    atr14: list[float | None],
    index: int,
) -> bool:
    atr_value = atr14[index]
    if atr_value is None or atr_value <= 0:
        return False
    return _body_ratio(candle) >= LONG_BODY_MIN_RATIO and candle["body"] >= atr_value * LONG_BODY_ATR_MULTIPLE


def _is_volume_above_recent_average(volumes: list[float | None], index: int) -> bool:
    if index < VOLUME_AVG_WINDOW:
        return False
    current = volumes[index]
    recent_values = volumes[index - VOLUME_AVG_WINDOW : index]
    if current is None or any(value is None for value in recent_values):
        return False
    average_volume = sum(value for value in recent_values if value is not None) / VOLUME_AVG_WINDOW
    return current >= average_volume * VOLUME_AVG_MIN_RATIO


def _shadow_ratio_at_least(
    *,
    long_shadow: float,
    short_shadow: float,
    multiple: float,
) -> bool:
    if long_shadow <= 0:
        return False
    if short_shadow <= 0:
        return True
    return long_shadow / short_shadow >= multiple


def _is_dragonfly_doji(
    candles: list[dict[str, float] | None],
    volumes: list[float | None],
    index: int,
) -> bool:
    candle = candles[index]
    if candle is None:
        return False
    return (
        _body_ratio(candle) <= 0.1
        and _shadow_ratio_at_least(
            long_shadow=candle["lower_shadow"],
            short_shadow=candle["upper_shadow"],
            multiple=6,
        )
        and _is_volume_above_recent_average(volumes, index)
    )


def _is_hammer_shape(candle: dict[str, float]) -> bool:
    body_ratio = _body_ratio(candle)
    return (
        0.1 <= body_ratio <= 0.4
        and _shadow_ratio_at_least(
            long_shadow=candle["lower_shadow"],
            short_shadow=candle["upper_shadow"],
            multiple=4,
        )
    )


def _is_inverted_hammer_shape(candle: dict[str, float]) -> bool:
    body_ratio = _body_ratio(candle)
    return (
        0.1 <= body_ratio <= 0.4
        and _shadow_ratio_at_least(
            long_shadow=candle["upper_shadow"],
            short_shadow=candle["lower_shadow"],
            multiple=4,
        )
    )


def _is_hammer(
    candles: list[dict[str, float] | None],
    volumes: list[float | None],
    index: int,
) -> bool:
    candle = candles[index]
    if candle is None:
        return False
    return _is_hammer_shape(candle) and _is_volume_above_recent_average(volumes, index)


def _is_morning_star(
    candles: list[dict[str, float] | None],
    atr14: list[float | None],
    current_index: int,
) -> bool:
    current = candles[current_index]
    if current is None or not _is_bullish(current) or not _is_long_body(current, atr14, current_index):
        return False

    earliest_index = max(0, current_index - 4)
    latest_left_index = current_index - 2
    for left_index in range(earliest_index, latest_left_index + 1):
        left = candles[left_index]
        if left is None or not _is_bearish(left) or not _is_long_body(left, atr14, left_index):
            continue
        middle_candles = candles[left_index + 1 : current_index]
        if 1 <= len(middle_candles) <= 3 and all(
            candle is not None and candle["total"] <= _atr_value_or_zero(atr14[index]) * SMALL_CANDLE_ATR_MULTIPLE
            for index, candle in zip(range(left_index + 1, current_index), middle_candles)
        ):
            return True
    return False


def _is_bullish_engulfing(
    candles: list[dict[str, float] | None],
    atr14: list[float | None],
    current_index: int,
) -> bool:
    if current_index <= 0:
        return False
    current = candles[current_index]
    previous = candles[current_index - 1]
    if current is None or previous is None:
        return False
    current_low = min(current["open"], current["close"])
    current_high = max(current["open"], current["close"])
    previous_low = min(previous["open"], previous["close"])
    previous_high = max(previous["open"], previous["close"])
    return (
        _is_bullish(current)
        and _is_bearish(previous)
        and _is_long_body(current, atr14, current_index)
        and _is_long_body(previous, atr14, current_index - 1)
        and previous["body"] >= current["body"] * BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO
        and current_low <= previous_low
        and current_high >= previous_high
    )


def _is_piercing_like(
    candles: list[dict[str, float] | None],
    atr14: list[float | None],
    current_index: int,
) -> bool:
    if current_index <= 0:
        return False
    current = candles[current_index]
    previous = candles[current_index - 1]
    if current is None or previous is None:
        return False
    current_low = min(current["open"], current["close"])
    current_high = max(current["open"], current["close"])
    previous_low = min(previous["open"], previous["close"])
    previous_high = max(previous["open"], previous["close"])
    previous_body = previous["body"]
    return (
        _is_bullish(current)
        and _is_bearish(previous)
        and _is_long_body(current, atr14, current_index)
        and previous_body > 0
        and current_low >= previous_low
        and current_high <= previous_high
        and current["body"] >= previous_body * PIERCING_CURRENT_BODY_MIN_RATIO
    )


def _is_fairy_guide(
    candles: list[dict[str, float] | None],
    atr14: list[float | None],
    current_index: int,
) -> bool:
    if current_index <= 0:
        return False
    current = candles[current_index]
    previous = candles[current_index - 1]
    if current is None or previous is None:
        return False
    return (
        _is_bullish(current)
        and _is_long_body(current, atr14, current_index)
        and _is_inverted_hammer_shape(previous)
        and current["close"] > previous["high"]
    )


def _atr_value_or_zero(value: float | None) -> float:
    return value if value is not None and value > 0 else 0.0


def _has_bearish_macd_divergence(closes: list[float | None]) -> bool:
    valid_closes = [value for value in closes if value is not None]
    if len(valid_closes) < MACD_DIVERGENCE_LOOKBACK:
        return False

    dif, _dea, macd_hist = _macd(valid_closes)
    start_index = len(valid_closes) - MACD_DIVERGENCE_LOOKBACK
    pivot_indices = _find_price_high_pivots(
        valid_closes,
        start_index=start_index,
        end_index=len(valid_closes) - 1,
    )
    if len(pivot_indices) < 2:
        return False

    for previous_index, current_index in zip(pivot_indices, pivot_indices[1:]):
        previous_price = valid_closes[previous_index]
        current_price = valid_closes[current_index]
        if current_price <= previous_price * (1 + MIN_PRICE_HIGHER_HIGH_RATIO):
            continue
        if _is_indicator_weaker(dif[previous_index], dif[current_index]):
            return True
        if _is_indicator_weaker(macd_hist[previous_index], macd_hist[current_index]):
            return True
    return False


def _find_price_high_pivots(
    values: list[float],
    *,
    start_index: int,
    end_index: int,
) -> list[int]:
    pivots: list[int] = []
    start = max(start_index, PIVOT_NEIGHBOR_WINDOW)
    end = min(end_index, len(values) - 1 - PIVOT_NEIGHBOR_WINDOW)
    for index in range(start, end + 1):
        current = values[index]
        left = values[index - PIVOT_NEIGHBOR_WINDOW : index]
        right = values[index + 1 : index + 1 + PIVOT_NEIGHBOR_WINDOW]
        if current >= max(left) and current > max(right):
            pivots.append(index)
    return pivots


def _is_indicator_weaker(previous: float, current: float) -> bool:
    baseline = max(abs(previous), MACD_ZERO_EPSILON)
    return current < previous - baseline * MIN_MACD_WEAKEN_RATIO


def _macd(values: list[float]) -> tuple[list[float], list[float], list[float]]:
    ema12 = _ema(values, 12)
    ema26 = _ema(values, 26)
    dif = [fast - slow for fast, slow in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    macd_hist = [(dif_value - dea_value) * 2 for dif_value, dea_value in zip(dif, dea)]
    return dif, dea, macd_hist


def _ema(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (window + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def _find_negative_to_positive_turn_points(slopes: list[float | None]) -> list[int]:
    points: list[int] = []
    for index in range(1, len(slopes)):
        previous = slopes[index - 1]
        current = slopes[index]
        if previous is None or current is None:
            continue
        if previous < 0 <= current:
            points.append(index)
    return points


def _moving_average(values: list[float | None], window: int) -> list[float | None]:
    result: list[float | None] = []
    window_sum = 0.0
    none_count = 0
    for index in range(len(values)):
        value = values[index]
        if value is None:
            none_count += 1
        else:
            window_sum += value

        if index >= window:
            expired = values[index - window]
            if expired is None:
                none_count -= 1
            else:
                window_sum -= expired

        if index + 1 < window or none_count > 0:
            result.append(None)
            continue
        result.append(window_sum / window)
    return result


def _average_true_range(
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float | None],
    window: int,
) -> list[float | None]:
    true_ranges: list[float | None] = [None]
    for index in range(1, len(closes)):
        high = highs[index]
        low = lows[index]
        previous_close = closes[index - 1]
        if high is None or low is None or previous_close is None:
            true_ranges.append(None)
            continue
        true_ranges.append(
            max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        )
    return _moving_average(true_ranges, window)


def _rolling_linear_slopes(
    values: list[float | None],
    window: int,
) -> list[float | None]:
    if window <= 1:
        return [None for _ in values]
    result: list[float | None] = []
    x_mean = (window - 1) / 2
    denominator = sum((x - x_mean) ** 2 for x in range(window))
    window_sum = 0.0
    weighted_sum = 0.0
    none_count = 0
    for index in range(len(values)):
        value = values[index]
        if index < window:
            if value is None:
                none_count += 1
            else:
                window_sum += value
                weighted_sum += index * value
        else:
            expired = values[index - window]
            if expired is None:
                none_count -= 1
            else:
                window_sum -= expired
            weighted_sum -= window_sum
            if value is None:
                none_count += 1
            else:
                window_sum += value
                weighted_sum += (window - 1) * value

        if index + 1 < window or none_count > 0:
            result.append(None)
            continue
        numerator = weighted_sum - x_mean * window_sum
        result.append(numerator / denominator)
    return result


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
