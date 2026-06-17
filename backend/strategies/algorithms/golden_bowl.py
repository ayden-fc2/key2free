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
    max_bowl_order: int = 2
    min_next_bowl_left_high_ratio: float | None = None
    max_bowl_width: int = 12
    min_bowl_width: int = 3
    min_bowl_depth_ratio: float | None = None
    max_bowl_depth_ratio: float | None = None
    right_close_to_left_high_ratio: float = 0.98
    max_right_close_to_left_high_ratio: float | None = None
    require_right_bullish: bool = True
    min_bottom_bounce_bullish_days: int = 2
    max_bottom_bounce_body_return_ratio: float | None = None
    require_bottom_bounce_bullish: bool = True
    require_bottom_bounce_low_non_decreasing: bool = True


@dataclass(frozen=True)
class GoldenBowlPattern:
    signal_index: int
    bowl_order: int
    breakout_index: int
    channel: TrendChannelConsolidation | None
    channel_end_to_breakout_gap: int | None
    channel_close_return: float | None
    breakout_body_return: float
    breakout_ratio: float
    left_close_high: float
    left_close_high_index: int
    trough_close: float
    trough_index: int
    bowl_width: int
    bowl_depth_ratio: float
    right_close_ratio: float
    previous_left_close_high: float | None = None
    previous_signal_index: int | None = None
    ma_bull_start_index: int | None = None
    ma_bull_end_index: int | None = None
    ma_bull_days: int | None = None
    bottom_low: float | None = None
    bottom_low_index: int | None = None
    bounce_days: int | None = None
    bounce_body_return_1: float | None = None
    bounce_body_return_2: float | None = None


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
        target_index - max(config.max_bowl_width, config.min_bowl_width) * max(config.max_bowl_order, 1),
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
        sequence = _resolve_bowl_sequence(
            closes=closes,
            opens=opens,
            target_index=target_index,
            breakout_index=breakout_index,
            channel=channel,
            channel_close_return=channel_close_return,
            breakout_body_return=breakout_body_return,
            breakout_ratio=breakout_ratio,
            config=config,
        )
        if sequence and sequence[-1].signal_index == target_index:
            return sequence[-1]
    return None


def resolve_golden_bowl_after_ma_bull(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    ma_5: np.ndarray,
    ma_10: np.ndarray,
    ma_20: np.ndarray,
    target_index: int,
    config: GoldenBowlConfig,
    min_ma_bull_days: int,
) -> GoldenBowlPattern | None:
    """Resolve a golden bowl after a sustained MA bullish alignment.

    The structure is: MA5 > MA10 > MA20 for at least ``min_ma_bull_days``
    before breakout -> breakout candle -> left close high -> close trough ->
    bullish right-side recovery near the left high.
    """
    if target_index < config.min_bowl_width + min_ma_bull_days + 1:
        return None
    close_t = float(closes[target_index])
    open_t = float(opens[target_index])
    if not (np.isfinite(close_t) and np.isfinite(open_t)):
        return None
    if config.require_right_bullish and close_t <= open_t:
        return None

    first_breakout = max(
        min_ma_bull_days,
        target_index - max(config.max_bowl_width, config.min_bowl_width) * max(config.max_bowl_order, 1),
    )
    last_breakout = target_index - config.min_bowl_width
    for breakout_index in range(last_breakout, first_breakout - 1, -1):
        breakout = _resolve_ma_bull_breakout(
            opens=opens,
            closes=closes,
            ma_5=ma_5,
            ma_10=ma_10,
            ma_20=ma_20,
            breakout_index=breakout_index,
            config=config,
            min_ma_bull_days=min_ma_bull_days,
        )
        if breakout is None:
            continue
        ma_bull_start, ma_bull_end, ma_bull_days, breakout_body_return, breakout_ratio = breakout
        sequence = _resolve_bowl_sequence(
            closes=closes,
            opens=opens,
            target_index=target_index,
            breakout_index=breakout_index,
            channel=None,
            channel_close_return=None,
            breakout_body_return=breakout_body_return,
            breakout_ratio=breakout_ratio,
            config=config,
            ma_bull_start_index=ma_bull_start,
            ma_bull_end_index=ma_bull_end,
            ma_bull_days=ma_bull_days,
        )
        if sequence and sequence[-1].signal_index == target_index:
            return sequence[-1]
    return None


def resolve_golden_bowl_bottom_bounce_after_ma_bull(
    *,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    ma_5: np.ndarray,
    ma_10: np.ndarray,
    ma_20: np.ndarray,
    target_index: int,
    config: GoldenBowlConfig,
    min_ma_bull_days: int,
) -> GoldenBowlPattern | None:
    """Resolve an earlier golden-bowl entry at bottom-bounce confirmation.

    The signal day is the second small bullish candle after the bowl bottom,
    so this resolver does not require the right side to recover near the left
    high before signaling.
    """
    bounce_days = max(2, int(config.min_bottom_bounce_bullish_days))
    if target_index < bounce_days + min_ma_bull_days + 1:
        return None

    if not _is_bottom_bounce_confirmation(
        opens=opens,
        lows=lows,
        closes=closes,
        target_index=target_index,
        bounce_days=bounce_days,
        max_body_return_ratio=config.max_bottom_bounce_body_return_ratio,
        require_bullish=config.require_bottom_bounce_bullish,
        require_low_non_decreasing=config.require_bottom_bounce_low_non_decreasing,
    ):
        return None

    first_breakout = max(
        min_ma_bull_days,
        target_index - max(config.max_bowl_width, config.min_bowl_width) * max(config.max_bowl_order, 1),
    )
    last_breakout = target_index - bounce_days
    for breakout_index in range(last_breakout, first_breakout - 1, -1):
        breakout = _resolve_ma_bull_breakout(
            opens=opens,
            closes=closes,
            ma_5=ma_5,
            ma_10=ma_10,
            ma_20=ma_20,
            breakout_index=breakout_index,
            config=config,
            min_ma_bull_days=min_ma_bull_days,
        )
        if breakout is None:
            continue
        ma_bull_start, ma_bull_end, ma_bull_days, breakout_body_return, breakout_ratio = breakout
        sequence = _resolve_bottom_bounce_sequence(
            opens=opens,
            lows=lows,
            closes=closes,
            target_index=target_index,
            breakout_index=breakout_index,
            breakout_body_return=breakout_body_return,
            breakout_ratio=breakout_ratio,
            config=config,
            ma_bull_start_index=ma_bull_start,
            ma_bull_end_index=ma_bull_end,
            ma_bull_days=ma_bull_days,
        )
        if sequence and sequence[-1].signal_index == target_index:
            return sequence[-1]
    return None


def _resolve_bowl_sequence(
    *,
    closes: np.ndarray,
    opens: np.ndarray,
    target_index: int,
    breakout_index: int,
    channel: TrendChannelConsolidation | None,
    channel_close_return: float | None,
    breakout_body_return: float,
    breakout_ratio: float,
    config: GoldenBowlConfig,
    ma_bull_start_index: int | None = None,
    ma_bull_end_index: int | None = None,
    ma_bull_days: int | None = None,
) -> list[GoldenBowlPattern]:
    sequence: list[GoldenBowlPattern] = []
    first_target = breakout_index + config.min_bowl_width
    for index in range(first_target, target_index + 1):
        pattern = _resolve_bowl_shape(
            closes=closes,
            opens=opens,
            target_index=index,
            breakout_index=breakout_index,
            channel=channel,
            channel_close_return=channel_close_return,
            breakout_body_return=breakout_body_return,
            breakout_ratio=breakout_ratio,
            config=config,
            ma_bull_start_index=ma_bull_start_index,
            ma_bull_end_index=ma_bull_end_index,
            ma_bull_days=ma_bull_days,
        )
        if pattern is None:
            continue
        if not sequence:
            if not _is_valid_first_bowl(pattern=pattern, closes=closes, config=config):
                continue
            sequence.append(pattern)
            continue

        previous = sequence[-1]
        if (
            pattern.left_close_high_index == previous.left_close_high_index
            and pattern.trough_index == previous.trough_index
        ):
            continue
        if len(sequence) >= max(config.max_bowl_order, 1):
            continue
        if not _is_valid_next_bowl(pattern=pattern, previous=previous, config=config):
            continue
        sequence.append(
            _with_sequence_context(
                pattern=pattern,
                bowl_order=previous.bowl_order + 1,
                previous=previous,
            )
        )
    return sequence


def _resolve_bowl_shape(
    *,
    closes: np.ndarray,
    opens: np.ndarray,
    target_index: int,
    breakout_index: int,
    channel: TrendChannelConsolidation | None,
    channel_close_return: float | None,
    breakout_body_return: float,
    breakout_ratio: float,
    config: GoldenBowlConfig,
    ma_bull_start_index: int | None = None,
    ma_bull_end_index: int | None = None,
    ma_bull_days: int | None = None,
) -> GoldenBowlPattern | None:
    close_t = float(closes[target_index])
    open_t = float(opens[target_index])
    if not (np.isfinite(close_t) and np.isfinite(open_t)):
        return None
    if config.require_right_bullish and close_t <= open_t:
        return None

    close_window = np.asarray(closes[breakout_index:target_index], dtype=float)
    if len(close_window) < 2 or not np.all(np.isfinite(close_window)):
        return None
    left_offset = int(np.argmax(close_window))
    left_close_high_index = breakout_index + left_offset
    if left_close_high_index >= target_index - 1:
        return None
    left_close_high = float(closes[left_close_high_index])
    if not (np.isfinite(left_close_high) and left_close_high > 0):
        return None

    trough_window = np.asarray(closes[left_close_high_index + 1 : target_index], dtype=float)
    if len(trough_window) == 0 or not np.all(np.isfinite(trough_window)):
        return None
    trough_offset = int(np.argmin(trough_window))
    trough_index = left_close_high_index + 1 + trough_offset
    trough_close = float(closes[trough_index])
    if not (
        np.isfinite(trough_close)
        and trough_close < left_close_high
        and close_t > trough_close
    ):
        return None

    bowl_width = target_index - left_close_high_index
    if bowl_width < config.min_bowl_width or bowl_width > config.max_bowl_width:
        return None
    bowl_depth_ratio = left_close_high / trough_close - 1.0
    if config.min_bowl_depth_ratio is not None and bowl_depth_ratio < config.min_bowl_depth_ratio:
        return None
    if config.max_bowl_depth_ratio is not None and bowl_depth_ratio > config.max_bowl_depth_ratio:
        return None

    right_close_ratio = close_t / left_close_high
    if not (
        np.isfinite(right_close_ratio)
        and right_close_ratio >= config.right_close_to_left_high_ratio
    ):
        return None
    if (
        config.max_right_close_to_left_high_ratio is not None
        and right_close_ratio > config.max_right_close_to_left_high_ratio
    ):
        return None

    return GoldenBowlPattern(
        signal_index=target_index,
        bowl_order=1,
        breakout_index=breakout_index,
        channel=channel,
        channel_end_to_breakout_gap=(
            None if channel is None else breakout_index - channel.end_index
        ),
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
        ma_bull_start_index=ma_bull_start_index,
        ma_bull_end_index=ma_bull_end_index,
        ma_bull_days=ma_bull_days,
    )


def _is_valid_first_bowl(
    *,
    pattern: GoldenBowlPattern,
    closes: np.ndarray,
    config: GoldenBowlConfig,
) -> bool:
    if config.max_left_high_to_channel_end_close_ratio is None:
        return True
    if pattern.channel is None:
        return False
    channel_end_close = float(closes[pattern.channel.end_index])
    return (
        np.isfinite(channel_end_close)
        and channel_end_close > 0
        and pattern.left_close_high
        <= channel_end_close * config.max_left_high_to_channel_end_close_ratio
    )


def _is_valid_next_bowl(
    *,
    pattern: GoldenBowlPattern,
    previous: GoldenBowlPattern,
    config: GoldenBowlConfig,
) -> bool:
    return (
        pattern.left_close_high_index > previous.signal_index
        and pattern.trough_index > previous.signal_index
        and (
            config.min_next_bowl_left_high_ratio is None
            or pattern.left_close_high
            >= previous.left_close_high * config.min_next_bowl_left_high_ratio
        )
    )


def _with_sequence_context(
    *,
    pattern: GoldenBowlPattern,
    bowl_order: int,
    previous: GoldenBowlPattern | None,
) -> GoldenBowlPattern:
    return GoldenBowlPattern(
        signal_index=pattern.signal_index,
        bowl_order=bowl_order,
        breakout_index=pattern.breakout_index,
        channel=pattern.channel,
        channel_end_to_breakout_gap=pattern.channel_end_to_breakout_gap,
        channel_close_return=pattern.channel_close_return,
        breakout_body_return=pattern.breakout_body_return,
        breakout_ratio=pattern.breakout_ratio,
        left_close_high=pattern.left_close_high,
        left_close_high_index=pattern.left_close_high_index,
        trough_close=pattern.trough_close,
        trough_index=pattern.trough_index,
        bowl_width=pattern.bowl_width,
        bowl_depth_ratio=pattern.bowl_depth_ratio,
        right_close_ratio=pattern.right_close_ratio,
        previous_left_close_high=None if previous is None else previous.left_close_high,
        previous_signal_index=None if previous is None else previous.signal_index,
        ma_bull_start_index=pattern.ma_bull_start_index,
        ma_bull_end_index=pattern.ma_bull_end_index,
        ma_bull_days=pattern.ma_bull_days,
        bottom_low=pattern.bottom_low,
        bottom_low_index=pattern.bottom_low_index,
        bounce_days=pattern.bounce_days,
        bounce_body_return_1=pattern.bounce_body_return_1,
        bounce_body_return_2=pattern.bounce_body_return_2,
    )


def _resolve_bottom_bounce_shape(
    *,
    opens: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    target_index: int,
    breakout_index: int,
    breakout_body_return: float,
    breakout_ratio: float,
    config: GoldenBowlConfig,
    ma_bull_start_index: int | None,
    ma_bull_end_index: int | None,
    ma_bull_days: int | None,
) -> GoldenBowlPattern | None:
    bounce_days = max(2, int(config.min_bottom_bounce_bullish_days))
    left_window_end = target_index - bounce_days
    if left_window_end <= breakout_index:
        return None

    close_window = np.asarray(closes[breakout_index : left_window_end + 1], dtype=float)
    if len(close_window) < 2 or not np.all(np.isfinite(close_window)):
        return None
    left_offset = int(np.argmax(close_window))
    left_close_high_index = breakout_index + left_offset
    if left_close_high_index >= target_index - bounce_days:
        return None
    left_close_high = float(closes[left_close_high_index])
    if not (np.isfinite(left_close_high) and left_close_high > 0):
        return None

    trough_close_window = np.asarray(closes[left_close_high_index + 1 : target_index + 1], dtype=float)
    if len(trough_close_window) < bounce_days or not np.all(np.isfinite(trough_close_window)):
        return None
    trough_offset = int(np.argmin(trough_close_window))
    trough_index = left_close_high_index + 1 + trough_offset
    trough_close = float(closes[trough_index])
    if not (
        np.isfinite(trough_close)
        and trough_close < left_close_high
        and trough_index <= target_index - 1
        and float(closes[target_index]) < left_close_high
        and float(closes[target_index]) > trough_close
    ):
        return None

    bottom_low_window = np.asarray(lows[left_close_high_index + 1 : target_index + 1], dtype=float)
    if len(bottom_low_window) == 0 or not np.all(np.isfinite(bottom_low_window)):
        return None
    bottom_low_offset = int(np.argmin(bottom_low_window))
    bottom_low_index = left_close_high_index + 1 + bottom_low_offset
    bottom_low = float(lows[bottom_low_index])
    if not (
        np.isfinite(bottom_low)
        and bottom_low > 0
        and bottom_low_index <= target_index - 1
    ):
        return None

    bowl_width = target_index - left_close_high_index
    if bowl_width < config.min_bowl_width or bowl_width > config.max_bowl_width:
        return None
    bowl_depth_ratio = left_close_high / trough_close - 1.0
    if config.min_bowl_depth_ratio is not None and bowl_depth_ratio < config.min_bowl_depth_ratio:
        return None
    if config.max_bowl_depth_ratio is not None and bowl_depth_ratio > config.max_bowl_depth_ratio:
        return None

    body_returns = [
        _body_return(opens[index], closes[index])
        for index in range(target_index - bounce_days + 1, target_index + 1)
    ]
    return GoldenBowlPattern(
        signal_index=target_index,
        bowl_order=1,
        breakout_index=breakout_index,
        channel=None,
        channel_end_to_breakout_gap=None,
        channel_close_return=None,
        breakout_body_return=breakout_body_return,
        breakout_ratio=breakout_ratio,
        left_close_high=left_close_high,
        left_close_high_index=left_close_high_index,
        trough_close=trough_close,
        trough_index=trough_index,
        bowl_width=bowl_width,
        bowl_depth_ratio=float(bowl_depth_ratio),
        right_close_ratio=float(closes[target_index] / left_close_high),
        ma_bull_start_index=ma_bull_start_index,
        ma_bull_end_index=ma_bull_end_index,
        ma_bull_days=ma_bull_days,
        bottom_low=bottom_low,
        bottom_low_index=bottom_low_index,
        bounce_days=bounce_days,
        bounce_body_return_1=body_returns[-2] if len(body_returns) >= 2 else None,
        bounce_body_return_2=body_returns[-1] if len(body_returns) >= 1 else None,
    )


def _resolve_bottom_bounce_sequence(
    *,
    opens: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    target_index: int,
    breakout_index: int,
    breakout_body_return: float,
    breakout_ratio: float,
    config: GoldenBowlConfig,
    ma_bull_start_index: int | None,
    ma_bull_end_index: int | None,
    ma_bull_days: int | None,
) -> list[GoldenBowlPattern]:
    sequence: list[GoldenBowlPattern] = []
    bounce_days = max(2, int(config.min_bottom_bounce_bullish_days))
    first_target = breakout_index + max(config.min_bowl_width, bounce_days)
    for index in range(first_target, target_index + 1):
        if not _is_bottom_bounce_confirmation(
            opens=opens,
            lows=lows,
            closes=closes,
            target_index=index,
            bounce_days=bounce_days,
            max_body_return_ratio=config.max_bottom_bounce_body_return_ratio,
            require_bullish=config.require_bottom_bounce_bullish,
            require_low_non_decreasing=config.require_bottom_bounce_low_non_decreasing,
        ):
            continue
        pattern = _resolve_bottom_bounce_shape(
            opens=opens,
            lows=lows,
            closes=closes,
            target_index=index,
            breakout_index=breakout_index,
            breakout_body_return=breakout_body_return,
            breakout_ratio=breakout_ratio,
            config=config,
            ma_bull_start_index=ma_bull_start_index,
            ma_bull_end_index=ma_bull_end_index,
            ma_bull_days=ma_bull_days,
        )
        if pattern is None:
            continue
        if not sequence:
            sequence.append(pattern)
            continue

        previous = sequence[-1]
        if (
            pattern.left_close_high_index == previous.left_close_high_index
            and pattern.trough_index == previous.trough_index
        ):
            continue
        if len(sequence) >= max(config.max_bowl_order, 1):
            continue
        if not _is_valid_next_bowl(pattern=pattern, previous=previous, config=config):
            continue
        sequence.append(
            _with_sequence_context(
                pattern=pattern,
                bowl_order=previous.bowl_order + 1,
                previous=previous,
            )
        )
    return sequence


def _is_bottom_bounce_confirmation(
    *,
    opens: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    target_index: int,
    bounce_days: int,
    max_body_return_ratio: float | None,
    require_bullish: bool,
    require_low_non_decreasing: bool,
) -> bool:
    start = target_index - bounce_days + 1
    if start < 0:
        return False
    previous_close: float | None = None
    previous_low: float | None = None
    for index in range(start, target_index + 1):
        open_price = float(opens[index])
        close = float(closes[index])
        low = float(lows[index])
        if not (
            np.isfinite(open_price)
            and np.isfinite(close)
            and np.isfinite(low)
            and open_price > 0
        ):
            return False
        body_return = _body_return(open_price, close)
        if require_bullish and body_return <= 0:
            return False
        if max_body_return_ratio is not None and body_return > max_body_return_ratio:
            return False
        if previous_close is not None and close <= previous_close:
            return False
        if require_low_non_decreasing and previous_low is not None and low < previous_low:
            return False
        previous_close = close
        previous_low = low
    return True


def _body_return(open_price: float, close: float) -> float:
    open_value = float(open_price)
    close_value = float(close)
    if not (np.isfinite(open_value) and open_value > 0 and np.isfinite(close_value)):
        return float("nan")
    return close_value / open_value - 1.0


def _resolve_ma_bull_breakout(
    *,
    opens: np.ndarray,
    closes: np.ndarray,
    ma_5: np.ndarray,
    ma_10: np.ndarray,
    ma_20: np.ndarray,
    breakout_index: int,
    config: GoldenBowlConfig,
    min_ma_bull_days: int,
) -> tuple[int, int, int, float, float] | None:
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

    ma_bull_end = breakout_index - 1
    ma_bull_days = _ma_bull_streak_days(
        ma_5=ma_5,
        ma_10=ma_10,
        ma_20=ma_20,
        end_index=ma_bull_end,
    )
    if ma_bull_days < min_ma_bull_days:
        return None
    ma_bull_start = ma_bull_end - ma_bull_days + 1
    ma20_b = float(ma_20[ma_bull_end])
    breakout_ratio = close_b / ma20_b if np.isfinite(ma20_b) and ma20_b > 0 else float("nan")
    if (
        config.min_breakout_to_channel_upper_ratio is not None
        and (
            not np.isfinite(breakout_ratio)
            or breakout_ratio < config.min_breakout_to_channel_upper_ratio
        )
    ):
        return None
    return (
        int(ma_bull_start),
        int(ma_bull_end),
        int(ma_bull_days),
        float(breakout_body_return),
        float(breakout_ratio),
    )


def _ma_bull_streak_days(
    *,
    ma_5: np.ndarray,
    ma_10: np.ndarray,
    ma_20: np.ndarray,
    end_index: int,
) -> int:
    if end_index < 0:
        return 0
    days = 0
    for index in range(end_index, -1, -1):
        ma5 = float(ma_5[index])
        ma10 = float(ma_10[index])
        ma20 = float(ma_20[index])
        if not (
            np.isfinite(ma5)
            and np.isfinite(ma10)
            and np.isfinite(ma20)
            and ma5 > ma10 > ma20
        ):
            break
        days += 1
    return days


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
