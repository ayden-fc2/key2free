from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


# ---------------------------------------------------------------------------
# Constants. See a-obsidian-docs/strategies/demo.md for the strategy contract.
# ---------------------------------------------------------------------------

MAX_WATCH_DAYS = 1
DEMO_MAX_HOLDING_DAYS = 40

N_BOTTOM_LOOKBACK = 90
MA10_SLOPE_NOISE_THRESHOLD = 0.005
MIN_H1_L1_RATIO = 0.25
MIN_T_CLOSE_REBOUND_RATIO = 0.1
MAX_T_CLOSE_REBOUND_RATIO = 0.3
KLINE_SEARCH_BEFORE_L2 = 3
MAX_T_AVG_VOLUME10_TO_H1_AVG_VOLUME5_RATIO = 1.0 / 3.0
MAX_T_ATR14_TO_H1_ATR5_RATIO = 0.5
STRUCTURE_EXIT_RETRACE_RATIO = 0.15
MIN_REWARD_RISK_RATIO = 1.5

VOLUME_AVG_MIN_RATIO = 0.8
LONG_BODY_MIN_RATIO = 0.8
LONG_BODY_ATR_MULTIPLE = 0.618
SMALL_CANDLE_ATR_MULTIPLE = 0.6
BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO = 0.618

DEMO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_5",
    "atr_14",
    "ma_slope_10",
    "avg_volume_5",
    "avg_volume_10",
    "body_range_ratio",
    "body_atr14_ratio",
    "range_atr14_ratio",
    "upper_shadow_range_ratio",
    "lower_shadow_range_ratio",
)


@dataclass(frozen=True)
class NBottomContext:
    l1_index: int
    pl1: float
    h1_index: int
    ph1: float
    l2_index: int
    pl2: float
    atr14_t: float
    kline_index: int
    kline_low: float
    k_up_index: int
    k_up_value: float
    k_down_index: int
    k_down_value: float
    avg_volume10_t: float
    avg_volume5_h1: float
    atr5_h1: float


@dataclass(frozen=True)
class KlineSignals:
    passed: np.ndarray
    pattern_lows: np.ndarray


@dataclass(frozen=True)
class NBottomSeries:
    close_nan_cumsum: np.ndarray


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


def demo_code_filter(code: str) -> bool:
    """Keep main-board common A-share codes; date-sensitive ST checks run later."""
    value = code.lower()
    if value.startswith("sh.688") or value.startswith("sz.300") or value.startswith("sz.301"):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


def demo_batch_signal_strategy(
    frame: StockDailyFrame,
    target_indices: list[int],
) -> dict[int, SignalDecision]:
    if not target_indices or len(frame) == 0:
        return {}

    columns = frame.columns
    closes = columns["qfq_close"]

    with np.errstate(invalid="ignore", divide="ignore"):
        kline_signals = _kline_filter_series(columns)
        st_blocked = _st_blocked_series(columns)
        n_bottom_series = _prepare_n_bottom_series(closes)

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if st_blocked[index]:
            continue
        context = _resolve_n_bottom_context(
            index=index,
            frame=frame,
            closes=closes,
            atr14=columns["atr_14"],
            kline_signals=kline_signals,
            n_bottom_series=n_bottom_series,
        )
        if context is None:
            continue

        signal_close = float(closes[index])
        structure_range = context.ph1 - context.pl2
        stop_loss = context.pl2 - STRUCTURE_EXIT_RETRACE_RATIO * structure_range
        take_profit = context.ph1 - STRUCTURE_EXIT_RETRACE_RATIO * structure_range
        risk = signal_close - stop_loss
        reward = take_profit - signal_close
        if not (
            np.isfinite(signal_close)
            and np.isfinite(stop_loss)
            and np.isfinite(take_profit)
            and risk > 0
            and reward > 0
            and reward / risk >= MIN_REWARD_RISK_RATIO
        ):
            continue

        results[index] = SignalDecision(
            triggered=True,
            signal_close=signal_close,
            stop_losses=(stop_loss,),
            take_profits=(take_profit,),
            max_watch_days=MAX_WATCH_DAYS,
            extras={
                "pattern": "n_bottom",
                "tl1": frame.trade_dates[context.l1_index].isoformat(),
                "pl1": context.pl1,
                "th1": frame.trade_dates[context.h1_index].isoformat(),
                "ph1": context.ph1,
                "tl2": frame.trade_dates[context.l2_index].isoformat(),
                "pl2": context.pl2,
                "atr14_t": context.atr14_t,
                "kline_date": frame.trade_dates[context.kline_index].isoformat(),
                "kline_low": context.kline_low,
                "k_up_date": frame.trade_dates[context.k_up_index].isoformat(),
                "k_up_value": context.k_up_value,
                "k_down_date": frame.trade_dates[context.k_down_index].isoformat(),
                "k_down_value": context.k_down_value,
                "avg_volume10_t": context.avg_volume10_t,
                "avg_volume5_h1": context.avg_volume5_h1,
                "atr5_h1": context.atr5_h1,
                "reward_risk_ratio": reward / risk,
            },
        )
    return results


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


def _resolve_n_bottom_context(
    *,
    index: int,
    frame: StockDailyFrame,
    closes: np.ndarray,
    atr14: np.ndarray,
    kline_signals: KlineSignals,
    n_bottom_series: NBottomSeries,
) -> NBottomContext | None:
    atr14_t = float(atr14[index])
    if not np.isfinite(atr14_t) or atr14_t <= 0:
        return None
    window_start = max(0, index + 1 - N_BOTTOM_LOOKBACK)
    if _has_nan_in_range(n_bottom_series.close_nan_cumsum, window_start, index):
        return None

    close_t = float(closes[index])
    if not np.isfinite(close_t):
        return None
    n_context = _resolve_n_bottom_by_ma10_slope(
        frame=frame,
        index=index,
        window_start=window_start,
    )
    if n_context is None:
        return None
    l1_point, h1_point, l2_point = n_context
    l1_index = l1_point.index
    h1_index = h1_point.index
    l2_index = l2_point.index
    pl1 = l1_point.price
    ph1 = h1_point.price
    pl2 = l2_point.price

    if not (l1_index < h1_index < l2_index <= index):
        return None
    if ph1 - pl1 < MIN_H1_L1_RATIO * ph1:
        return None
    if not (pl1 - atr14_t <= pl2 <= pl1 + atr14_t):
        return None
    structure_range = ph1 - pl2
    if structure_range <= 0:
        return None
    if not (
        pl2 + MIN_T_CLOSE_REBOUND_RATIO * structure_range
        <= close_t
        <= pl2 + MAX_T_CLOSE_REBOUND_RATIO * structure_range
    ):
        return None

    try:
        kline_index, kline_low = _resolve_best_kline_pattern(
            l2_index=l2_index,
            index=index,
            pl2=pl2,
            atr14_t=atr14_t,
            kline_signals=kline_signals,
        )
    except ValueError:
        return None

    avg_volume10_t = float(frame.columns["avg_volume_10"][index])
    avg_volume5_h1 = float(frame.columns["avg_volume_5"][h1_index])
    atr5_h1 = float(frame.columns["atr_5"][h1_index])
    if not (
        np.isfinite(avg_volume10_t)
        and np.isfinite(avg_volume5_h1)
        and avg_volume5_h1 > 0
        and avg_volume10_t <= MAX_T_AVG_VOLUME10_TO_H1_AVG_VOLUME5_RATIO * avg_volume5_h1
    ):
        return None
    if not (
        np.isfinite(atr5_h1)
        and atr5_h1 > 0
        and atr14_t <= MAX_T_ATR14_TO_H1_ATR5_RATIO * atr5_h1
    ):
        return None

    return NBottomContext(
        l1_index=l1_index,
        pl1=pl1,
        h1_index=h1_index,
        ph1=ph1,
        l2_index=l2_index,
        pl2=pl2,
        atr14_t=atr14_t,
        kline_index=kline_index,
        kline_low=kline_low,
        k_up_index=h1_point.left_extreme.index,
        k_up_value=h1_point.left_extreme.value,
        k_down_index=l2_point.left_extreme.index,
        k_down_value=l2_point.left_extreme.value,
        avg_volume10_t=avg_volume10_t,
        avg_volume5_h1=avg_volume5_h1,
        atr5_h1=atr5_h1,
    )


def _prepare_n_bottom_series(closes: np.ndarray) -> NBottomSeries:
    close_nan_cumsum = np.concatenate((
        np.array([0], dtype=np.int64),
        np.cumsum(np.isnan(closes).astype(np.int64)),
    ))
    return NBottomSeries(
        close_nan_cumsum=close_nan_cumsum,
    )


def _has_nan_in_range(cumsum: np.ndarray, start: int, end: int) -> bool:
    return int(cumsum[end + 1] - cumsum[start]) > 0


def _resolve_n_bottom_by_ma10_slope(
    *,
    frame: StockDailyFrame,
    index: int,
    window_start: int,
) -> tuple[StructurePoint, StructurePoint, StructurePoint] | None:
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
    if len(points) < 3:
        return None

    for right in range(len(points) - 1, 1, -1):
        l1, h1, l2 = points[right - 2], points[right - 1], points[right]
        if (l1.kind, h1.kind, l2.kind) == ("low", "high", "low"):
            return l1, h1, l2
    return None


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
    window = values[start_index:end_index + 1]
    if len(window) == 0 or np.isnan(window).all():
        return None, float("nan")
    offset = int(np.nanargmax(window))
    index = start_index + offset
    return index, float(values[index])


def _lowest_low(values: np.ndarray, start_index: int, end_index: int) -> tuple[int | None, float]:
    window = values[start_index:end_index + 1]
    if len(window) == 0 or np.isnan(window).all():
        return None, float("nan")
    offset = int(np.nanargmin(window))
    index = start_index + offset
    return index, float(values[index])


def _is_same_price(left: float, right: float) -> bool:
    return abs(left - right) <= max(1e-8, abs(right) * 1e-8)


def _has_valid_kline_pattern(
    *,
    l2_index: int,
    index: int,
    pl2: float,
    atr14_t: float,
    kline_signals: KlineSignals,
) -> bool:
    try:
        _resolve_best_kline_pattern(
            l2_index=l2_index,
            index=index,
            pl2=pl2,
            atr14_t=atr14_t,
            kline_signals=kline_signals,
        )
    except ValueError:
        return False
    return True


def _resolve_best_kline_pattern(
    *,
    l2_index: int,
    index: int,
    pl2: float,
    atr14_t: float,
    kline_signals: KlineSignals,
) -> tuple[int, float]:
    start = max(0, l2_index - KLINE_SEARCH_BEFORE_L2)
    candidates: list[tuple[float, int]] = []
    for position in range(start, index + 1):
        if not kline_signals.passed[position]:
            continue
        low_value = float(kline_signals.pattern_lows[position])
        if not np.isfinite(low_value):
            continue
        if _is_same_price(low_value, pl2):
            candidates.append((low_value, position))
    if not candidates:
        raise ValueError("no valid kline pattern")
    low_value, position = min(candidates, key=lambda item: (item[0], -item[1]))
    return position, low_value


def _kline_filter_series(columns: dict[str, Any]) -> KlineSignals:
    opens = columns["qfq_open"]
    highs = columns["qfq_high"]
    lows = columns["qfq_low"]
    closes = columns["qfq_close"]
    volumes = columns["vol"]
    atr14 = columns["atr_14"]
    avg_volume10 = columns["avg_volume_10"]
    body_ratio = columns["body_range_ratio"]
    body_atr = columns["body_atr14_ratio"]
    range_atr = columns["range_atr14_ratio"]
    upper_ratio = columns["upper_shadow_range_ratio"]
    lower_ratio = columns["lower_shadow_range_ratio"]

    bullish = closes > opens
    bearish = closes < opens
    body = np.abs(closes - opens)
    body_low = np.minimum(opens, closes)
    body_high = np.maximum(opens, closes)

    long_body = (body_ratio >= LONG_BODY_MIN_RATIO) & (body_atr >= LONG_BODY_ATR_MULTIPLE)
    small_candle = range_atr <= SMALL_CANDLE_ATR_MULTIPLE
    volume_ok = volumes >= VOLUME_AVG_MIN_RATIO * _shift_float(avg_volume10, 1)

    dragonfly = (
        (body_ratio <= 0.1)
        & _shadow_ratio_at_least(lower_ratio, upper_ratio, 6.0)
        & volume_ok
    )
    hammer_shape = (body_ratio >= 0.1) & (body_ratio <= 0.4)
    hammer = (
        hammer_shape
        & _shadow_ratio_at_least(lower_ratio, upper_ratio, 4.0)
        & volume_ok
    )
    inverted_hammer_shape = (
        hammer_shape
        & _shadow_ratio_at_least(upper_ratio, lower_ratio, 4.0)
    )

    bullish_long = bullish & long_body
    bearish_long = bearish & long_body
    small_cumsum = np.concatenate(([0], np.cumsum(small_candle.astype(np.int64))))
    morning_star = np.zeros(len(closes), dtype=bool)
    morning_star_low = np.full(len(closes), np.nan)
    for gap in (2, 3, 4):
        left_ok = _shift_bool(bearish_long, gap)
        middle_count = gap - 1
        middle_ok = np.zeros(len(closes), dtype=bool)
        valid = np.arange(len(closes)) >= gap
        starts = np.maximum(np.arange(len(closes)) - gap + 1, 0)
        ends = np.maximum(np.arange(len(closes)), 0)
        counts = small_cumsum[ends] - small_cumsum[starts]
        middle_ok[valid] = counts[valid] == middle_count
        candidate = bullish_long & left_ok & middle_ok
        for position in np.where(candidate)[0]:
            start = position - gap
            low_value = float(np.min(lows[start : position + 1]))
            if not morning_star[position] or low_value < morning_star_low[position]:
                morning_star_low[position] = low_value
        morning_star |= candidate

    engulfing = (
        bullish_long
        & _shift_bool(bearish_long, 1)
        & (_shift_float(body, 1) >= body * BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO)
        & (body_low <= _shift_float(body_low, 1))
        & (body_high >= _shift_float(body_high, 1))
    )

    fairy_guide = (
        bullish_long
        & _shift_bool(inverted_hammer_shape, 1)
        & (closes > _shift_float(highs, 1))
    )

    red_three_soldiers = (
        bullish
        & _shift_bool(bullish, 1)
        & _shift_bool(bullish, 2)
        & (closes > _shift_float(closes, 1))
        & (_shift_float(closes, 1) > _shift_float(closes, 2))
    )

    atr_ok = atr14 > 0
    passed = atr_ok & (
        dragonfly
        | hammer
        | morning_star
        | engulfing
        | fairy_guide
        | red_three_soldiers
    )
    pattern_lows = np.full(len(closes), np.nan)
    for mask, low_values in (
        (dragonfly, lows),
        (hammer, lows),
        (morning_star, morning_star_low),
        (engulfing, _rolling_pattern_low(lows, 1)),
        (fairy_guide, _rolling_pattern_low(lows, 1)),
        (red_three_soldiers, _rolling_pattern_low(lows, 2)),
    ):
        update = mask & (
            np.isnan(pattern_lows)
            | (low_values < pattern_lows)
        )
        pattern_lows[update] = low_values[update]
    pattern_lows[~passed] = np.nan
    return KlineSignals(passed=passed, pattern_lows=pattern_lows)


def _rolling_pattern_low(values: np.ndarray, lookback: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    for position in range(lookback, len(values)):
        window = values[position - lookback : position + 1]
        if np.isnan(window).any():
            continue
        result[position] = float(np.min(window))
    return result


def _shadow_ratio_at_least(
    long_ratio: np.ndarray,
    short_ratio: np.ndarray,
    multiple: float,
) -> np.ndarray:
    return (long_ratio > 0) & ((short_ratio <= 0) | (long_ratio >= multiple * short_ratio))


def _shift_float(values: np.ndarray, count: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if count < len(values):
        result[count:] = values[: len(values) - count]
    return result


def _shift_bool(values: np.ndarray, count: int) -> np.ndarray:
    result = np.zeros(len(values), dtype=bool)
    if count < len(values):
        result[count:] = values[: len(values) - count]
    return result
