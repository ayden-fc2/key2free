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

LOOKBACK_BARS = 400
RECENT_SIGNAL_BARS = 10

T1_VOLUME_TO_AVG5_MULTIPLE = 1.2
T1_BODY_OPEN_RATIO = 0.04
T1_BODY_ATR5_MULTIPLE = 1.5
CONFIRM_BODY_TO_T1_BODY_RATIO = 0.5
MAX_T4_UP_BODY_TO_T1_BODY_RATIO = 1.2

CONSOLIDATION_BARS = 30
MAX_CONSOLIDATION_AVG_DAILY_RANGE_RATIO = 0.03
MAX_CONSOLIDATION_TOTAL_RANGE_RATIO = 0.10

BREAKOUT_TO_CONSOLIDATION_HIGH_RATIO = 1.03
STOP_LOSS_2_RATIO = 1.03
MIN_TAKE_PROFIT_1_RATIO = 1.06
MAX_TAKE_PROFIT_1_RATIO = 1.10
MIN_TAKE_PROFIT_2_RATIO = 1.09
MAX_TAKE_PROFIT_2_RATIO = 1.15
TAKE_PROFIT_1_RISK_MULTIPLE = 1.5
TAKE_PROFIT_2_RISK_MULTIPLE = 2.2
MA10_SLOPE_NOISE_THRESHOLD = 0.008
MAX_N_RANGE_CLOSE_POSITION_RATIO = 0.40
MAX_TAKE_PROFIT_2_N_RANGE_RATIO = 0.90

PILLAR_TYPE_GOLDEN = "golden_pillar"
PILLAR_TYPE_GENERAL = "general_pillar"

GOLDEN_PILLAR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_5",
    "avg_volume_5",
    "ma_slope_10",
)


@dataclass(frozen=True)
class PillarPattern:
    type: str
    t4_kind: str
    t1_index: int
    t2_index: int
    t3_index: int
    t4_index: int
    structure_low: float
    structure_high: float
    confirm_mid_avg: float
    t1_body: float


@dataclass(frozen=True)
class ConsolidationRange:
    start_index: int
    end_index: int
    high: float
    low: float
    avg_daily_range_ratio: float
    total_range_ratio: float


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

    all_consolidations = _scan_consolidation_ranges(frame, 0, len(frame) - 1)
    all_patterns = _scan_pillar_patterns(frame, 0, len(frame) - 1)
    consolidation_end_indices = [item.end_index for item in all_consolidations]
    pattern_t4_indices = [item.t4_index for item in all_patterns]

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if index < LOOKBACK_BARS - 1 or st_blocked[index]:
            continue

        close_t = float(closes[index])
        if not np.isfinite(close_t):
            continue

        window_start = index + 1 - LOOKBACK_BARS
        recent_start = max(window_start, index - RECENT_SIGNAL_BARS)

        recent_consolidations = _slice_by_index_range(
            all_consolidations,
            consolidation_end_indices,
            recent_start,
            index,
        )
        if not recent_consolidations:
            continue
        consolidation = recent_consolidations[-1]

        recent_patterns = _slice_by_index_range(
            all_patterns,
            pattern_t4_indices,
            recent_start,
            index,
        )
        if not recent_patterns:
            continue

        n_range = _resolve_recent_n_range(
            frame=frame,
            index=index,
            window_start=window_start,
        )
        if n_range is None:
            continue
        n_low = n_range.low.price
        n_high = n_range.high.price
        n_range_size = n_high - n_low
        if not (
            np.isfinite(n_low)
            and np.isfinite(n_high)
            and n_low > 0
            and n_high > n_low
            and close_t <= n_low + MAX_N_RANGE_CLOSE_POSITION_RATIO * n_range_size
        ):
            continue

        consolidation_mid = (consolidation.high + consolidation.low) / 2.0
        if not (
            np.isfinite(consolidation.high)
            and np.isfinite(consolidation.low)
            and consolidation.high > 0
            and consolidation.low > 0
            and np.isfinite(consolidation_mid)
            and close_t >= BREAKOUT_TO_CONSOLIDATION_HIGH_RATIO * consolidation.high
        ):
            continue

        stop_loss_1 = consolidation_mid
        stop_loss_2 = close_t * STOP_LOSS_2_RATIO
        risk = close_t - stop_loss_1
        if not np.isfinite(risk) or risk <= 0:
            continue
        take_profit_1 = _clamp(
            close_t + risk * TAKE_PROFIT_1_RISK_MULTIPLE,
            close_t * MIN_TAKE_PROFIT_1_RATIO,
            close_t * MAX_TAKE_PROFIT_1_RATIO,
        )
        take_profit_2 = _clamp(
            close_t + risk * TAKE_PROFIT_2_RISK_MULTIPLE,
            close_t * MIN_TAKE_PROFIT_2_RATIO,
            close_t * MAX_TAKE_PROFIT_2_RATIO,
        )
        n_take_profit_2_limit = n_low + MAX_TAKE_PROFIT_2_N_RANGE_RATIO * n_range_size
        if not take_profit_2 < n_take_profit_2_limit:
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
                "consolidation_mid": consolidation_mid,
                "consolidation_avg_daily_range_ratio": consolidation.avg_daily_range_ratio,
                "consolidation_total_range_ratio": consolidation.total_range_ratio,
                "pillar_count_t10_t": len(recent_patterns),
                "pillar_types_t10_t": [pattern.type for pattern in recent_patterns],
                "latest_pillar_type": recent_patterns[-1].type,
                "latest_pillar_t1": frame.trade_dates[recent_patterns[-1].t1_index].isoformat(),
                "latest_pillar_t4": frame.trade_dates[recent_patterns[-1].t4_index].isoformat(),
                "n_low": n_low,
                "n_low_date": frame.trade_dates[n_range.low.index].isoformat(),
                "n_high": n_high,
                "n_high_date": frame.trade_dates[n_range.high.index].isoformat(),
                "n_trend_type": n_range.trend_type,
                "n_close_position_ratio": (close_t - n_low) / n_range_size,
                "n_take_profit_2_limit": n_take_profit_2_limit,
                "breakout_ratio": close_t / consolidation.high,
                "risk": risk,
                "stop_loss_1": float(stop_loss_1),
                "stop_loss_2": float(stop_loss_2),
                "take_profit_1": float(take_profit_1),
                "take_profit_2": float(take_profit_2),
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
    last_t1 = end_index - 3
    for t1_index in range(first_t1, last_t1 + 1):
        pattern = _detect_pillar_pattern(frame, t1_index)
        if pattern is not None and pattern.t4_index <= end_index:
            patterns.append(pattern)
    return patterns


def _detect_pillar_pattern(frame: StockDailyFrame, t1_index: int) -> PillarPattern | None:
    columns = frame.columns
    opens = columns["qfq_open"]
    highs = columns["qfq_high"]
    lows = columns["qfq_low"]
    closes = columns["qfq_close"]
    volumes = columns["vol"]
    avg_volume5 = columns["avg_volume_5"]
    atr5 = columns["atr_5"]

    t0_index = t1_index - 1
    t2_index = t1_index + 1
    t3_index = t1_index + 2
    t4_index = t1_index + 3
    if t0_index < 0 or t4_index >= len(frame):
        return None

    indices = [t1_index, t2_index, t3_index, t4_index]
    values = [
        *(float(opens[index]) for index in indices),
        *(float(highs[index]) for index in indices),
        *(float(lows[index]) for index in indices),
        *(float(closes[index]) for index in indices),
        float(volumes[t1_index]),
        float(avg_volume5[t0_index]),
        float(atr5[t0_index]),
    ]
    if not all(np.isfinite(value) for value in values):
        return None

    open1 = float(opens[t1_index])
    close1 = float(closes[t1_index])
    volume1 = float(volumes[t1_index])
    avg_volume5_t0 = float(avg_volume5[t0_index])
    atr5_t0 = float(atr5[t0_index])
    body1 = abs(close1 - open1)
    if not (
        open1 > 0
        and close1 > open1
        and avg_volume5_t0 > 0
        and atr5_t0 > 0
        and volume1 >= T1_VOLUME_TO_AVG5_MULTIPLE * avg_volume5_t0
        and body1 >= min(T1_BODY_OPEN_RATIO * open1, T1_BODY_ATR5_MULTIPLE * atr5_t0)
    ):
        return None

    body2 = abs(float(closes[t2_index]) - float(opens[t2_index]))
    body3 = abs(float(closes[t3_index]) - float(opens[t3_index]))
    body4 = abs(float(closes[t4_index]) - float(opens[t4_index]))
    max_confirm_body = CONFIRM_BODY_TO_T1_BODY_RATIO * body1
    if body2 > max_confirm_body or body3 > max_confirm_body:
        return None
    t4_is_short = body4 <= max_confirm_body
    t4_is_up_pillar = (
        max_confirm_body <= body4 <= MAX_T4_UP_BODY_TO_T1_BODY_RATIO * body1
        and float(closes[t4_index]) > float(opens[t4_index])
    )
    if not (t4_is_short or t4_is_up_pillar):
        return None

    confirm_mid_avg = float(
        np.mean(
            [
                _mid_body(opens, closes, t2_index),
                _mid_body(opens, closes, t3_index),
                _mid_body(opens, closes, t4_index),
            ]
        )
    )
    t1_body_low = min(open1, close1)
    t1_body_high = max(open1, close1)
    t1_front_2_3_upper = t1_body_low + (t1_body_high - t1_body_low) * 2.0 / 3.0
    if confirm_mid_avg > close1:
        pattern_type = PILLAR_TYPE_GOLDEN
    elif t1_body_low <= confirm_mid_avg <= t1_front_2_3_upper:
        pattern_type = PILLAR_TYPE_GENERAL
    else:
        return None

    structure_low = float(np.nanmin(lows[t1_index : t4_index + 1]))
    structure_high = float(np.nanmax(highs[t1_index : t4_index + 1]))
    if not (np.isfinite(structure_low) and np.isfinite(structure_high)):
        return None

    return PillarPattern(
        type=pattern_type,
        t4_kind="short" if t4_is_short else "up_pillar",
        t1_index=t1_index,
        t2_index=t2_index,
        t3_index=t3_index,
        t4_index=t4_index,
        structure_low=structure_low,
        structure_high=structure_high,
        confirm_mid_avg=confirm_mid_avg,
        t1_body=body1,
    )


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
        daily_range_ratios = (highs - lows) / closes
    if not np.all(np.isfinite(daily_range_ratios)):
        return None

    avg_daily_range_ratio = float(np.mean(daily_range_ratios))
    high = float(np.max(highs))
    low = float(np.min(lows))
    if low <= 0:
        return None
    total_range_ratio = (high - low) / low
    if not (
        avg_daily_range_ratio <= MAX_CONSOLIDATION_AVG_DAILY_RANGE_RATIO
        and total_range_ratio <= MAX_CONSOLIDATION_TOTAL_RANGE_RATIO
    ):
        return None

    return ConsolidationRange(
        start_index=start_index,
        end_index=end_index,
        high=high,
        low=low,
        avg_daily_range_ratio=avg_daily_range_ratio,
        total_range_ratio=total_range_ratio,
    )


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

    current_slope = float(slope[index])
    if current_slope > MA10_SLOPE_NOISE_THRESHOLD:
        trend_type = "up"
    elif current_slope < -MA10_SLOPE_NOISE_THRESHOLD:
        trend_type = "down"
    else:
        trend_type = "straight"

    return NRange(low=low, high=high, trend_type=trend_type)


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
    highs = frame.columns["qfq_high"]
    lows = frame.columns["qfq_low"]
    points: list[StructurePoint] = []
    for left, right in zip(extremes, extremes[1:]):
        start = min(left.index, right.index)
        end = max(left.index, right.index)
        if start > end:
            continue
        if left.kind == "up" and right.kind == "down":
            high_index, high_price = _highest_high(highs, start, end)
            if high_index is not None:
                points.append(StructurePoint("high", high_index, high_price, left, right))
        elif left.kind == "down" and right.kind == "up":
            low_index, low_price = _lowest_low(lows, start, end)
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


def _highest_high(values: np.ndarray, start_index: int, end_index: int) -> tuple[int | None, float]:
    window = values[start_index : end_index + 1]
    if len(window) == 0 or np.isnan(window).all():
        return None, float("nan")
    offset = int(np.nanargmax(window))
    index = start_index + offset
    return index, float(values[index])


def _lowest_low(values: np.ndarray, start_index: int, end_index: int) -> tuple[int | None, float]:
    window = values[start_index : end_index + 1]
    if len(window) == 0 or np.isnan(window).all():
        return None, float("nan")
    offset = int(np.nanargmin(window))
    index = start_index + offset
    return index, float(values[index])


def _mid_body(opens: np.ndarray, closes: np.ndarray, index: int) -> float:
    return (float(opens[index]) + float(closes[index])) / 2.0


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


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
