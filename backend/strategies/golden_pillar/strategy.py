"""Golden/general pillar breakout strategy.

Spec: a-obsidian-docs/strategies/黄金柱战法.md.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, TypeVar

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


T = TypeVar("T")

MAX_WATCH_DAYS = 1
GOLDEN_PILLAR_POSITION_FRACTION = 1.0 / 4.0
GOLDEN_PILLAR_MAX_HOLDING_DAYS = 15
GOLDEN_PILLAR_FAILED_START_DAYS = 6
GOLDEN_PILLAR_FAILED_START_RETURN_RATIO = 1.04
GOLDEN_PILLAR_MAX_ENTRY_OPEN_RATIO = 1.03

LOOKBACK_BARS = 400
RECENT_CONSOLIDATION_BARS = 10
RECENT_PILLAR_BARS = 4

CONSOLIDATION_BARS = 17
MAX_CONSOLIDATION_AVG_DAILY_BODY_RATIO = 0.030
MAX_CONSOLIDATION_BODY_RANGE_RATIO = 0.070

MIN_SIGNAL_TO_CONSOLIDATION_BODY_HIGH_RATIO = 1.02
MAX_SIGNAL_TO_CONSOLIDATION_BODY_HIGH_RATIO = 1.09
STOP_LOSS_2_RATIO = 1.0
TAKE_PROFIT_1_MAX_RATIO = 1.08
TAKE_PROFIT_2_MAX_RATIO = 1.12
TAKE_PROFIT_1_RISK_MULTIPLE = 1.5
TAKE_PROFIT_2_RISK_MULTIPLE = 2.0
MA10_SLOPE_NOISE_THRESHOLD = 0.008
MAX_TAKE_PROFIT_2_N_HIGH_RATIO = 0.90
T1_VOLUME_TO_AVG5_MULTIPLE = 1.2
T1_BODY_OPEN_RATIO = 0.035
T1_BODY_ATR5_MULTIPLE = 1.5
MAX_T1_BODY_OPEN_RATIO = 0.090
CONFIRM_BODY_TO_T1_CLOSE_RATIO = 0.03
GOLDEN_PILLAR_MIN_CONFIRM_POSITION = 0.8
GOLDEN_PILLAR_MAX_CONFIRM_POSITION = 1.3
GENERAL_PILLAR_MIN_CONFIRM_POSITION = 0.5
GENERAL_PILLAR_MAX_CONFIRM_POSITION = 0.8
PILLAR_T1_CLOSE_TO_CONSOLIDATION_BODY_HIGH_RATIO = 1.0
PILLAR_TYPE_GOLDEN = "golden_pillar"
PILLAR_TYPE_GENERAL = "general_pillar"

GOLDEN_PILLAR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_5",
    "avg_volume_5",
    "ma_slope_10",
)


@dataclass(frozen=True)
class ConsolidationRange:
    start_index: int
    end_index: int
    high: float
    low: float
    body_high: float
    body_low: float
    avg_daily_body_ratio: float
    body_range_ratio: float


@dataclass(frozen=True)
class PillarPattern:
    pattern_type: str
    t1_index: int
    t4_index: int
    t1_open: float
    t1_close: float
    t4_close: float
    t4_large_bullish: bool
    confirm_position_min: float
    confirm_position_max: float


@dataclass(frozen=True)
class SlopeExtreme:
    kind: str
    index: int
    value: float


@dataclass(frozen=True)
class StructurePoint:
    kind: str
    index: int
    price: float
    left_extreme: SlopeExtreme
    right_extreme: SlopeExtreme


@dataclass(frozen=True)
class NRange:
    low: StructurePoint
    high: StructurePoint
    previous_low: StructurePoint | None
    previous_high: StructurePoint | None
    trend_type: str


def golden_pillar_code_filter(code: str) -> bool:
    """Keep main-board common A-share codes; date-sensitive ST checks run later."""
    value = code.lower()
    if value.startswith("sh.688") or value.startswith("sz.300") or value.startswith("sz.301"):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


def golden_pillar_batch_signal_strategy(
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

    with np.errstate(invalid="ignore", divide="ignore"):
        st_blocked = _st_blocked_series(columns)

    all_pillars = _scan_pillar_patterns(frame, 0, len(frame) - 1)
    pillar_t4_indices = [item.t4_index for item in all_pillars]
    all_consolidations = _scan_consolidation_ranges(frame, 0, len(frame) - 1)
    consolidation_end_indices = [item.end_index for item in all_consolidations]

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if index < LOOKBACK_BARS - 1 or st_blocked[index]:
            continue

        close_t = float(closes[index])
        if not np.isfinite(close_t):
            continue

        window_start = index + 1 - LOOKBACK_BARS
        recent_pillar_start = max(window_start, index - RECENT_PILLAR_BARS)
        recent_consolidation_start = max(window_start, index - RECENT_CONSOLIDATION_BARS)

        recent_consolidations = _slice_by_index_range(
            all_consolidations,
            consolidation_end_indices,
            recent_consolidation_start,
            index,
        )
        if not recent_consolidations:
            continue
        consolidation = recent_consolidations[-1]

        recent_pillars = _slice_by_index_range(
            all_pillars,
            pillar_t4_indices,
            recent_pillar_start,
            index,
        )
        matched_pillar = _latest_pillar_above_consolidation(recent_pillars, consolidation)
        if matched_pillar is None:
            continue

        n_range = _resolve_recent_n_range(
            frame=frame,
            index=index,
            window_start=window_start,
        )
        if n_range is None:
            continue
        if n_range.previous_high is None or n_range.previous_low is None:
            continue
        n_low = n_range.low.price
        n_high = n_range.high.price
        n_range_size = n_high - n_low
        if not (
            np.isfinite(n_low)
            and np.isfinite(n_high)
            and n_low > 0
            and n_high > n_low
        ):
            continue

        if not (
            np.isfinite(consolidation.high)
            and np.isfinite(consolidation.low)
            and np.isfinite(consolidation.body_high)
            and consolidation.high > 0
            and consolidation.low > 0
            and consolidation.body_high > 0
            and MIN_SIGNAL_TO_CONSOLIDATION_BODY_HIGH_RATIO * consolidation.body_high
            <= close_t
            <= MAX_SIGNAL_TO_CONSOLIDATION_BODY_HIGH_RATIO * consolidation.body_high
        ):
            continue

        stop_loss_1 = matched_pillar.t1_open
        stop_loss_2 = close_t * STOP_LOSS_2_RATIO
        risk_distance = close_t - stop_loss_1
        take_profit_1 = min(
            close_t * TAKE_PROFIT_1_MAX_RATIO,
            close_t + risk_distance * TAKE_PROFIT_1_RISK_MULTIPLE,
        )
        take_profit_2 = min(
            close_t * TAKE_PROFIT_2_MAX_RATIO,
            close_t + risk_distance * TAKE_PROFIT_2_RISK_MULTIPLE,
        )
        if not (
            np.isfinite(stop_loss_1)
            and np.isfinite(stop_loss_2)
            and np.isfinite(take_profit_1)
            and np.isfinite(take_profit_2)
            and stop_loss_1 > 0
            and risk_distance > 0
            and stop_loss_1 < close_t
        ):
            continue
        n_take_profit_2_high = _higher_recent_n_high(n_range)
        n_take_profit_2_limit = n_take_profit_2_high * MAX_TAKE_PROFIT_2_N_HIGH_RATIO
        if take_profit_2 >= n_take_profit_2_limit:
            continue

        results[index] = SignalDecision(
            triggered=True,
            signal_close=close_t,
            stop_losses=(float(stop_loss_1), float(stop_loss_2)),
            take_profits=(float(take_profit_1), float(take_profit_2)),
            max_watch_days=MAX_WATCH_DAYS,
            extras={
                "pattern": "golden_pillar_breakout",
                "consolidation_start": frame.trade_dates[consolidation.start_index].isoformat(),
                "consolidation_end": frame.trade_dates[consolidation.end_index].isoformat(),
                "consolidation_high": consolidation.high,
                "consolidation_low": consolidation.low,
                "consolidation_body_high": consolidation.body_high,
                "consolidation_body_low": consolidation.body_low,
                "consolidation_avg_daily_body_ratio": consolidation.avg_daily_body_ratio,
                "consolidation_body_range_ratio": consolidation.body_range_ratio,
                "pillar_type": matched_pillar.pattern_type,
                "pillar_t1_date": frame.trade_dates[matched_pillar.t1_index].isoformat(),
                "pillar_t4_date": frame.trade_dates[matched_pillar.t4_index].isoformat(),
                "pillar_t1_open": matched_pillar.t1_open,
                "pillar_t1_close": matched_pillar.t1_close,
                "pillar_t4_close": matched_pillar.t4_close,
                "pillar_t4_large_bullish": matched_pillar.t4_large_bullish,
                "pillar_t1_close_to_consolidation_body_high": (
                    matched_pillar.t1_close / consolidation.body_high
                ),
                "pillar_confirm_position_min": matched_pillar.confirm_position_min,
                "pillar_confirm_position_max": matched_pillar.confirm_position_max,
                "n_low": n_low,
                "n_low_date": frame.trade_dates[n_range.low.index].isoformat(),
                "n_high": n_high,
                "n_high_date": frame.trade_dates[n_range.high.index].isoformat(),
                "previous_n_low": None if n_range.previous_low is None else n_range.previous_low.price,
                "previous_n_low_date": (
                    None
                    if n_range.previous_low is None
                    else frame.trade_dates[n_range.previous_low.index].isoformat()
                ),
                "previous_n_high": None if n_range.previous_high is None else n_range.previous_high.price,
                "previous_n_high_date": (
                    None
                    if n_range.previous_high is None
                    else frame.trade_dates[n_range.previous_high.index].isoformat()
                ),
                "n_trend_type": n_range.trend_type,
                "n_close_position_ratio": (close_t - n_low) / n_range_size,
                "n_take_profit_2_high": n_take_profit_2_high,
                "n_take_profit_2_limit": n_take_profit_2_limit,
                "breakout_ratio_t": close_t / consolidation.body_high,
                "risk_distance": float(risk_distance),
                "stop_loss_1": float(stop_loss_1),
                "stop_loss_2": float(stop_loss_2),
                "take_profit_1": float(take_profit_1),
                "take_profit_2": float(take_profit_2),
                "max_entry_open": float(close_t * GOLDEN_PILLAR_MAX_ENTRY_OPEN_RATIO),
                "failed_start_days": GOLDEN_PILLAR_FAILED_START_DAYS,
                "failed_start_return_ratio": GOLDEN_PILLAR_FAILED_START_RETURN_RATIO,
            },
        )
    return results


def _scan_pillar_patterns(
    frame: StockDailyFrame,
    start_index: int,
    end_index: int,
) -> list[PillarPattern]:
    patterns: list[PillarPattern] = []
    first_t1 = max(1, start_index)
    last_t1 = min(end_index - 3, len(frame) - 4)
    for t1_index in range(first_t1, last_t1 + 1):
        pattern = _detect_pillar_pattern(frame, t1_index)
        if pattern is not None:
            patterns.append(pattern)
    return patterns


def _latest_pillar_above_consolidation(
    patterns: list[PillarPattern],
    consolidation: ConsolidationRange,
) -> PillarPattern | None:
    for pattern in reversed(patterns):
        if pattern.t1_close >= PILLAR_T1_CLOSE_TO_CONSOLIDATION_BODY_HIGH_RATIO * consolidation.body_high:
            return pattern
    return None


def _detect_pillar_pattern(
    frame: StockDailyFrame,
    t1_index: int,
) -> PillarPattern | None:
    t0_index = t1_index - 1
    t4_index = t1_index + 3
    if t0_index < 0 or t4_index >= len(frame):
        return None

    columns = frame.columns
    opens = columns["qfq_open"]
    closes = columns["qfq_close"]
    volumes = columns.get("volume")
    if volumes is None:
        volumes = columns["vol"]
    avg_volumes = columns["avg_volume_5"]
    atrs = columns["atr_5"]

    t1_open = float(opens[t1_index])
    t1_close = float(closes[t1_index])
    t4_close = float(closes[t4_index])
    t1_volume = float(volumes[t1_index])
    avg_volume_5_t0 = float(avg_volumes[t0_index])
    atr_5_t0 = float(atrs[t0_index])
    values = [t1_open, t1_close, t4_close, t1_volume, avg_volume_5_t0, atr_5_t0]
    if not all(np.isfinite(value) for value in values):
        return None
    if t1_open <= 0 or t1_close <= t1_open or avg_volume_5_t0 <= 0 or atr_5_t0 <= 0:
        return None
    if t1_volume < T1_VOLUME_TO_AVG5_MULTIPLE * avg_volume_5_t0:
        return None

    t1_body = t1_close - t1_open
    min_t1_body = min(T1_BODY_OPEN_RATIO * t1_open, T1_BODY_ATR5_MULTIPLE * atr_5_t0)
    max_t1_body = MAX_T1_BODY_OPEN_RATIO * t1_open
    if not (min_t1_body <= t1_body <= max_t1_body):
        return None

    confirm_positions = []
    max_short_confirm_body = CONFIRM_BODY_TO_T1_CLOSE_RATIO * t1_close
    t4_large_bullish = False
    for position in range(t1_index + 1, t4_index + 1):
        open_value = float(opens[position])
        close_value = float(closes[position])
        if not (np.isfinite(open_value) and np.isfinite(close_value)):
            return None
        body = abs(close_value - open_value)
        if position < t4_index:
            if body > max_short_confirm_body:
                return None
        elif body > max_short_confirm_body and close_value <= open_value:
            return None
        elif position == t4_index and body >= max_short_confirm_body and close_value > open_value:
            t4_large_bullish = True
        body_low = min(open_value, close_value)
        body_high = max(open_value, close_value)
        position_low = (body_low - t1_open) / t1_body
        position_high = (body_high - t1_open) / t1_body
        if not (np.isfinite(position_low) and np.isfinite(position_high)):
            return None
        confirm_positions.append((position_low, position_high))

    confirm_position_min = min(item[0] for item in confirm_positions)
    confirm_position_max = max(item[1] for item in confirm_positions)
    if (
        confirm_position_min >= GOLDEN_PILLAR_MIN_CONFIRM_POSITION
        and confirm_position_max <= GOLDEN_PILLAR_MAX_CONFIRM_POSITION
    ):
        pattern_type = PILLAR_TYPE_GOLDEN
    elif (
        confirm_position_min >= GENERAL_PILLAR_MIN_CONFIRM_POSITION
        and confirm_position_max <= GENERAL_PILLAR_MAX_CONFIRM_POSITION
    ):
        pattern_type = PILLAR_TYPE_GENERAL
    else:
        return None

    return PillarPattern(
        pattern_type=pattern_type,
        t1_index=t1_index,
        t4_index=t4_index,
        t1_open=t1_open,
        t1_close=t1_close,
        t4_close=t4_close,
        t4_large_bullish=t4_large_bullish,
        confirm_position_min=float(confirm_position_min),
        confirm_position_max=float(confirm_position_max),
    )


def golden_pillar_entry_strategy(*, bar: tuple[float, float, float, float, float, float], watch: Any) -> float | None:
    signal = watch.signal or {}
    signal_close = watch.signal_close
    if signal_close is None or signal_close <= 0:
        return None
    max_entry_open = signal.get("max_entry_open")
    if not isinstance(max_entry_open, (int, float)) or not np.isfinite(float(max_entry_open)):
        max_entry_open = signal_close * GOLDEN_PILLAR_MAX_ENTRY_OPEN_RATIO
    open_price = float(bar[0])
    if not np.isfinite(open_price) or open_price > float(max_entry_open):
        return None
    return open_price


def _scan_consolidation_ranges(
    frame: StockDailyFrame,
    start_index: int,
    end_index: int,
) -> list[ConsolidationRange]:
    ranges: list[ConsolidationRange] = []
    first_start = max(0, start_index)
    last_start = end_index - CONSOLIDATION_BARS + 1
    for range_start in range(first_start, last_start + 1):
        item = _detect_consolidation_range(frame, range_start)
        if item is not None:
            ranges.append(item)
    return ranges


def _detect_consolidation_range(
    frame: StockDailyFrame,
    start_index: int,
) -> ConsolidationRange | None:
    end_index = start_index + CONSOLIDATION_BARS - 1
    if end_index >= len(frame):
        return None

    highs = frame.columns["qfq_high"][start_index : end_index + 1]
    lows = frame.columns["qfq_low"][start_index : end_index + 1]
    closes = frame.columns["qfq_close"][start_index : end_index + 1]
    opens = frame.columns["qfq_open"][start_index : end_index + 1]
    values = [*highs, *lows, *closes, *opens]
    if not all(np.isfinite(float(value)) for value in values):
        return None
    if np.any(closes <= 0):
        return None

    with np.errstate(invalid="ignore", divide="ignore"):
        daily_body_ratios = np.abs(closes - opens) / closes
    if not np.all(np.isfinite(daily_body_ratios)):
        return None

    avg_daily_body_ratio = float(np.mean(daily_body_ratios))
    high = float(np.max(highs))
    low = float(np.min(lows))
    body_highs = np.maximum(opens, closes)
    body_lows = np.minimum(opens, closes)
    trimmed_body_highs = _drop_one_extreme(body_highs, drop_high=True)
    trimmed_body_lows = _drop_one_extreme(body_lows, drop_high=False)
    if len(trimmed_body_highs) == 0 or len(trimmed_body_lows) == 0:
        return None
    body_high = float(np.max(trimmed_body_highs))
    body_low = float(np.min(trimmed_body_lows))
    if low <= 0 or body_low <= 0:
        return None
    body_range_ratio = (body_high - body_low) / body_low
    if not (
        avg_daily_body_ratio <= MAX_CONSOLIDATION_AVG_DAILY_BODY_RATIO
        and body_range_ratio <= MAX_CONSOLIDATION_BODY_RANGE_RATIO
    ):
        return None

    return ConsolidationRange(
        start_index=start_index,
        end_index=end_index,
        high=high,
        low=low,
        body_high=body_high,
        body_low=body_low,
        avg_daily_body_ratio=avg_daily_body_ratio,
        body_range_ratio=body_range_ratio,
    )


def _drop_one_extreme(values: np.ndarray, *, drop_high: bool) -> np.ndarray:
    if len(values) <= 1:
        return values
    index = int(np.argmax(values) if drop_high else np.argmin(values))
    return np.delete(values, index)


def _resolve_recent_n_range(
    *,
    frame: StockDailyFrame,
    index: int,
    window_start: int,
) -> NRange | None:
    slope = frame.columns["ma_slope_10"]
    extremes = _ma10_slope_extremes(
        slope=slope,
        start_index=window_start,
        end_index=index,
        threshold=MA10_SLOPE_NOISE_THRESHOLD,
    )
    points = _structure_points_from_slope_extremes(
        frame=frame,
        extremes=extremes,
    )
    low = _latest_structure_point(points, "low")
    high = _latest_structure_point(points, "high")
    if low is None or high is None:
        return None
    previous_low = _previous_structure_point(points, "low", low)
    previous_high = _previous_structure_point(points, "high", high)

    current_slope = float(slope[index])
    if current_slope > MA10_SLOPE_NOISE_THRESHOLD:
        trend_type = "up"
    elif current_slope < -MA10_SLOPE_NOISE_THRESHOLD:
        trend_type = "down"
    else:
        trend_type = "straight"

    return NRange(low=low, high=high, previous_low=previous_low, previous_high=previous_high, trend_type=trend_type)


def _ma10_slope_extremes(
    *,
    slope: np.ndarray,
    start_index: int,
    end_index: int,
    threshold: float,
) -> list[SlopeExtreme]:
    pending_kind: str | None = None
    pending_index: int | None = None
    pending_value: float | None = None
    reversed_extremes: list[SlopeExtreme] = []

    for position in range(end_index, start_index - 1, -1):
        value = float(slope[position])
        if not np.isfinite(value):
            continue
        kind = _slope_kind(value, threshold)
        if kind is None:
            continue
        if pending_kind is None:
            pending_kind = kind
            pending_index = position
            pending_value = value
            continue
        if kind == pending_kind:
            if pending_value is None or _is_stronger_slope(kind, value, pending_value):
                pending_index = position
                pending_value = value
            continue
        reversed_extremes.append(SlopeExtreme(pending_kind, int(pending_index), float(pending_value)))
        pending_kind = kind
        pending_index = position
        pending_value = value

    if pending_kind is not None and pending_index is not None and pending_value is not None:
        reversed_extremes.append(SlopeExtreme(pending_kind, pending_index, pending_value))
    return list(reversed(reversed_extremes))


def _structure_points_from_slope_extremes(
    *,
    frame: StockDailyFrame,
    extremes: list[SlopeExtreme],
) -> list[StructurePoint]:
    closes = frame.columns["qfq_close"]
    points: list[StructurePoint] = []
    for left, right in zip(extremes, extremes[1:]):
        start = min(left.index, right.index)
        end = max(left.index, right.index)
        if start > end:
            continue
        if left.kind == "up" and right.kind == "down":
            high_index, high_price = _highest_value(closes, start, end)
            if high_index is not None:
                points.append(StructurePoint("high", high_index, high_price, left, right))
        elif left.kind == "down" and right.kind == "up":
            low_index, low_price = _lowest_value(closes, start, end)
            if low_index is not None:
                points.append(StructurePoint("low", low_index, low_price, left, right))

    points.sort(key=lambda item: item.index)
    return points


def _latest_structure_point(
    points: list[StructurePoint],
    kind: str,
) -> StructurePoint | None:
    for point in reversed(points):
        if point.kind == kind:
            return point
    return None


def _previous_structure_point(
    points: list[StructurePoint],
    kind: str,
    current: StructurePoint,
) -> StructurePoint | None:
    for point in reversed(points):
        if point.kind == kind and point.index < current.index:
            return point
    return None


def _higher_recent_n_high(n_range: NRange) -> float:
    values = [n_range.high.price]
    if n_range.previous_high is not None:
        values.append(n_range.previous_high.price)
    finite_values = [value for value in values if np.isfinite(value)]
    if not finite_values:
        return float("nan")
    return float(max(finite_values))


def _slope_kind(value: float, threshold: float) -> str | None:
    if value > threshold:
        return "up"
    if value < -threshold:
        return "down"
    return None


def _is_stronger_slope(kind: str, value: float, current: float) -> bool:
    if kind == "up":
        return value > current
    return value < current


def _highest_value(values: np.ndarray, start_index: int, end_index: int) -> tuple[int | None, float]:
    window = values[start_index : end_index + 1]
    if len(window) == 0 or np.isnan(window).all():
        return None, float("nan")
    offset = int(np.nanargmax(window))
    index = start_index + offset
    return index, float(values[index])


def _lowest_value(values: np.ndarray, start_index: int, end_index: int) -> tuple[int | None, float]:
    window = values[start_index : end_index + 1]
    if len(window) == 0 or np.isnan(window).all():
        return None, float("nan")
    offset = int(np.nanargmin(window))
    index = start_index + offset
    return index, float(values[index])


def _slice_by_index_range(
    values: list[T],
    indices: list[int],
    start_index: int,
    end_index: int,
) -> list[T]:
    left = bisect_left(indices, start_index)
    right = bisect_right(indices, end_index)
    return values[left:right]


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
