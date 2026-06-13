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
MIN_H1_L1_PL1_RATIO = 0.2
MAX_L2_BELOW_L1_ATR_MULTIPLE = 2.0
MAX_L2_ABOVE_L1_ATR_MULTIPLE = 1.0
MIN_T_CLOSE_REBOUND_RATIO = 0.1
MAX_T_CLOSE_REBOUND_RATIO = 0.3
MAX_T_AVG_VOLUME10_TO_H1_AVG_VOLUME5_RATIO = 1.0 / 4.0
MAX_T_ATR14_TO_H1_ATR5_RATIO = 1.0 / 3.0
H1_REFERENCE_OFFSET_DAYS = 2
STRUCTURE_EXIT_RETRACE_RATIO = 0.15
MIN_REWARD_RISK_RATIO = 1.5

DEMO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_5",
    "atr_14",
    "ma_slope_10",
    "avg_volume_5",
    "avg_volume_10",
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
    k_up_index: int
    k_up_value: float
    k_down_index: int
    k_down_value: float
    avg_volume10_t: float
    avg_volume5_h1_plus2: float
    atr5_h1_plus2: float


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
                "k_up_date": frame.trade_dates[context.k_up_index].isoformat(),
                "k_up_value": context.k_up_value,
                "k_down_date": frame.trade_dates[context.k_down_index].isoformat(),
                "k_down_value": context.k_down_value,
                "avg_volume10_t": context.avg_volume10_t,
                "avg_volume5_h1_plus2": context.avg_volume5_h1_plus2,
                "atr5_h1_plus2": context.atr5_h1_plus2,
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
    if ph1 - pl1 < MIN_H1_L1_PL1_RATIO * pl1:
        return None
    if not (
        pl1 - MAX_L2_BELOW_L1_ATR_MULTIPLE * atr14_t
        <= pl2
        <= pl1 + MAX_L2_ABOVE_L1_ATR_MULTIPLE * atr14_t
    ):
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

    avg_volume10_t = float(frame.columns["avg_volume_10"][index])
    h1_ref_index = h1_index + H1_REFERENCE_OFFSET_DAYS
    if h1_ref_index > index:
        return None
    avg_volume5_h1_plus2 = float(frame.columns["avg_volume_5"][h1_ref_index])
    atr5_h1_plus2 = float(frame.columns["atr_5"][h1_ref_index])
    if not (
        np.isfinite(avg_volume10_t)
        and np.isfinite(avg_volume5_h1_plus2)
        and avg_volume5_h1_plus2 > 0
        and avg_volume10_t <= MAX_T_AVG_VOLUME10_TO_H1_AVG_VOLUME5_RATIO * avg_volume5_h1_plus2
    ):
        return None
    if not (
        np.isfinite(atr5_h1_plus2)
        and atr5_h1_plus2 > 0
        and atr14_t <= MAX_T_ATR14_TO_H1_ATR5_RATIO * atr5_h1_plus2
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
        k_up_index=h1_point.left_extreme.index,
        k_up_value=h1_point.left_extreme.value,
        k_down_index=l2_point.left_extreme.index,
        k_down_value=l2_point.left_extreme.value,
        avg_volume10_t=avg_volume10_t,
        avg_volume5_h1_plus2=avg_volume5_h1_plus2,
        atr5_h1_plus2=atr5_h1_plus2,
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
        terminal_index=index,
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
    terminal_index: int,
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

    if extremes:
        last = extremes[-1]
        if last.kind == "down" and last.index <= terminal_index:
            low_index, low_price = _lowest_low(lows, last.index, terminal_index)
            if low_index is not None:
                points.append(StructurePoint("low", low_index, low_price, last, last))
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
