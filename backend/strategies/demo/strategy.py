from __future__ import annotations

from typing import Any

from app.entities.stock_data_context import StockDataContext


HISTORY_WINDOW = 430
MA30_WINDOW = 30
MA30_SLOPE_WINDOW = 10
MA30_STRUCTURE_DAYS = 400
MIN_MA30_TURN_POINTS = 5
MAX_MA30_TURN_POINTS = 8
RECENT_TURN_POINTS = 5
RECENT_LOW_COUNT = 4
MIN_LOW_STRUCTURE_SPAN_DAYS = 200
LOW_CHANGE_ATR_MULTIPLE = 0.3
RECENT_SUPPORT_LOOKBACK = 6
ATR30_WINDOW = 30

ATR14_WINDOW = 14
VOLUME_AVG_WINDOW = 10
LONG_BODY_MIN_RATIO = 0.7
LONG_BODY_ATR_MULTIPLE = 0.8
SMALL_CANDLE_ATR_MULTIPLE = 0.6

MACD_DIVERGENCE_LOOKBACK = 120
PIVOT_NEIGHBOR_WINDOW = 3
MIN_PRICE_HIGHER_HIGH_RATIO = 0.01
MIN_MACD_WEAKEN_RATIO = 0.05
MACD_ZERO_EPSILON = 1e-9

ALLOWED_LOW_PATTERNS = {
    ("震", "震", "震"),
    ("跌", "震", "涨"),
    ("跌", "涨", "震"),
    ("跌", "涨", "涨"),
    ("震", "涨", "涨"),
    ("涨", "震", "涨"),
    ("涨", "涨", "震"),
    ("震", "震", "涨"),
    ("涨", "震", "震"),
    ("震", "涨", "震"),
    ("涨", "涨", "涨"),
}


def demo_signal_strategy(context: StockDataContext) -> bool:
    if not _passes_universe_filter(context):
        return False
    if not _passes_trend_filter(context.bars_1d_qfq):
        return False
    if not _passes_kline_filter(context.bars_1d_qfq):
        return False
    return True


def demo_universe_filter(context: StockDataContext) -> bool:
    return _passes_universe_filter(context)


def demo_entry_strategy(*_args: Any, **_kwargs: Any) -> int:
    return -1


def demo_exit_strategy(*_args: Any, **_kwargs: Any) -> int:
    return -1


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
    if len(bars) < HISTORY_WINDOW:
        return False

    window_bars = bars[-HISTORY_WINDOW:]
    closes = [_to_float(item.get("close")) for item in window_bars]
    highs = [_to_float(item.get("high")) for item in window_bars]
    lows = [_to_float(item.get("low")) for item in window_bars]
    if any(value is None for value in closes):
        return False
    if any(value is None for value in highs):
        return False
    if any(value is None for value in lows):
        return False

    ma30 = _moving_average(closes, MA30_WINDOW)
    atr30 = _average_true_range(highs, lows, closes, ATR30_WINDOW)
    ma30_points = [
        (index, value)
        for index, value in enumerate(ma30)
        if value is not None
    ]
    if len(ma30_points) < MA30_STRUCTURE_DAYS:
        return False

    ma30_points = ma30_points[-MA30_STRUCTURE_DAYS:]
    ma30_indices = [item[0] for item in ma30_points]
    ma30_values = [item[1] for item in ma30_points]
    ma30_slopes = _rolling_linear_slopes(ma30_values, MA30_SLOPE_WINDOW)
    turn_positions = _find_negative_to_positive_turn_points(ma30_slopes)
    if not (MIN_MA30_TURN_POINTS <= len(turn_positions) <= MAX_MA30_TURN_POINTS):
        return False

    recent_turn_indices = [ma30_indices[position] for position in turn_positions[-RECENT_TURN_POINTS:]]
    low_points = _extract_interval_low_points(
        lows=lows,
        atr30=atr30,
        turn_indices=recent_turn_indices,
    )
    if low_points is None:
        return False
    if low_points[-1][0] - low_points[0][0] < MIN_LOW_STRUCTURE_SPAN_DAYS:
        return False

    low_pattern = _classify_low_changes(low_points)
    if low_pattern not in ALLOWED_LOW_PATTERNS:
        return False

    if not _is_recent_low_near_last_structure_low(lows, low_points[-1]):
        return False

    return not _has_bearish_macd_divergence(closes)


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
        threshold = next_atr * LOW_CHANGE_ATR_MULTIPLE
        if delta > threshold:
            changes.append("涨")
        elif delta < -threshold:
            changes.append("跌")
        else:
            changes.append("震")
    return tuple(changes)


def _is_recent_low_near_last_structure_low(
    lows: list[float | None],
    last_low_point: tuple[int, float, float],
) -> bool:
    recent_lows = lows[-RECENT_SUPPORT_LOOKBACK:]
    if len(recent_lows) < RECENT_SUPPORT_LOOKBACK or any(value is None for value in recent_lows):
        return False
    _low_index, low_value, low_atr = last_low_point
    return min(value for value in recent_lows if value is not None) <= low_value + low_atr * LOW_CHANGE_ATR_MULTIPLE


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
        or _is_piercing_like(candles, atr14, current_index)
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
    return current >= average_volume


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
        and current["body"] >= previous_body * 0.8
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
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
            continue
        window_values = values[index + 1 - window : index + 1]
        if any(value is None for value in window_values):
            result.append(None)
            continue
        result.append(sum(value for value in window_values if value is not None) / window)
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
    result: list[float | None] = []
    x_values = list(range(window))
    x_mean = sum(x_values) / window
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
            continue
        window_values = values[index + 1 - window : index + 1]
        if any(value is None for value in window_values):
            result.append(None)
            continue
        y_values = [value for value in window_values if value is not None]
        y_mean = sum(y_values) / window
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
        result.append(numerator / denominator)
    return result


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
