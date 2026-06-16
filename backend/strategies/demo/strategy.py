from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame
from strategies.algorithms import (
    GoldenBowlConfig,
    find_latest_trend_channel_consolidation,
    resolve_n_bottom_by_ma_slope,
    resolve_golden_bowl,
)


DEMO_SIGNAL_DATE = date(2026, 6, 15)
MAX_WATCH_DAYS = 1
DEMO_MAX_HOLDING_DAYS = 1

DEMO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_pct_14",
    "ma_slope_10",
    "volume_ratio_20",
)


def demo_code_filter(code: str) -> bool:
    return bool(code)


def demo_batch_signal_strategy(
    frame: StockDailyFrame,
    target_indices: list[int],
) -> dict[int, SignalDecision]:
    if not target_indices or len(frame) == 0:
        return {}

    columns = frame.columns
    closes = columns["qfq_close"]

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if frame.trade_dates[index] != DEMO_SIGNAL_DATE:
            continue
        signal_close = float(closes[index])
        if not np.isfinite(signal_close) or signal_close <= 0:
            continue

        results[index] = SignalDecision(
            triggered=True,
            signal_close=signal_close,
            stop_losses=(),
            take_profits=(),
            max_watch_days=MAX_WATCH_DAYS,
            extras={
                "pattern": "demo_fixed_signal",
                "signal_date": DEMO_SIGNAL_DATE.isoformat(),
                "entry_rule": "next_trade_day_open",
                "exit_rule": "one_trade_day_close",
                "algorithm_modules": {
                    "trend_channel": _trend_channel_preview(frame=frame, index=index),
                    "n_bottom": _n_bottom_preview(frame=frame, index=index),
                    "golden_bowl": _golden_bowl_preview(frame=frame, index=index),
                },
            },
        )
    return results


def _trend_channel_preview(*, frame: StockDailyFrame, index: int) -> dict[str, Any] | None:
    item = find_latest_trend_channel_consolidation(
        opens=frame.columns["qfq_open"],
        highs=frame.columns["qfq_high"],
        lows=frame.columns["qfq_low"],
        closes=frame.columns["qfq_close"],
        end_index=index,
        length=30,
        lookback=90,
        trim_extreme_count=2,
        max_channel_width_ratio=0.10,
        min_in_channel_ratio=0.85,
        max_exception_count=4,
        atr_pct_14=frame.columns.get("atr_pct_14"),
        volume_ratio_20=frame.columns.get("volume_ratio_20"),
    )
    if item is None:
        return None
    return {
        "start": frame.trade_dates[item.start_index].isoformat(),
        "end": frame.trade_dates[item.end_index].isoformat(),
        "length": item.length,
        "slope": item.slope,
        "channel_width_ratio": item.channel_width_ratio,
        "in_channel_ratio": item.in_channel_ratio,
        "exception_count": item.exception_count,
        "upper_line_end": item.upper_line_end,
        "lower_line_end": item.lower_line_end,
        "avg_atr_pct_14": item.avg_atr_pct_14,
        "avg_volume_ratio_20": item.avg_volume_ratio_20,
    }


def _n_bottom_preview(*, frame: StockDailyFrame, index: int) -> dict[str, Any] | None:
    start_index = max(0, index + 1 - 90)
    item = resolve_n_bottom_by_ma_slope(
        slope=frame.columns["ma_slope_10"],
        highs=frame.columns["qfq_high"],
        lows=frame.columns["qfq_low"],
        start_index=start_index,
        end_index=index,
        threshold=0.005,
    )
    if item is None:
        return None
    l1, h1, l2 = item
    return {
        "l1_date": frame.trade_dates[l1.index].isoformat(),
        "l1_price": l1.price,
        "h1_date": frame.trade_dates[h1.index].isoformat(),
        "h1_price": h1.price,
        "l2_date": frame.trade_dates[l2.index].isoformat(),
        "l2_price": l2.price,
    }


def _golden_bowl_preview(*, frame: StockDailyFrame, index: int) -> dict[str, Any] | None:
    item = resolve_golden_bowl(
        opens=frame.columns["qfq_open"],
        highs=frame.columns["qfq_high"],
        lows=frame.columns["qfq_low"],
        closes=frame.columns["qfq_close"],
        target_index=index,
        config=GoldenBowlConfig(
            channel_length=20,
            channel_trim_extreme_count=2,
            max_channel_width_ratio=0.06,
            max_channel_close_return_ratio=0.08,
            min_breakout_body_return_ratio=0.06,
            min_breakout_to_channel_upper_ratio=1.03,
            max_channel_end_to_breakout_gap=10,
            max_left_high_to_channel_end_close_ratio=1.12,
            max_bowl_width=12,
            min_bowl_width=3,
            min_bowl_depth_ratio=0.03,
            max_bowl_depth_ratio=0.20,
            right_close_to_left_high_ratio=0.98,
            require_right_bullish=True,
        ),
        atr_pct_14=frame.columns.get("atr_pct_14"),
        volume_ratio_20=frame.columns.get("volume_ratio_20"),
    )
    if item is None:
        return None
    return {
        "breakout_date": frame.trade_dates[item.breakout_index].isoformat(),
        "channel_start": frame.trade_dates[item.channel.start_index].isoformat(),
        "channel_end": frame.trade_dates[item.channel.end_index].isoformat(),
        "channel_end_to_breakout_gap": item.channel_end_to_breakout_gap,
        "left_high_date": frame.trade_dates[item.left_close_high_index].isoformat(),
        "left_close_high": item.left_close_high,
        "trough_date": frame.trade_dates[item.trough_index].isoformat(),
        "trough_close": item.trough_close,
        "bowl_width": item.bowl_width,
        "bowl_depth_ratio": item.bowl_depth_ratio,
        "right_close_ratio": item.right_close_ratio,
        "channel_width_ratio": item.channel.channel_width_ratio,
        "breakout_ratio": item.breakout_ratio,
    }
