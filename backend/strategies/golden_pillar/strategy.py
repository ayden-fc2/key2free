"""Golden/general pillar intraday-trigger strategy.

Spec: a-obsidian-docs/strategies/黄金柱战法.md.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, TypeVar

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


T = TypeVar("T")

MAX_WATCH_DAYS = 3
GOLDEN_PILLAR_POSITION_FRACTION = 1.0 / 4.0
GOLDEN_PILLAR_MAX_HOLDING_DAYS = 1

LOOKBACK_BARS = 400
RECENT_CONSOLIDATION_BARS = 5
CONSOLIDATION_BARS = 15
MIN_CONSOLIDATION_CLOSE_RANGE_RATIO = 0.04
MAX_CONSOLIDATION_CLOSE_RANGE_RATIO = 0.07
MAX_CONSOLIDATION_AVG_BODY_RATIO = 0.025

T1_VOLUME_TO_AVG5_MULTIPLE = 1.4
T1_BODY_OPEN_RATIO = 0.032
T1_BODY_ATR5_MULTIPLE = 1.5
MAX_T1_BODY_OPEN_RATIO = 0.080
CONFIRM_BODY_TO_T1_BODY_RATIO = 0.5
CONFIRM_BODY_HIGH_TO_T1_CLOSE_CEILING_RATIO = 1.06
MAX_T4_BODY_OPEN_RATIO = 0.08
GOLDEN_PILLAR_MIN_CONFIRM_POSITION = 1.0
RECENT_CLOSE_BREAKOUT_DAYS = 3
RECENT_CLOSE_BREAKOUT_MIN_COUNT = 2
RECENT_CLOSE_BREAKOUT_RATIO = 1.02
T1_CLOSE_TO_CONSOLIDATION_BODY_HIGH_CEILING_RATIO = 1.05
SIGNAL_CLOSE_TO_T1_CLOSE_FLOOR_RATIO = 0.98
SIGNAL_CLOSE_TO_T1_CLOSE_CEILING_RATIO = 1.04
MAX_SIGNAL_BODY_RETURN_RATIO = 0.015
MAX_CONFIRM_AFTER_T4_DAYS = 0
ENTRY_OPEN_TO_T1_CLOSE_FLOOR_RATIO = 0.98
ENTRY_OPEN_TO_T1_CLOSE_CEILING_RATIO = 1.04
ENTRY_TRIGGER_TO_T1_CLOSE_RATIO = 1.005
ENTRY_TRIGGER_TO_OPEN_RATIO = 1.01
ENTRY_BUY_PRICE_TO_CONSOLIDATION_HIGH_CEILING_RATIO = 1.08
ENTRY_BUY_PRICE_TO_MA10_CEILING_RATIO = 1.06
ENTRY_BUY_PRICE_TO_T1_CLOSE_CEILING_RATIO = 1.05

PILLAR_TYPE_GOLDEN = "golden_pillar"

GOLDEN_PILLAR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_5",
    "avg_volume_5",
    "ma_10",
)


@dataclass(frozen=True)
class ConsolidationRange:
    start_index: int
    end_index: int
    high: float
    low: float
    body_high: float
    body_low: float
    close_high: float
    close_low: float
    avg_daily_body_ratio: float
    close_range_ratio: float


@dataclass(frozen=True)
class PillarPattern:
    pattern_type: str
    t1_index: int
    t4_index: int
    t1_open: float
    t1_close: float
    t4_close: float
    confirm_position_min: float
    confirm_position_max: float
    confirm_position_avg: float


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
    ma10 = columns["ma_10"]

    with np.errstate(invalid="ignore", divide="ignore"):
        st_blocked = _st_blocked_series(columns)

    all_consolidations = _scan_consolidation_ranges(frame, 0, len(frame) - 1)
    consolidation_end_indices = [item.end_index for item in all_consolidations]

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if index < LOOKBACK_BARS - 1 or st_blocked[index]:
            continue

        close_t = float(closes[index])
        open_t = float(opens[index])
        if not (np.isfinite(open_t) and np.isfinite(close_t) and open_t > 0):
            continue
        signal_body_return = (close_t - open_t) / open_t
        if signal_body_return > MAX_SIGNAL_BODY_RETURN_RATIO:
            continue

        matched_pillar = _resolve_confirmed_pillar(
            frame=frame,
            index=index,
        )
        if matched_pillar is None:
            continue

        window_start = index + 1 - LOOKBACK_BARS
        latest_consolidation_end = matched_pillar.t1_index - 1
        recent_consolidation_start = max(
            window_start,
            latest_consolidation_end - RECENT_CONSOLIDATION_BARS,
        )

        recent_consolidations = _slice_by_index_range(
            all_consolidations,
            consolidation_end_indices,
            recent_consolidation_start,
            latest_consolidation_end,
        )
        if not recent_consolidations:
            continue
        consolidation = recent_consolidations[-1]

        if not (
            np.isfinite(consolidation.body_high)
            and consolidation.body_high > 0
            and matched_pillar.t1_close >= RECENT_CLOSE_BREAKOUT_RATIO * consolidation.body_high
            and matched_pillar.t1_close
            <= T1_CLOSE_TO_CONSOLIDATION_BODY_HIGH_CEILING_RATIO * consolidation.body_high
            and _close_breakout_count(
                closes=closes,
                start_index=matched_pillar.t1_index + 1,
                end_index=matched_pillar.t4_index,
                threshold=RECENT_CLOSE_BREAKOUT_RATIO * consolidation.body_high,
            )
            >= RECENT_CLOSE_BREAKOUT_MIN_COUNT
        ):
            continue

        entry_open_floor = matched_pillar.t1_close * ENTRY_OPEN_TO_T1_CLOSE_FLOOR_RATIO
        entry_open_ceiling = matched_pillar.t1_close * ENTRY_OPEN_TO_T1_CLOSE_CEILING_RATIO
        entry_trigger_price = matched_pillar.t1_close * ENTRY_TRIGGER_TO_T1_CLOSE_RATIO
        ma10_t = float(ma10[index])
        if not (np.isfinite(ma10_t) and ma10_t > 0):
            continue
        entry_buy_price_ceiling = min(
            entry_open_ceiling,
            consolidation.high * ENTRY_BUY_PRICE_TO_CONSOLIDATION_HIGH_CEILING_RATIO,
            ma10_t * ENTRY_BUY_PRICE_TO_MA10_CEILING_RATIO,
            matched_pillar.t1_close * ENTRY_BUY_PRICE_TO_T1_CLOSE_CEILING_RATIO,
        )
        if entry_trigger_price > entry_buy_price_ceiling:
            continue
        results[index] = SignalDecision(
            triggered=True,
            signal_close=close_t,
            stop_losses=(),
            take_profits=(),
            max_watch_days=MAX_WATCH_DAYS,
            extras={
                "pattern": "golden_pillar_intraday_trigger",
                "consolidation_start": frame.trade_dates[consolidation.start_index].isoformat(),
                "consolidation_end": frame.trade_dates[consolidation.end_index].isoformat(),
                "consolidation_high": consolidation.high,
                "consolidation_low": consolidation.low,
                "consolidation_body_high": consolidation.body_high,
                "consolidation_body_low": consolidation.body_low,
                "consolidation_close_high": consolidation.close_high,
                "consolidation_close_low": consolidation.close_low,
                "consolidation_avg_daily_body_ratio": consolidation.avg_daily_body_ratio,
                "consolidation_close_range_ratio": consolidation.close_range_ratio,
                "pillar_type": matched_pillar.pattern_type,
                "pillar_t1_date": frame.trade_dates[matched_pillar.t1_index].isoformat(),
                "pillar_t4_date": frame.trade_dates[matched_pillar.t4_index].isoformat(),
                "pillar_t1_open": matched_pillar.t1_open,
                "pillar_t1_close": matched_pillar.t1_close,
                "pillar_t4_close": matched_pillar.t4_close,
                "pillar_confirm_position_min": matched_pillar.confirm_position_min,
                "pillar_confirm_position_max": matched_pillar.confirm_position_max,
                "pillar_confirm_position_avg": matched_pillar.confirm_position_avg,
                "pillar_t1_close_to_consolidation_body_high": (
                    matched_pillar.t1_close / consolidation.body_high
                ),
                "signal_close_to_consolidation_body_high": close_t / consolidation.body_high,
                "ma10": ma10_t,
                "recent_close_breakout_ratio": RECENT_CLOSE_BREAKOUT_RATIO,
                "t1_close_to_consolidation_body_high_ceiling_ratio": (
                    T1_CLOSE_TO_CONSOLIDATION_BODY_HIGH_CEILING_RATIO
                ),
                "recent_close_breakout_days": RECENT_CLOSE_BREAKOUT_DAYS,
                "recent_close_breakout_min_count": RECENT_CLOSE_BREAKOUT_MIN_COUNT,
                "signal_close_to_t1_close_floor_ratio": SIGNAL_CLOSE_TO_T1_CLOSE_FLOOR_RATIO,
                "signal_close_to_t1_close_ceiling_ratio": SIGNAL_CLOSE_TO_T1_CLOSE_CEILING_RATIO,
                "signal_body_return": float(signal_body_return),
                "max_signal_body_return_ratio": MAX_SIGNAL_BODY_RETURN_RATIO,
                "post_pillar_support_price": matched_pillar.t1_open,
                "max_confirm_after_t4_days": MAX_CONFIRM_AFTER_T4_DAYS,
                "confirm_lag_days": index - matched_pillar.t4_index,
                "entry_open_floor": float(entry_open_floor),
                "entry_open_ceiling": float(entry_open_ceiling),
                "entry_trigger_price": float(entry_trigger_price),
                "entry_buy_price_ceiling": float(entry_buy_price_ceiling),
                "entry_open_to_t1_close_floor_ratio": ENTRY_OPEN_TO_T1_CLOSE_FLOOR_RATIO,
                "entry_open_to_t1_close_ceiling_ratio": ENTRY_OPEN_TO_T1_CLOSE_CEILING_RATIO,
                "entry_trigger_to_t1_close_ratio": ENTRY_TRIGGER_TO_T1_CLOSE_RATIO,
                "entry_trigger_to_open_ratio": ENTRY_TRIGGER_TO_OPEN_RATIO,
                "entry_buy_price_to_consolidation_high_ceiling_ratio": (
                    ENTRY_BUY_PRICE_TO_CONSOLIDATION_HIGH_CEILING_RATIO
                ),
                "entry_buy_price_to_ma10_ceiling_ratio": ENTRY_BUY_PRICE_TO_MA10_CEILING_RATIO,
                "entry_buy_price_to_t1_close_ceiling_ratio": (
                    ENTRY_BUY_PRICE_TO_T1_CLOSE_CEILING_RATIO
                ),
                "exit_rule": "next_trade_day_open",
            },
        )
    return results


def golden_pillar_entry_strategy(*, bar: tuple[float, float, float, float, float, float], watch: Any) -> float | None:
    signal = watch.signal or {}
    entry_open_floor = _signal_value(signal, "entry_open_floor")
    entry_open_ceiling = _signal_value(signal, "entry_open_ceiling")
    entry_trigger_price = _signal_value(signal, "entry_trigger_price")
    entry_buy_price_ceiling = _signal_value(signal, "entry_buy_price_ceiling")
    if not all(
        isinstance(value, (int, float))
        for value in (entry_open_floor, entry_open_ceiling, entry_trigger_price)
    ):
        return None
    entry_open_floor = float(entry_open_floor)
    entry_open_ceiling = float(entry_open_ceiling)
    entry_trigger_price = float(entry_trigger_price)
    entry_buy_price_ceiling = (
        float(entry_buy_price_ceiling)
        if isinstance(entry_buy_price_ceiling, (int, float))
        else entry_open_ceiling
    )
    if not (
        np.isfinite(entry_open_floor)
        and np.isfinite(entry_open_ceiling)
        and np.isfinite(entry_trigger_price)
        and np.isfinite(entry_buy_price_ceiling)
        and entry_open_floor > 0
        and entry_open_ceiling >= entry_open_floor
        and entry_trigger_price > 0
        and entry_buy_price_ceiling > 0
    ):
        return None

    open_price = float(bar[0])
    high_price = float(bar[1])
    if not (np.isfinite(open_price) and np.isfinite(high_price)):
        return None
    entry_trigger_price = max(entry_trigger_price, open_price * ENTRY_TRIGGER_TO_OPEN_RATIO)
    if entry_trigger_price > entry_buy_price_ceiling:
        return None
    if open_price < entry_open_floor or open_price > entry_open_ceiling or high_price < entry_trigger_price:
        return None
    return entry_trigger_price


def _resolve_confirmed_pillar(
    *,
    frame: StockDailyFrame,
    index: int,
) -> PillarPattern | None:
    closes = frame.columns["qfq_close"]
    lows = frame.columns["qfq_low"]
    close_t = float(closes[index])
    if not np.isfinite(close_t):
        return None

    for lag in range(0, MAX_CONFIRM_AFTER_T4_DAYS + 1):
        t4_index = index - lag
        t1_index = t4_index - 3
        if t1_index < 1:
            continue
        pattern = _detect_pillar_pattern(frame, t1_index)
        if pattern is None or pattern.t4_index != t4_index:
            continue
        signal_floor = pattern.t1_close * SIGNAL_CLOSE_TO_T1_CLOSE_FLOOR_RATIO
        signal_ceiling = pattern.t1_close * SIGNAL_CLOSE_TO_T1_CLOSE_CEILING_RATIO
        if close_t < signal_floor or close_t > signal_ceiling:
            continue
        if _has_prior_t1_close_confirmation(
            closes=closes,
            start_index=pattern.t4_index,
            end_index=index - 1,
            threshold=signal_floor,
        ):
            continue
        if _breaks_t1_open_after_pillar(
            lows=lows,
            start_index=pattern.t4_index + 1,
            end_index=index,
            t1_open=pattern.t1_open,
        ):
            continue
        return pattern
    return None


def _has_prior_t1_close_confirmation(
    *,
    closes: np.ndarray,
    start_index: int,
    end_index: int,
    threshold: float,
) -> bool:
    if end_index < start_index:
        return False
    for position in range(start_index, end_index + 1):
        close_value = float(closes[position])
        if np.isfinite(close_value) and close_value >= threshold:
            return True
    return False


def _breaks_t1_open_after_pillar(
    *,
    lows: np.ndarray,
    start_index: int,
    end_index: int,
    t1_open: float,
) -> bool:
    if end_index < start_index:
        return False
    if not np.isfinite(t1_open):
        return True
    for position in range(start_index, end_index + 1):
        low_value = float(lows[position])
        if not np.isfinite(low_value) or low_value < t1_open:
            return True
    return False


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

    max_confirm_body = CONFIRM_BODY_TO_T1_BODY_RATIO * t1_body
    confirm_positions: list[tuple[float, float, float]] = []
    for position in range(t1_index + 1, t4_index + 1):
        open_value = float(opens[position])
        close_value = float(closes[position])
        if not (np.isfinite(open_value) and np.isfinite(close_value)):
            return None
        body = abs(close_value - open_value)
        if position < t4_index:
            if body > max_confirm_body:
                return None
        elif body > max_confirm_body:
            if close_value <= open_value or body > MAX_T4_BODY_OPEN_RATIO * open_value:
                return None
        body_low = min(open_value, close_value)
        body_high = max(open_value, close_value)
        if body_high > CONFIRM_BODY_HIGH_TO_T1_CLOSE_CEILING_RATIO * t1_close:
            return None
        position_low = (body_low - t1_open) / t1_body
        position_high = (body_high - t1_open) / t1_body
        position_mid = (((open_value + close_value) / 2.0) - t1_open) / t1_body
        if not (
            np.isfinite(position_low)
            and np.isfinite(position_high)
            and np.isfinite(position_mid)
        ):
            return None
        confirm_positions.append((position_low, position_high, position_mid))

    confirm_position_min = min(item[0] for item in confirm_positions)
    confirm_position_max = max(item[1] for item in confirm_positions)
    confirm_position_avg = float(np.mean([item[2] for item in confirm_positions]))
    if confirm_position_min < GOLDEN_PILLAR_MIN_CONFIRM_POSITION:
        return None

    return PillarPattern(
        pattern_type=PILLAR_TYPE_GOLDEN,
        t1_index=t1_index,
        t4_index=t4_index,
        t1_open=t1_open,
        t1_close=t1_close,
        t4_close=t4_close,
        confirm_position_min=float(confirm_position_min),
        confirm_position_max=float(confirm_position_max),
        confirm_position_avg=float(confirm_position_avg),
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

    columns = frame.columns
    highs = columns["qfq_high"][start_index : end_index + 1]
    lows = columns["qfq_low"][start_index : end_index + 1]
    closes = columns["qfq_close"][start_index : end_index + 1]
    opens = columns["qfq_open"][start_index : end_index + 1]
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
    body_high = float(np.max(body_highs))
    body_low = float(np.min(body_lows))
    close_high = float(np.max(closes))
    close_low = float(np.min(closes))
    if low <= 0 or body_low <= 0 or close_low <= 0:
        return None
    close_range_ratio = (close_high - close_low) / close_low
    if not (
        MIN_CONSOLIDATION_CLOSE_RANGE_RATIO <= close_range_ratio <= MAX_CONSOLIDATION_CLOSE_RANGE_RATIO
        and avg_daily_body_ratio <= MAX_CONSOLIDATION_AVG_BODY_RATIO
    ):
        return None

    return ConsolidationRange(
        start_index=start_index,
        end_index=end_index,
        high=high,
        low=low,
        body_high=body_high,
        body_low=body_low,
        close_high=close_high,
        close_low=close_low,
        avg_daily_body_ratio=avg_daily_body_ratio,
        close_range_ratio=close_range_ratio,
    )


def _close_breakout_count(
    *,
    closes: np.ndarray,
    start_index: int,
    end_index: int,
    threshold: float,
) -> int:
    count = 0
    for position in range(start_index, end_index + 1):
        close_value = float(closes[position])
        if np.isfinite(close_value) and close_value >= threshold:
            count += 1
    return count


def _slice_by_index_range(
    values: list[T],
    indices: list[int],
    start_index: int,
    end_index: int,
) -> list[T]:
    left = bisect_left(indices, start_index)
    right = bisect_right(indices, end_index)
    return values[left:right]


def _signal_value(signal: dict[str, Any], key: str) -> Any:
    if key in signal:
        return signal[key]
    extras = signal.get("extras")
    if isinstance(extras, dict):
        return extras.get(key)
    return None


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
