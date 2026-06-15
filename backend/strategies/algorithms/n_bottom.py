from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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


def resolve_n_bottom_by_ma_slope(
    *,
    slope: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    start_index: int,
    end_index: int,
    threshold: float,
) -> tuple[StructurePoint, StructurePoint, StructurePoint] | None:
    extremes = ma_slope_extremes(
        slope=slope,
        start_index=start_index,
        end_index=end_index,
        threshold=threshold,
    )
    points = structure_points_from_slope_extremes(
        highs=highs,
        lows=lows,
        extremes=extremes,
        terminal_index=end_index,
    )
    if len(points) < 3:
        return None

    for right in range(len(points) - 1, 1, -1):
        l1, h1, l2 = points[right - 2], points[right - 1], points[right]
        if (l1.kind, h1.kind, l2.kind) == ("low", "high", "low"):
            return l1, h1, l2
    return None


def ma_slope_extremes(
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


def structure_points_from_slope_extremes(
    *,
    highs: np.ndarray,
    lows: np.ndarray,
    extremes: list[SlopeExtreme],
    terminal_index: int,
) -> list[StructurePoint]:
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
