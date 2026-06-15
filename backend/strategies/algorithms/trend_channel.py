from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TrendChannelConsolidation:
    start_index: int
    end_index: int
    length: int
    slope: float
    intercept: float
    trend_start_price: float
    trend_end_price: float
    upper_residual: float
    lower_residual: float
    channel_width_ratio: float
    upper_line_start: float
    upper_line_end: float
    lower_line_start: float
    lower_line_end: float
    in_channel_ratio: float
    exception_count: int
    avg_atr_pct_14: float | None = None
    avg_volume_ratio_20: float | None = None


def detect_trend_channel_consolidation(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    start_index: int,
    length: int,
    trim_extreme_count: int = 2,
    max_channel_width_ratio: float | None = None,
    min_in_channel_ratio: float | None = None,
    max_exception_count: int | None = None,
    atr_pct_14: np.ndarray | None = None,
    volume_ratio_20: np.ndarray | None = None,
) -> TrendChannelConsolidation | None:
    """Fit a log-price channel and measure de-trended consolidation width.

    The returned channel is rectangular in log/de-trended space and maps back
    to a parallel rising, flat, or falling price channel.
    """
    if length < 5 or start_index < 0:
        return None
    end_index = start_index + length - 1
    if end_index >= len(closes):
        return None

    open_window = np.asarray(opens[start_index : end_index + 1], dtype=float)
    high_window = np.asarray(highs[start_index : end_index + 1], dtype=float)
    low_window = np.asarray(lows[start_index : end_index + 1], dtype=float)
    close_window = np.asarray(closes[start_index : end_index + 1], dtype=float)
    if not _all_finite_positive(open_window, high_window, low_window, close_window):
        return None

    body_high = np.maximum(open_window, close_window)
    body_low = np.minimum(open_window, close_window)
    body_mid = (body_high + body_low) / 2.0
    if not _all_finite_positive(body_high, body_low, body_mid):
        return None

    x = np.arange(length, dtype=float)
    log_mid = np.log(body_mid)
    slope, intercept = np.polyfit(x, log_mid, 1)
    trend = intercept + slope * x

    upper_residuals = np.log(body_high) - trend
    lower_residuals = np.log(body_low) - trend
    if not np.all(np.isfinite(upper_residuals)) or not np.all(np.isfinite(lower_residuals)):
        return None

    upper_residual = _trimmed_upper(upper_residuals, trim_extreme_count)
    lower_residual = _trimmed_lower(lower_residuals, trim_extreme_count)
    if not (
        np.isfinite(upper_residual)
        and np.isfinite(lower_residual)
        and upper_residual > lower_residual
    ):
        return None

    upper_line = np.exp(trend + upper_residual)
    lower_line = np.exp(trend + lower_residual)
    in_channel = (body_high <= upper_line) & (body_low >= lower_line)
    exception_count = int(length - int(np.sum(in_channel)))
    in_channel_ratio = float(np.mean(in_channel))
    channel_width_ratio = float(np.exp(upper_residual - lower_residual) - 1.0)

    if max_channel_width_ratio is not None and channel_width_ratio > max_channel_width_ratio:
        return None
    if min_in_channel_ratio is not None and in_channel_ratio < min_in_channel_ratio:
        return None
    if max_exception_count is not None and exception_count > max_exception_count:
        return None

    return TrendChannelConsolidation(
        start_index=start_index,
        end_index=end_index,
        length=length,
        slope=float(slope),
        intercept=float(intercept),
        trend_start_price=float(np.exp(trend[0])),
        trend_end_price=float(np.exp(trend[-1])),
        upper_residual=float(upper_residual),
        lower_residual=float(lower_residual),
        channel_width_ratio=channel_width_ratio,
        upper_line_start=float(upper_line[0]),
        upper_line_end=float(upper_line[-1]),
        lower_line_start=float(lower_line[0]),
        lower_line_end=float(lower_line[-1]),
        in_channel_ratio=in_channel_ratio,
        exception_count=exception_count,
        avg_atr_pct_14=_finite_mean(atr_pct_14, start_index, end_index),
        avg_volume_ratio_20=_finite_mean(volume_ratio_20, start_index, end_index),
    )


def scan_trend_channel_consolidations(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    start_index: int,
    end_index: int,
    length: int,
    trim_extreme_count: int = 2,
    max_channel_width_ratio: float | None = None,
    min_in_channel_ratio: float | None = None,
    max_exception_count: int | None = None,
    atr_pct_14: np.ndarray | None = None,
    volume_ratio_20: np.ndarray | None = None,
) -> list[TrendChannelConsolidation]:
    ranges: list[TrendChannelConsolidation] = []
    first_start = max(0, start_index)
    last_start = min(end_index - length + 1, len(closes) - length)
    for current_start in range(first_start, last_start + 1):
        item = detect_trend_channel_consolidation(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            start_index=current_start,
            length=length,
            trim_extreme_count=trim_extreme_count,
            max_channel_width_ratio=max_channel_width_ratio,
            min_in_channel_ratio=min_in_channel_ratio,
            max_exception_count=max_exception_count,
            atr_pct_14=atr_pct_14,
            volume_ratio_20=volume_ratio_20,
        )
        if item is not None:
            ranges.append(item)
    return ranges


def find_latest_trend_channel_consolidation(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    end_index: int,
    length: int,
    lookback: int,
    trim_extreme_count: int = 2,
    max_channel_width_ratio: float | None = None,
    min_in_channel_ratio: float | None = None,
    max_exception_count: int | None = None,
    atr_pct_14: np.ndarray | None = None,
    volume_ratio_20: np.ndarray | None = None,
) -> TrendChannelConsolidation | None:
    start_index = max(0, end_index + 1 - lookback)
    ranges = scan_trend_channel_consolidations(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        start_index=start_index,
        end_index=end_index,
        length=length,
        trim_extreme_count=trim_extreme_count,
        max_channel_width_ratio=max_channel_width_ratio,
        min_in_channel_ratio=min_in_channel_ratio,
        max_exception_count=max_exception_count,
        atr_pct_14=atr_pct_14,
        volume_ratio_20=volume_ratio_20,
    )
    return ranges[-1] if ranges else None


def _trimmed_upper(values: np.ndarray, trim_extreme_count: int) -> float:
    ordered = np.sort(values)
    trim = max(0, min(trim_extreme_count, len(ordered) - 1))
    return float(ordered[-(trim + 1)])


def _trimmed_lower(values: np.ndarray, trim_extreme_count: int) -> float:
    ordered = np.sort(values)
    trim = max(0, min(trim_extreme_count, len(ordered) - 1))
    return float(ordered[trim])


def _finite_mean(values: np.ndarray | None, start_index: int, end_index: int) -> float | None:
    if values is None or end_index >= len(values):
        return None
    window = np.asarray(values[start_index : end_index + 1], dtype=float)
    finite = window[np.isfinite(window)]
    if len(finite) == 0:
        return None
    return float(np.mean(finite))


def _all_finite_positive(*arrays: np.ndarray) -> bool:
    for array in arrays:
        if len(array) == 0 or not np.all(np.isfinite(array)) or np.any(array <= 0):
            return False
    return True
