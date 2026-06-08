from __future__ import annotations

from typing import Any

from app.entities.stock_data_context import StockDataContext


MA_FAST_WINDOW = 20
MA_SLOW_WINDOW = 30
SLOPE_ATR_WINDOW = 14
STRUCTURE_ATR_WINDOW = 30
VOLUME_ATR_WINDOW = 30
SLOPE_WINDOW = 10
MIN_NORMALIZED_SLOPE = 0.03
NEAR_ZERO_NORMALIZED_SLOPE = 0.01
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
    return True


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
    if ma20[-2] is None or ma30[-2] is None or ma20[-1] is None or ma30[-1] is None:
        return False
    if not (ma20[-2] < ma30[-2] and ma20[-1] > ma30[-1]):
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
    recent_slopes = slopes[-SLOPE_WINDOW:]
    if any(value is None for value in recent_slopes):
        return False

    normalized = [value / current_slope_atr for value in recent_slopes if value is not None]
    if normalized[-1] <= MIN_NORMALIZED_SLOPE:
        return False
    if not _has_negative_to_zero_to_positive_turn(normalized):
        return False
    if not _passes_ma30_structure_filter(closes, ma30, current_structure_atr):
        return False
    return not _has_bearish_macd_divergence(closes)


def _has_negative_to_zero_to_positive_turn(values: list[float]) -> bool:
    if len(values) < SLOPE_WINDOW:
        return False
    first_part = values[:3]
    middle_part = values[3:7]
    last_part = values[7:]
    return (
        min(first_part) < -NEAR_ZERO_NORMALIZED_SLOPE
        and any(abs(value) <= NEAR_ZERO_NORMALIZED_SLOPE for value in middle_part)
        and max(last_part) > NEAR_ZERO_NORMALIZED_SLOPE
        and values[-1] > values[0]
    )


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
