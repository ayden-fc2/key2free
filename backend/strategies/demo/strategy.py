from __future__ import annotations

from typing import Any

from app.entities.stock_data_context import StockDataContext


MA_FAST_WINDOW = 20
MA_SLOW_WINDOW = 30
SLOPE_ATR_WINDOW = 14
STRUCTURE_ATR_WINDOW = 30
VOLUME_ATR_WINDOW = 14
SLOPE_WINDOW = 10
CROSS_LOOKBACK_DAYS = 5
SLOPE_TURN_START_DAYS_AGO = 20
SLOPE_TURN_END_DAYS_AGO = 5
LONG_BODY_MIN_RATIO = 0.8
LONG_BODY_ATR_MULTIPLE = 1.2
SMALL_BODY_ATR_MULTIPLE = 0.5
VOLUME_EXPANSION_ATR_MULTIPLE = 1.2
MIN_NORMALIZED_SLOPE = 0.03
STRUCTURE_LOOKBACK = 300
MA30_TURN_SLOPE_WINDOW = 10
MIN_TROUGH_COUNT = 3
PIVOT_NOISE_TOLERANCE = 0.02
MIN_PIVOT_SLOPE_ATR_MULTIPLE = 0.08
PIVOT_LINEAR_FIT_MAX_RMSE_ATR_MULTIPLE = 0.8
MIN_PIVOT_RECOVERY_ATR_MULTIPLE = 0.3
PIVOT_TURN_MIN_SEGMENT_POINTS = 2
MACD_DIVERGENCE_LOOKBACK = 120
PIVOT_NEIGHBOR_WINDOW = 3
MIN_PRICE_HIGHER_HIGH_RATIO = 0.01
MIN_MACD_WEAKEN_RATIO = 0.05
MACD_ZERO_EPSILON = 1e-9


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
    min_bars = max(
        MA_SLOW_WINDOW,
        SLOPE_ATR_WINDOW,
        STRUCTURE_ATR_WINDOW,
        VOLUME_ATR_WINDOW,
        MA_SLOW_WINDOW + STRUCTURE_LOOKBACK,
    ) + SLOPE_WINDOW + 1
    if len(bars) < min_bars:
        return False

    closes = [_to_float(item.get("close")) for item in bars]
    highs = [_to_float(item.get("high")) for item in bars]
    lows = [_to_float(item.get("low")) for item in bars]
    if any(value is None for value in closes[-min_bars:]):
        return False
    if any(value is None for value in highs[-(STRUCTURE_ATR_WINDOW + 1):]):
        return False
    if any(value is None for value in lows[-(STRUCTURE_ATR_WINDOW + 1):]):
        return False

    ma20 = _moving_average(closes, MA_FAST_WINDOW)
    ma30 = _moving_average(closes, MA_SLOW_WINDOW)
    if not _has_recent_ma_cross_up(ma20, ma30, CROSS_LOOKBACK_DAYS):
        return False

    slope_atr = _average_true_range(highs, lows, closes, SLOPE_ATR_WINDOW)
    structure_atr = _average_true_range(highs, lows, closes, STRUCTURE_ATR_WINDOW)
    current_slope_atr = slope_atr[-1]
    current_structure_atr = structure_atr[-1]
    if current_slope_atr is None or current_slope_atr <= 0:
        return False
    if current_structure_atr is None or current_structure_atr <= 0:
        return False

    slopes = _rolling_linear_slopes(ma20, SLOPE_WINDOW)
    if not _has_slope_negative_to_positive_turn_in_window(
        slopes,
        start_days_ago=SLOPE_TURN_START_DAYS_AGO,
        end_days_ago=SLOPE_TURN_END_DAYS_AGO,
    ):
        return False
    recent_slopes = slopes[-SLOPE_WINDOW:]
    if any(value is None for value in recent_slopes):
        return False

    normalized = [value / current_slope_atr for value in recent_slopes if value is not None]
    if normalized[-1] <= MIN_NORMALIZED_SLOPE:
        return False
    if not _passes_ma30_structure_filter(closes, ma30, current_structure_atr):
        return False
    return not _has_bearish_macd_divergence(closes)


def _passes_kline_filter(bars: list[dict[str, Any]]) -> bool:
    min_bars = max(SLOPE_ATR_WINDOW, VOLUME_ATR_WINDOW) + 5
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
    if any(value is None for value in volumes[-(VOLUME_ATR_WINDOW + 1):]):
        return False

    atr14 = _average_true_range(highs, lows, closes, SLOPE_ATR_WINDOW)
    volume_atr = _average_volume_true_range(volumes, VOLUME_ATR_WINDOW)
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
    current_volume_atr = volume_atr[current_index]
    if current_atr is None or current_atr <= 0:
        return False
    if current_volume_atr is None or current_volume_atr <= 0:
        return False

    return (
        _is_dragonfly_doji(candles, volumes, volume_atr, current_index)
        or _is_hammer(candles, volumes, volume_atr, current_index)
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


def _has_volume_expansion(
    volumes: list[float | None],
    volume_atr: list[float | None],
    index: int,
) -> bool:
    if index <= 0:
        return False
    current = volumes[index]
    previous = volumes[index - 1]
    atr_value = volume_atr[index]
    if current is None or previous is None or atr_value is None or atr_value <= 0:
        return False
    return current > previous and current - previous >= atr_value * VOLUME_EXPANSION_ATR_MULTIPLE


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
    volume_atr: list[float | None],
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
            multiple=8,
        )
        and _has_volume_expansion(volumes, volume_atr, index)
    )


def _is_hammer_shape(candle: dict[str, float]) -> bool:
    body_ratio = _body_ratio(candle)
    return (
        0.1 <= body_ratio <= 0.4
        and _shadow_ratio_at_least(
            long_shadow=candle["lower_shadow"],
            short_shadow=candle["upper_shadow"],
            multiple=5,
        )
    )


def _is_inverted_hammer_shape(candle: dict[str, float]) -> bool:
    body_ratio = _body_ratio(candle)
    return (
        0.1 <= body_ratio <= 0.4
        and _shadow_ratio_at_least(
            long_shadow=candle["upper_shadow"],
            short_shadow=candle["lower_shadow"],
            multiple=5,
        )
    )


def _is_hammer(
    candles: list[dict[str, float] | None],
    volumes: list[float | None],
    volume_atr: list[float | None],
    index: int,
) -> bool:
    candle = candles[index]
    if candle is None:
        return False
    return _is_hammer_shape(candle) and _has_volume_expansion(volumes, volume_atr, index)


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
            candle is not None and candle["body"] <= _atr_value_or_zero(atr14[index]) * SMALL_BODY_ATR_MULTIPLE
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


def _has_recent_ma_cross_up(
    ma_fast: list[float | None],
    ma_slow: list[float | None],
    lookback_days: int,
) -> bool:
    if len(ma_fast) != len(ma_slow) or len(ma_fast) < 2:
        return False

    start_index = max(1, len(ma_fast) - lookback_days - 1)
    for index in range(start_index, len(ma_fast)):
        previous_fast = ma_fast[index - 1]
        previous_slow = ma_slow[index - 1]
        current_fast = ma_fast[index]
        current_slow = ma_slow[index]
        if (
            previous_fast is not None
            and previous_slow is not None
            and current_fast is not None
            and current_slow is not None
            and previous_fast < previous_slow
            and current_fast > current_slow
        ):
            return True
    return False


def _has_slope_negative_to_positive_turn_in_window(
    slopes: list[float | None],
    *,
    start_days_ago: int,
    end_days_ago: int,
) -> bool:
    if start_days_ago <= end_days_ago or len(slopes) < start_days_ago + 1:
        return False

    start_index = len(slopes) - start_days_ago
    end_index = len(slopes) - end_days_ago
    for index in range(max(1, start_index), end_index + 1):
        previous = slopes[index - 1]
        current = slopes[index]
        if previous is None or current is None:
            continue
        if previous < 0 <= current:
            return True
    return False


def _passes_ma30_structure_filter(
    closes: list[float | None],
    ma30: list[float | None],
    current_atr: float,
) -> bool:
    aligned = [
        (ma_value, close_value)
        for ma_value, close_value in zip(ma30, closes)
        if ma_value is not None and close_value is not None
    ]
    if len(aligned) < STRUCTURE_LOOKBACK:
        return False
    lookback = aligned[-STRUCTURE_LOOKBACK:]
    ma30_values = [item[0] for item in lookback]
    close_values = [item[1] for item in lookback]
    ma30_slopes = _rolling_linear_slopes(ma30_values, MA30_TURN_SLOPE_WINDOW)
    turn_points = _find_negative_to_positive_turn_points(ma30_slopes)
    if len(turn_points) < MIN_TROUGH_COUNT + 1:
        return False

    troughs: list[float] = []
    peaks: list[float] = []
    for start, end in zip(turn_points, turn_points[1:]):
        segment = close_values[start : end + 1]
        if len(segment) < 2:
            continue
        troughs.append(min(segment))
        peaks.append(max(segment))

    if len(troughs) < MIN_TROUGH_COUNT:
        return False
    return _passes_pivot_trend_structure(
        troughs,
        current_atr,
    ) and _passes_pivot_trend_structure(peaks, current_atr)


def _has_bearish_macd_divergence(closes: list[float | None]) -> bool:
    valid_closes = [value for value in closes if value is not None]
    if len(valid_closes) < MACD_DIVERGENCE_LOOKBACK:
        return False

    dif, dea, macd_hist = _macd(valid_closes)
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


def _passes_pivot_trend_structure(values: list[float], current_atr: float) -> bool:
    if len(values) < MIN_TROUGH_COUNT:
        return False
    if current_atr <= 0:
        return False

    slope, rmse = _linear_fit_stats(values)
    if rmse / current_atr <= PIVOT_LINEAR_FIT_MAX_RMSE_ATR_MULTIPLE:
        return _is_clean_uptrend(values, slope, current_atr)
    return _is_pullback_then_recovery(values, current_atr)


def _is_clean_uptrend(
    values: list[float],
    regression_slope: float,
    current_atr: float,
) -> bool:
    if len(values) < MIN_TROUGH_COUNT:
        return False
    if current_atr <= 0:
        return False
    if regression_slope / current_atr <= MIN_PIVOT_SLOPE_ATR_MULTIPLE:
        return False
    if values[-1] < values[-2]:
        return False

    tolerated_drops = 0
    for previous, current in zip(values, values[1:]):
        if current >= previous * (1 - PIVOT_NOISE_TOLERANCE):
            continue
        tolerated_drops += 1
    return tolerated_drops <= max(1, len(values) // 4)


def _is_pullback_then_recovery(values: list[float], current_atr: float) -> bool:
    if len(values) < MIN_TROUGH_COUNT:
        return False
    if current_atr <= 0:
        return False

    bottom_index = min(range(len(values)), key=values.__getitem__)
    if bottom_index < PIVOT_TURN_MIN_SEGMENT_POINTS - 1:
        return False
    if len(values) - bottom_index - 1 < PIVOT_TURN_MIN_SEGMENT_POINTS:
        return False

    early_values = values[: bottom_index + 1]
    recent_values = values[bottom_index:]
    early_slope, _early_rmse = _linear_fit_stats(early_values)
    recent_slope, _recent_rmse = _linear_fit_stats(recent_values)

    return (
        early_slope <= 0
        and recent_slope / current_atr > MIN_PIVOT_SLOPE_ATR_MULTIPLE
        and values[-1] > values[-2]
        and values[-1] - values[bottom_index] > current_atr * MIN_PIVOT_RECOVERY_ATR_MULTIPLE
    )


def _linear_fit_stats(values: list[float]) -> tuple[float, float]:
    if len(values) < 2:
        return 0.0, 0.0
    x_values = list(range(len(values)))
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(values) / len(values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0, 0.0
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    residual_mean_square = sum(
        (y - (slope * x + intercept)) ** 2
        for x, y in zip(x_values, values)
    ) / len(values)
    rmse = residual_mean_square**0.5
    return slope, rmse


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


def _average_volume_true_range(
    values: list[float | None],
    window: int = VOLUME_ATR_WINDOW,
) -> list[float | None]:
    ranges: list[float | None] = [None]
    for index in range(1, len(values)):
        current = values[index]
        previous = values[index - 1]
        if current is None or previous is None:
            ranges.append(None)
            continue
        ranges.append(abs(current - previous))
    return _moving_average(ranges, window)


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
