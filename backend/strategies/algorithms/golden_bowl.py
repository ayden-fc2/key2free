from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .trend_channel import TrendChannelConsolidation, detect_trend_channel_consolidation


@dataclass(frozen=True)
class GoldenBowlConfig:
    channel_length: int
    channel_trim_extreme_count: int = 2
    max_channel_width_ratio: float | None = None
    max_channel_close_return_ratio: float | None = None
    min_breakout_body_return_ratio: float | None = None
    min_breakout_to_channel_upper_ratio: float | None = None
    max_channel_end_to_breakout_gap: int = 10
    max_left_high_to_channel_end_close_ratio: float | None = None
    max_bowl_width: int = 12
    min_bowl_width: int = 3
    min_bowl_depth_ratio: float | None = None
    max_bowl_depth_ratio: float | None = None
    right_close_to_left_high_ratio: float = 0.98
    require_right_bullish: bool = True


@dataclass(frozen=True)
class GoldenBowlPattern:
    breakout_index: int
    channel: TrendChannelConsolidation
    channel_end_to_breakout_gap: int
    channel_close_return: float
    breakout_body_return: float
    breakout_ratio: float
    left_close_high: float
    left_close_high_index: int
    trough_close: float
    trough_index: int
    bowl_width: int
    bowl_depth_ratio: float
    right_close_ratio: float


def resolve_golden_bowl(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    target_index: int,
    config: GoldenBowlConfig,
    atr_pct_14: np.ndarray | None = None,
    volume_ratio_20: np.ndarray | None = None,
) -> GoldenBowlPattern | None:
    """Resolve the latest golden-bowl pattern ending at target_index.

    The structure is: trend-channel consolidation -> breakout -> left close
    high -> close trough -> bullish right-side recovery near the left high.
    """
    if target_index < config.channel_length + config.min_bowl_width:
        return None
    close_t = float(closes[target_index])
    open_t = float(opens[target_index])
    if not (np.isfinite(close_t) and np.isfinite(open_t)):
        return None
    if config.require_right_bullish and close_t <= open_t:
        return None

    first_breakout = max(
        config.channel_length,
        target_index - max(config.max_bowl_width, config.min_bowl_width),
    )
    last_breakout = target_index - config.min_bowl_width
    for breakout_index in range(last_breakout, first_breakout - 1, -1):
        breakout = _resolve_channel_breakout(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            breakout_index=breakout_index,
            config=config,
            atr_pct_14=atr_pct_14,
            volume_ratio_20=volume_ratio_20,
        )
        if breakout is None:
            continue
        channel, channel_close_return, breakout_body_return, breakout_ratio = breakout

        close_window = np.asarray(closes[breakout_index:target_index], dtype=float)
        if len(close_window) < 2 or not np.all(np.isfinite(close_window)):
            continue
        left_offset = int(np.argmax(close_window))
        left_close_high_index = breakout_index + left_offset
        if left_close_high_index >= target_index - 1:
            continue
        left_close_high = float(closes[left_close_high_index])
        if not (np.isfinite(left_close_high) and left_close_high > 0):
            continue

        channel_end_close = float(closes[channel.end_index])
        if (
            config.max_left_high_to_channel_end_close_ratio is not None
            and (
                not np.isfinite(channel_end_close)
                or channel_end_close <= 0
                or left_close_high
                > channel_end_close * config.max_left_high_to_channel_end_close_ratio
            )
        ):
            continue

        trough_window = np.asarray(closes[left_close_high_index + 1 : target_index], dtype=float)
        if len(trough_window) == 0 or not np.all(np.isfinite(trough_window)):
            continue
        trough_offset = int(np.argmin(trough_window))
        trough_index = left_close_high_index + 1 + trough_offset
        trough_close = float(closes[trough_index])
        if not (
            np.isfinite(trough_close)
            and trough_close < left_close_high
            and close_t > trough_close
        ):
            continue

        bowl_width = target_index - left_close_high_index
        bowl_depth_ratio = left_close_high / trough_close - 1.0
        if config.min_bowl_depth_ratio is not None and bowl_depth_ratio < config.min_bowl_depth_ratio:
            continue
        if config.max_bowl_depth_ratio is not None and bowl_depth_ratio > config.max_bowl_depth_ratio:
            continue

        right_close_ratio = close_t / left_close_high
        if not (
            np.isfinite(right_close_ratio)
            and right_close_ratio >= config.right_close_to_left_high_ratio
        ):
            continue

        return GoldenBowlPattern(
            breakout_index=breakout_index,
            channel=channel,
            channel_end_to_breakout_gap=breakout_index - channel.end_index,
            channel_close_return=channel_close_return,
            breakout_body_return=breakout_body_return,
            breakout_ratio=breakout_ratio,
            left_close_high=left_close_high,
            left_close_high_index=left_close_high_index,
            trough_close=trough_close,
            trough_index=trough_index,
            bowl_width=bowl_width,
            bowl_depth_ratio=float(bowl_depth_ratio),
            right_close_ratio=float(right_close_ratio),
        )
    return None


def _resolve_channel_breakout(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    breakout_index: int,
    config: GoldenBowlConfig,
    atr_pct_14: np.ndarray | None,
    volume_ratio_20: np.ndarray | None,
) -> tuple[TrendChannelConsolidation, float, float, float] | None:
    open_b = float(opens[breakout_index])
    close_b = float(closes[breakout_index])
    if not (np.isfinite(open_b) and np.isfinite(close_b) and open_b > 0):
        return None
    breakout_body_return = (close_b - open_b) / open_b
    if (
        config.min_breakout_body_return_ratio is not None
        and breakout_body_return < config.min_breakout_body_return_ratio
    ):
        return None

    channel = _find_recent_channel_before_breakout(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        breakout_index=breakout_index,
        config=config,
        atr_pct_14=atr_pct_14,
        volume_ratio_20=volume_ratio_20,
    )
    if channel is None:
        return None

    channel_first_close = float(closes[channel.start_index])
    channel_last_close = float(closes[channel.end_index])
    if not (
        np.isfinite(channel_first_close)
        and np.isfinite(channel_last_close)
        and channel_first_close > 0
    ):
        return None
    channel_close_return = channel_last_close / channel_first_close - 1.0
    if (
        config.max_channel_close_return_ratio is not None
        and channel_close_return > config.max_channel_close_return_ratio
    ):
        return None

    breakout_ratio = (
        close_b / channel.upper_line_end
        if channel.upper_line_end > 0
        else float("nan")
    )
    if (
        config.min_breakout_to_channel_upper_ratio is not None
        and (
            not np.isfinite(breakout_ratio)
            or breakout_ratio < config.min_breakout_to_channel_upper_ratio
        )
    ):
        return None
    return (
        channel,
        float(channel_close_return),
        float(breakout_body_return),
        float(breakout_ratio),
    )


def _find_recent_channel_before_breakout(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    breakout_index: int,
    config: GoldenBowlConfig,
    atr_pct_14: np.ndarray | None,
    volume_ratio_20: np.ndarray | None,
) -> TrendChannelConsolidation | None:
    max_gap = max(1, config.max_channel_end_to_breakout_gap)
    first_end = max(config.channel_length - 1, breakout_index - max_gap)
    last_end = breakout_index - 1
    for channel_end in range(last_end, first_end - 1, -1):
        channel_start = channel_end - config.channel_length + 1
        channel = detect_trend_channel_consolidation(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            start_index=channel_start,
            length=config.channel_length,
            trim_extreme_count=config.channel_trim_extreme_count,
            max_channel_width_ratio=config.max_channel_width_ratio,
            atr_pct_14=atr_pct_14,
            volume_ratio_20=volume_ratio_20,
        )
        if channel is not None and channel.end_index == channel_end:
            return channel
    return None
