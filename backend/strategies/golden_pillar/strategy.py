"""新版黄金柱战法。

策略口径见 a-obsidian-docs/strategies/黄金柱战法.md。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


# ---------------------------------------------------------------------------
# Constants. Keep in sync with a-obsidian-docs/strategies/黄金柱战法.md.
# ---------------------------------------------------------------------------

MAX_WATCH_DAYS = 1
GOLDEN_PILLAR_POSITION_FRACTION = 1.0 / 3.0
GOLDEN_PILLAR_MAX_HOLDING_DAYS = 15

STRUCTURE_LOOKBACK = 180
MA10_SLOPE_NOISE_THRESHOLD = 0.008
H1_REFERENCE_OFFSET_DAYS = 2

MIN_T_MINUS_1_REMAINING_UPSIDE_RATIO = 0.4
MAX_T_MINUS_1_AVG_VOLUME5_TO_H1_AVG_VOLUME5_RATIO = 0.5
MAX_T_MINUS_1_ATR5_TO_H1_ATR5_RATIO = 0.5

MIN_PILLAR_BODY_OPEN_RATIO = 0.05
MIN_PILLAR_BODY_ATR5_MULTIPLE = 1.6
PRE_PILLAR_CLEAN_DAYS = 15
ENTRY_OPEN_MAX_RATIO = 1.03

GOLDEN_PILLAR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_5",
    "ma_slope_10",
    "avg_volume_5",
)


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
class GoldenPillarContext:
    l1_index: int
    pl1: float
    h1_index: int
    ph1: float
    l2_index: int
    pl2: float
    avg_volume5_t_minus_1: float
    avg_volume5_th1_plus2: float
    atr5_t_minus_1: float
    atr5_th1_plus2: float


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
    closes = columns["qfq_close"]

    with np.errstate(invalid="ignore", divide="ignore"):
        st_blocked = _st_blocked_series(columns)

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        t_minus_1 = index - 1
        if t_minus_1 < 0 or st_blocked[index]:
            continue

        context = _resolve_context(
            frame=frame,
            index=index,
            t_minus_1=t_minus_1,
        )
        if context is None:
            continue

        close_t = float(closes[index])
        close_t_minus_1 = float(closes[t_minus_1])
        open_t = float(opens[index])
        atr5_t_minus_1 = context.atr5_t_minus_1
        if not (
            np.isfinite(close_t)
            and np.isfinite(close_t_minus_1)
            and np.isfinite(open_t)
            and close_t_minus_1 > 0
            and close_t > open_t
        ):
            continue

        pillar_body = close_t - open_t
        pillar_body_open_ratio = pillar_body / open_t if open_t > 0 else float("nan")
        if not (
            np.isfinite(pillar_body_open_ratio)
            and pillar_body_open_ratio >= MIN_PILLAR_BODY_OPEN_RATIO
            and np.isfinite(pillar_body)
            and pillar_body > 0
            and np.isfinite(atr5_t_minus_1)
            and atr5_t_minus_1 > 0
            and pillar_body >= MIN_PILLAR_BODY_ATR5_MULTIPLE * atr5_t_minus_1
        ):
            continue
        if _has_prior_large_bullish_body(
            opens=opens,
            closes=closes,
            atr5=columns["atr_5"],
            index=index,
        ):
            continue

        entry_open_max = close_t * ENTRY_OPEN_MAX_RATIO
        results[index] = SignalDecision(
            triggered=True,
            signal_close=close_t,
            stop_losses=(),
            take_profits=(),
            max_watch_days=MAX_WATCH_DAYS,
            extras={
                "pattern": "golden_pillar",
                "tl1": frame.trade_dates[context.l1_index].isoformat(),
                "pl1": context.pl1,
                "th1": frame.trade_dates[context.h1_index].isoformat(),
                "ph1": context.ph1,
                "tl2": frame.trade_dates[context.l2_index].isoformat(),
                "pl2": context.pl2,
                "avg_volume5_t_minus_1": context.avg_volume5_t_minus_1,
                "avg_volume5_th1_plus2": context.avg_volume5_th1_plus2,
                "atr5_t_minus_1": context.atr5_t_minus_1,
                "atr5_th1_plus2": context.atr5_th1_plus2,
                "pillar_open": open_t,
                "pillar_close": close_t,
                "pillar_body": pillar_body,
                "pillar_body_open_ratio": pillar_body_open_ratio,
                "entry_open_max": entry_open_max,
            },
        )
    return results


def golden_pillar_entry_strategy(*, bar: tuple[float, float, float, float, float, float], watch: Any) -> float | None:
    """T+1 open must not exceed T close by more than 3%; otherwise skip the signal."""
    open_price = float(bar[0])
    extras = (watch.signal or {}).get("extras") or {}
    entry_open_max = extras.get("entry_open_max")
    if not (
        np.isfinite(open_price)
        and isinstance(entry_open_max, (int, float))
        and open_price <= float(entry_open_max)
    ):
        return None
    return open_price


def golden_pillar_exit_plan(
    buy_price: float,
    signal: dict,
) -> tuple[list[float], list[float]] | None:
    extras = signal.get("extras") or {}
    pillar_open = extras.get("pillar_open")
    pillar_body = extras.get("pillar_body")
    if not isinstance(pillar_open, (int, float)) or not isinstance(pillar_body, (int, float)):
        return None
    body = float(pillar_body)
    if not np.isfinite(buy_price) or not np.isfinite(body) or body <= 0:
        return None
    stop_loss = float(pillar_open)
    take_profit = buy_price + body
    if not np.isfinite(stop_loss) or not np.isfinite(take_profit):
        return None
    return ([stop_loss], [take_profit])


def _resolve_context(
    *,
    frame: StockDailyFrame,
    index: int,
    t_minus_1: int,
) -> GoldenPillarContext | None:
    window_start = max(0, t_minus_1 + 1 - STRUCTURE_LOOKBACK)
    n_context = _resolve_structure_by_ma10_slope(
        frame=frame,
        index=t_minus_1,
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
    if not (l1_index < h1_index < l2_index <= t_minus_1):
        return None
    if not (np.isfinite(pl1) and np.isfinite(ph1) and ph1 > pl1 > 0):
        return None

    close_t_minus_1 = float(frame.columns["qfq_close"][t_minus_1])
    max_position = ph1 - MIN_T_MINUS_1_REMAINING_UPSIDE_RATIO * (ph1 - pl1)
    if not (np.isfinite(close_t_minus_1) and close_t_minus_1 <= max_position):
        return None

    h1_ref_index = h1_index + H1_REFERENCE_OFFSET_DAYS
    if h1_ref_index > t_minus_1:
        return None
    avg_volume5_t_minus_1 = float(frame.columns["avg_volume_5"][t_minus_1])
    avg_volume5_th1_plus2 = float(frame.columns["avg_volume_5"][h1_ref_index])
    atr5_t_minus_1 = float(frame.columns["atr_5"][t_minus_1])
    atr5_th1_plus2 = float(frame.columns["atr_5"][h1_ref_index])
    if not (
        np.isfinite(avg_volume5_t_minus_1)
        and np.isfinite(avg_volume5_th1_plus2)
        and avg_volume5_th1_plus2 > 0
        and avg_volume5_t_minus_1
        <= MAX_T_MINUS_1_AVG_VOLUME5_TO_H1_AVG_VOLUME5_RATIO * avg_volume5_th1_plus2
    ):
        return None
    if not (
        np.isfinite(atr5_t_minus_1)
        and np.isfinite(atr5_th1_plus2)
        and atr5_th1_plus2 > 0
        and atr5_t_minus_1 <= MAX_T_MINUS_1_ATR5_TO_H1_ATR5_RATIO * atr5_th1_plus2
    ):
        return None

    return GoldenPillarContext(
        l1_index=l1_index,
        pl1=pl1,
        h1_index=h1_index,
        ph1=ph1,
        l2_index=l2_index,
        pl2=pl2,
        avg_volume5_t_minus_1=avg_volume5_t_minus_1,
        avg_volume5_th1_plus2=avg_volume5_th1_plus2,
        atr5_t_minus_1=atr5_t_minus_1,
        atr5_th1_plus2=atr5_th1_plus2,
    )


def _has_prior_large_bullish_body(
    *,
    opens: np.ndarray,
    closes: np.ndarray,
    atr5: np.ndarray,
    index: int,
) -> bool:
    start = max(0, index - 1 - PRE_PILLAR_CLEAN_DAYS)
    end = index - 1
    if start >= end:
        return False
    for position in range(start, end):
        open_price = float(opens[position])
        close_price = float(closes[position])
        prior_atr5 = float(atr5[position - 1]) if position > 0 else float("nan")
        body = close_price - open_price
        body_ratio = body / open_price if open_price > 0 else float("nan")
        if not (
            np.isfinite(body)
            and np.isfinite(body_ratio)
            and np.isfinite(prior_atr5)
            and prior_atr5 > 0
        ):
            continue
        if (
            body_ratio >= MIN_PILLAR_BODY_OPEN_RATIO
            and body >= MIN_PILLAR_BODY_ATR5_MULTIPLE * prior_atr5
        ):
            return True
    return False


def _resolve_structure_by_ma10_slope(
    *,
    frame: StockDailyFrame,
    index: int,
    window_start: int,
) -> tuple[StructurePoint, StructurePoint, StructurePoint] | None:
    extremes = _ma10_slope_extremes(
        slope=frame.columns["ma_slope_10"],
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
        has_next_high = any(point.kind == "high" for point in points[right + 1 :])
        if (l1.kind, h1.kind, l2.kind) == ("low", "high", "low") and not has_next_high:
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
            if "st" in text.lower() or "*" in text or "＊" in text:
                blocked[position] = True
    return blocked
