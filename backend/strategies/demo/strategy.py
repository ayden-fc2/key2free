from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


# ---------------------------------------------------------------------------
# 常量（口径见 a-obsidian-docs/strategies/demo.md）
# ---------------------------------------------------------------------------

# T+1 直接按开盘价买入；如果 T+1 不可交易，不顺延。
MAX_WATCH_DAYS = 1
DEMO_MAX_HOLDING_DAYS = 20

N_BOTTOM_LOOKBACK = 90
SWING_LEFT_BARS = 3
SWING_RIGHT_BARS = 3
MIN_L1_TO_T_BARS = 10
MIN_L1_TO_H1_BARS = 3
MIN_H1_TO_L2_BARS = 3
L2_TO_T_BARS = 2

MIN_RISE_ATR_MULTIPLE = 3.0
L2_L1_ATR_MULTIPLE = 1.0
KLINE_SEARCH_BEFORE_L2 = 3
KLINE_LOW_ABOVE_L2_ATR_MULTIPLE = 0.2
MAX_T_CLOSE_REBOUND_RATIO = 0.3
STOP_LOSS_ATR_MULTIPLE = 0.8
TAKE_PROFIT_ATR_MULTIPLE = 0.5
MIN_REWARD_RISK_RATIO = 1.3

VOLUME_AVG_MIN_RATIO = 0.8
LONG_BODY_MIN_RATIO = 0.8
LONG_BODY_ATR_MULTIPLE = 0.618
SMALL_CANDLE_ATR_MULTIPLE = 0.6
BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO = 0.618

# 策略需要的宽表列（框架基础列 qfq_open/high/low/close、vol、is_st、name 之外）。
DEMO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "atr_14",
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


@dataclass(frozen=True)
class KlineSignals:
    passed: np.ndarray
    pattern_lows: np.ndarray


@dataclass(frozen=True)
class NBottomSeries:
    swing_lows: np.ndarray
    swing_highs: np.ndarray
    close_nan_cumsum: np.ndarray


# ---------------------------------------------------------------------------
# 成分预过滤（代码级，静态）
# ---------------------------------------------------------------------------

def demo_code_filter(code: str) -> bool:
    """只保留主板普通 A 股代码形态；ST 等与交易日相关的条件在信号函数内判断。"""
    value = code.lower()
    if value.startswith("sh.688") or value.startswith("sz.300") or value.startswith("sz.301"):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


# ---------------------------------------------------------------------------
# 信号策略（逐股批量评估）
# ---------------------------------------------------------------------------

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
        stop_loss = context.pl2 - STOP_LOSS_ATR_MULTIPLE * context.atr14_t
        take_profit = context.ph1 - TAKE_PROFIT_ATR_MULTIPLE * context.atr14_t
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
                "reward_risk_ratio": reward / risk,
            },
        )
    return results


# ---------------------------------------------------------------------------
# 成分筛选（交易日相关部分）
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 趋势结构过滤：N 字结构 L1(tl1, pl1) -> H1(th1, ph1) -> L2(tl2, pl2)
# p 使用收盘价，t 使用交易日。
# ---------------------------------------------------------------------------

def _resolve_n_bottom_context(
    *,
    index: int,
    frame: StockDailyFrame,
    closes: np.ndarray,
    atr14: np.ndarray,
    kline_signals: KlineSignals,
    n_bottom_series: NBottomSeries,
) -> NBottomContext | None:
    l2_index = index - L2_TO_T_BARS
    if l2_index <= 0:
        return None
    atr14_t = float(atr14[index])
    if not np.isfinite(atr14_t) or atr14_t <= 0:
        return None
    window_start = max(0, index + 1 - N_BOTTOM_LOOKBACK)
    if _has_nan_in_range(n_bottom_series.close_nan_cumsum, window_start, index):
        return None

    pl2 = float(closes[l2_index])
    close_t = float(closes[index])
    if not (np.isfinite(pl2) and np.isfinite(close_t)):
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

    swing_lows = _precomputed_pivots_in_range(
        pivots=n_bottom_series.swing_lows,
        start=window_start,
        end=l2_index,
        left=SWING_LEFT_BARS,
        right=SWING_RIGHT_BARS,
        series_length=len(closes),
    )
    swing_highs = _precomputed_pivots_in_range(
        pivots=n_bottom_series.swing_highs,
        start=window_start,
        end=l2_index,
        left=SWING_LEFT_BARS,
        right=SWING_RIGHT_BARS,
        series_length=len(closes),
    )

    best: tuple[float, int, float, int, float] | None = None
    for h1_index in swing_highs:
        h1_index = int(h1_index)
        if h1_index > l2_index - MIN_H1_TO_L2_BARS:
            continue
        l1_candidates = swing_lows[
            (swing_lows <= h1_index - MIN_L1_TO_H1_BARS)
            & (index - swing_lows >= MIN_L1_TO_T_BARS)
        ]
        if len(l1_candidates) == 0:
            continue
        # 同一 H1 下，使用 H1 前最低的 swing low 作为 L1。
        l1_index = int(l1_candidates[np.argmin(closes[l1_candidates])])
        pl1 = float(closes[l1_index])
        ph1 = float(closes[h1_index])
        if not (np.isfinite(pl1) and np.isfinite(ph1)):
            continue
        if not (l1_index < h1_index < l2_index < index):
            continue
        if ph1 - pl1 < MIN_RISE_ATR_MULTIPLE * atr14_t:
            continue
        if not (
            -L2_L1_ATR_MULTIPLE * atr14_t
            <= pl2 - pl1
            <= L2_L1_ATR_MULTIPLE * atr14_t
        ):
            continue
        if not (pl2 <= close_t <= pl2 + MAX_T_CLOSE_REBOUND_RATIO * (ph1 - pl2)):
            continue
        # L2 必须是 H1 到 T 之间的最低收盘价，确保 N 字第二脚有效。
        after_h1_closes = closes[h1_index : index + 1]
        if len(after_h1_closes) == 0:
            continue
        if abs(float(np.min(after_h1_closes)) - pl2) > max(1e-8, abs(pl2) * 1e-8):
            continue
        score = (ph1 - pl1) / atr14_t
        if best is None or score > best[0]:
            best = (score, l1_index, pl1, h1_index, ph1)

    if best is None:
        return None
    _score, l1_index, pl1, h1_index, ph1 = best
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
    )


def _prepare_n_bottom_series(closes: np.ndarray) -> NBottomSeries:
    close_nan_cumsum = np.concatenate((
        np.array([0], dtype=np.int64),
        np.cumsum(np.isnan(closes).astype(np.int64)),
    ))
    swing_lows = np.asarray(
        _find_pivot_indices(
            values=closes,
            start=0,
            end=len(closes) - 1,
            left=SWING_LEFT_BARS,
            right=SWING_RIGHT_BARS,
            mode="low",
        ),
        dtype=np.int64,
    )
    swing_highs = np.asarray(
        _find_pivot_indices(
            values=closes,
            start=0,
            end=len(closes) - 1,
            left=SWING_LEFT_BARS,
            right=SWING_RIGHT_BARS,
            mode="high",
        ),
        dtype=np.int64,
    )
    return NBottomSeries(
        swing_lows=swing_lows,
        swing_highs=swing_highs,
        close_nan_cumsum=close_nan_cumsum,
    )


def _has_nan_in_range(cumsum: np.ndarray, start: int, end: int) -> bool:
    return int(cumsum[end + 1] - cumsum[start]) > 0


def _precomputed_pivots_in_range(
    *,
    pivots: np.ndarray,
    start: int,
    end: int,
    left: int,
    right: int,
    series_length: int,
) -> np.ndarray:
    first = max(start + left, left)
    last = min(end - right, series_length - 1 - right)
    if last < first or len(pivots) == 0:
        return np.asarray([], dtype=np.int64)
    left_position = int(np.searchsorted(pivots, first, side="left"))
    right_position = int(np.searchsorted(pivots, last, side="right"))
    return pivots[left_position:right_position]


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
        if low_value <= pl2 + KLINE_LOW_ABOVE_L2_ATR_MULTIPLE * atr14_t:
            candidates.append((low_value, position))
    if not candidates:
        raise ValueError("no valid kline pattern")
    low_value, position = min(candidates, key=lambda item: (item[0], -item[1]))
    return position, low_value


def _find_pivot_indices(
    *,
    values: np.ndarray,
    start: int,
    end: int,
    left: int,
    right: int,
    mode: str,
) -> list[int]:
    """确认型 swing pivot：只使用 end 及以前数据，避免未来泄漏。"""
    result: list[int] = []
    first = max(start + left, left)
    last = min(end - right, len(values) - 1 - right)
    if last < first:
        return result
    for position in range(first, last + 1):
        window = values[position - left : position + right + 1]
        if len(window) != left + right + 1 or np.isnan(window).any():
            continue
        center = float(values[position])
        if mode == "low":
            if center <= float(np.min(window)):
                result.append(position)
        elif mode == "high":
            if center >= float(np.max(window)):
                result.append(position)
        else:
            raise ValueError(f"unknown pivot mode: {mode}")
    return result


# ---------------------------------------------------------------------------
# K 线形态过滤
# ---------------------------------------------------------------------------

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
    """长影线 / 短影线 >= multiple；短影线为 0 时只要求长影线 > 0。"""
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
