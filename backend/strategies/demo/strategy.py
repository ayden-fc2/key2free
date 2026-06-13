from __future__ import annotations

from typing import Any

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


# ---------------------------------------------------------------------------
# 常量（口径见 a-obsidian-docs/strategies/demo.md）
# ---------------------------------------------------------------------------

MAX_WATCH_DAYS = 2

MA20_SLOPE_WINDOW = 10
MAX_MA20_SLOPE_IMPROVING_DAYS = 5
MIN_MA20_SLOPE_IMPROVING_STEPS = 3

MA30_SLOPE_WINDOW = 10
MIN_MA30_TURN_POINTS = 5
MAX_MA30_TURN_POINTS = 10
RECENT_TURN_POINTS = 5
RECENT_LOW_COUNT = 4
MIN_LOW_STRUCTURE_SPAN_DAYS = 144
STRUCTURE_NOISE_ATR_MULTIPLE = 1.0
RECENT_SUPPORT_LOOKBACK = 6
RECENT_LOW_MAX_ABOVE_L4_ATR_MULTIPLE = 1.0
RECENT_LOW_MAX_BELOW_L4_ATR_MULTIPLE = 1.618
POST_L4_CLOSE_MAX_BELOW_L4_ATR_MULTIPLE = 1.0
CURRENT_CLOSE_MAX_ABOVE_L4_STRONG_ATR_MULTIPLE = 1.618
CURRENT_CLOSE_MAX_ABOVE_L4_NORMAL_ATR_MULTIPLE = 1.0
CURRENT_CLOSE_MAX_ABOVE_RECENT_LOW_ATR_MULTIPLE = 1.2

VOLUME_AVG_MIN_RATIO = 0.8
LONG_BODY_MIN_RATIO = 0.8
LONG_BODY_ATR_MULTIPLE = 0.618
SMALL_CANDLE_ATR_MULTIPLE = 0.6
BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO = 0.618

TAKE_PROFIT_FIRST_RISK_MULTIPLE = 1.5
TAKE_PROFIT_SECOND_RISK_MULTIPLE = 2.0

# 第一止损位 = L4 - 1.618 * ATR30(L4)。与入场逻辑的噪音容忍带对齐：
# 入场时允许近期低点/右侧影线刺破到 L4 - 1.618*ATR30（视为正常噪音），
# 止损也必须放在该噪音带之外，否则持仓会死在自己定义的噪音里。
# （2023+2024 回测归因：旧 1.0 倍止损的亏单中 49.7% 在止损后 20 个交易日内收盘收复买入价）
STOP_LOSS_ATR_MULTIPLE = 1.618

# 右侧位置确认：T 日 boll_percent_b_20_2 >= 0.25，要求价格已脱离布林下轨。
# （归因数据：盈单买入日 %B 中位 0.34，亏单 0.20——贴着下轨买入更接近"接刀"）
RIGHT_SIDE_MIN_BOLL_PERCENT_B = 0.25

# 长期跌幅下限：T 日 roc_120 >= -20%，跌得过深的"筑底"更容易是中继。
# （归因数据：亏单 roc_120 中位 -10.9%，盈单 -7.4%）
MIN_ROC_120 = -0.20

LOW_CHANGE_FLAT = "震"
LOW_CHANGE_RISE = "涨"
LOW_CHANGE_FALL = "跌"

ALLOWED_LOW_PATTERNS = {
    (LOW_CHANGE_FLAT, LOW_CHANGE_FLAT, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FALL, LOW_CHANGE_FLAT, LOW_CHANGE_RISE),
    (LOW_CHANGE_FALL, LOW_CHANGE_RISE, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FALL, LOW_CHANGE_RISE, LOW_CHANGE_RISE),
    (LOW_CHANGE_FLAT, LOW_CHANGE_RISE, LOW_CHANGE_RISE),
    (LOW_CHANGE_RISE, LOW_CHANGE_FLAT, LOW_CHANGE_RISE),
    (LOW_CHANGE_RISE, LOW_CHANGE_RISE, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FLAT, LOW_CHANGE_FLAT, LOW_CHANGE_RISE),
    (LOW_CHANGE_RISE, LOW_CHANGE_FLAT, LOW_CHANGE_FLAT),
    (LOW_CHANGE_FLAT, LOW_CHANGE_RISE, LOW_CHANGE_FLAT),
    (LOW_CHANGE_RISE, LOW_CHANGE_RISE, LOW_CHANGE_RISE),
}

# 策略需要的宽表列（框架基础列 qfq_open/high/low/close、vol、is_st、name 之外）。
# MA/ATR/均量/K 线结构比例全部复用数据资产层预计算结果，策略内不再重复计算。
DEMO_REQUIRED_COLUMNS: tuple[str, ...] = (
    "ma_20",
    "ma_30",
    "atr_30",
    "atr_14",
    "avg_volume_10",
    "body_range_ratio",
    "body_atr14_ratio",
    "range_atr14_ratio",
    "upper_shadow_range_ratio",
    "lower_shadow_range_ratio",
    "boll_percent_b_20_2",
    "roc_120",
)


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
    opens = columns["qfq_open"]
    highs = columns["qfq_high"]
    lows = columns["qfq_low"]
    closes = columns["qfq_close"]

    with np.errstate(invalid="ignore", divide="ignore"):
        kline_pass = _kline_filter_series(columns)
        st_blocked = _st_blocked_series(columns)
        ma30_slopes = _rolling_linear_slopes(columns["ma_30"], MA30_SLOPE_WINDOW)
        ma20_slopes = _rolling_linear_slopes(columns["ma_20"], MA20_SLOPE_WINDOW)
    turn_indices = _negative_to_positive_turns(ma30_slopes)

    boll_percent_b = columns["boll_percent_b_20_2"]
    roc_120 = columns["roc_120"]

    results: dict[int, SignalDecision] = {}
    for index in target_indices:
        if st_blocked[index] or not kline_pass[index]:
            continue
        # 右侧位置确认：价格已脱离布林下轨（nan 视为不通过）
        if not boll_percent_b[index] >= RIGHT_SIDE_MIN_BOLL_PERCENT_B:
            continue
        # 长期跌幅下限：过深的下跌趋势不参与
        if not roc_120[index] >= MIN_ROC_120:
            continue
        trend = _resolve_trend_context(
            index=index,
            highs=highs,
            lows=lows,
            closes=closes,
            atr30=columns["atr_30"],
            ma30=columns["ma_30"],
            turn_indices=turn_indices,
            ma20_slopes=ma20_slopes,
        )
        if trend is None:
            continue
        l4_low, l4_atr30, l3_l4_high, l3_l4_max_close = trend
        signal_close = float(closes[index])
        first_stop = l4_low - STOP_LOSS_ATR_MULTIPLE * l4_atr30
        risk = signal_close - first_stop
        if not np.isfinite(risk) or risk <= 0:
            continue
        first_take_profit = signal_close + TAKE_PROFIT_FIRST_RISK_MULTIPLE * risk
        second_take_profit = signal_close + TAKE_PROFIT_SECOND_RISK_MULTIPLE * risk
        # 止盈可达性：最终止盈位必须低于 L3~L4 区间最高收盘价（前高阻力），
        # 止盈计划撞上阻力位说明盈亏目标不现实，信号作废
        if second_take_profit >= l3_l4_max_close:
            continue
        results[index] = SignalDecision(
            triggered=True,
            signal_close=signal_close,
            stop_losses=(first_stop, signal_close),
            take_profits=(first_take_profit, second_take_profit),
            max_watch_days=MAX_WATCH_DAYS,
            extras={
                "signal_atr30": l4_atr30,
                "l4_low": l4_low,
                "l3_l4_high": l3_l4_high,
                "l3_l4_max_close": l3_l4_max_close,
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
# K 线筛选（全序列向量化；形态条件复用宽表 K 线结构列）
# ---------------------------------------------------------------------------

def _kline_filter_series(columns: dict[str, Any]) -> np.ndarray:
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

    # 长实体：实体占比 >= 0.8 且实体 >= 0.618 * ATR14（宽表 body_atr14_ratio）
    long_body = (body_ratio >= LONG_BODY_MIN_RATIO) & (body_atr >= LONG_BODY_ATR_MULTIPLE)
    # 小线：总高度 <= 0.6 * ATR14（宽表 range_atr14_ratio）
    small_candle = range_atr <= SMALL_CANDLE_ATR_MULTIPLE
    # 量能：T 日成交量 >= 0.8 * 过去 10 日均量（宽表 avg_volume_10 含当日，取 T-1 行）
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

    # 启明之星：T 日长阳；T-4 ~ T-2 中存在长阴；之间 1~3 根小线
    bullish_long = bullish & long_body
    bearish_long = bearish & long_body
    small_cumsum = np.concatenate(([0], np.cumsum(small_candle.astype(np.int64))))
    morning_star = np.zeros(len(closes), dtype=bool)
    for gap in (2, 3, 4):  # 左侧大阴线在 i-gap，中间夹 gap-1 根小线
        left_ok = _shift_bool(bearish_long, gap)
        middle_count = gap - 1
        # small_candle[i-gap+1 .. i-1] 全部成立
        middle_ok = np.zeros(len(closes), dtype=bool)
        valid = np.arange(len(closes)) >= gap
        starts = np.maximum(np.arange(len(closes)) - gap + 1, 0)
        ends = np.maximum(np.arange(len(closes)), 0)
        counts = small_cumsum[ends] - small_cumsum[starts]
        middle_ok[valid] = counts[valid] == middle_count
        morning_star |= bullish_long & left_ok & middle_ok

    # 看涨吞没：T 长阳、T-1 长阴、T-1 实体 >= 0.618 * T 实体、T 实体区间完全吞没 T-1
    engulfing = (
        bullish_long
        & _shift_bool(bearish_long, 1)
        & (_shift_float(body, 1) >= body * BULLISH_ENGULFING_PREVIOUS_BODY_MIN_RATIO)
        & (body_low <= _shift_float(body_low, 1))
        & (body_high >= _shift_float(body_high, 1))
    )

    # 仙人指路：T 长阳、T-1 倒锤形、T 收盘 > T-1 最高
    fairy_guide = (
        bullish_long
        & _shift_bool(inverted_hammer_shape, 1)
        & (closes > _shift_float(highs, 1))
    )

    atr_ok = atr14 > 0
    return atr_ok & (dragonfly | hammer | morning_star | engulfing | fairy_guide)


def _shadow_ratio_at_least(
    long_ratio: np.ndarray,
    short_ratio: np.ndarray,
    multiple: float,
) -> np.ndarray:
    """长影线 / 短影线 >= multiple；短影线为 0 时只要求长影线 > 0。"""
    return (long_ratio > 0) & ((short_ratio <= 0) | (long_ratio >= multiple * short_ratio))


# ---------------------------------------------------------------------------
# 趋势筛选（逐目标日；MA30/MA20/ATR30 复用宽表列，仅结构识别在策略内完成）
# ---------------------------------------------------------------------------

def _resolve_trend_context(
    *,
    index: int,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr30: np.ndarray,
    ma30: np.ndarray,
    turn_indices: np.ndarray,
    ma20_slopes: np.ndarray,
) -> tuple[float, float, float, float] | None:
    window_start = index + 1 - _structure_window()
    if window_start < 0:
        return None
    # 窗口内 ma_30 必须就绪（上市初期 ma_30 为 null 时保守不出信号）
    if np.isnan(ma30[window_start]) or np.isnan(ma30[index]):
        return None

    # MA30 斜率负转正的点位数量需在 5 ~ 10
    left = int(np.searchsorted(turn_indices, window_start, side="left"))
    right = int(np.searchsorted(turn_indices, index, side="right"))
    turn_count = right - left
    if not (MIN_MA30_TURN_POINTS <= turn_count <= MAX_MA30_TURN_POINTS):
        return None
    recent_turns = turn_indices[right - RECENT_TURN_POINTS : right]

    # 最近 5 个转折点之间的 4 个区间低点 L1 ~ L4 及其 ATR30
    low_points: list[tuple[int, float, float]] = []
    for start, end in zip(recent_turns, recent_turns[1:]):
        segment = lows[start : end + 1]
        if len(segment) < 2 or np.isnan(segment).any():
            return None
        local = int(np.argmin(segment))
        low_index = int(start) + local
        low_value = float(segment[local])
        low_atr = float(atr30[low_index]) if not np.isnan(atr30[low_index]) else 0.0
        if low_atr <= 0:
            return None
        low_points.append((low_index, low_value, low_atr))
    if len(low_points) != RECENT_LOW_COUNT:
        return None
    if low_points[-1][0] - low_points[0][0] < MIN_LOW_STRUCTURE_SPAN_DAYS:
        return None

    low_pattern = _classify_low_changes(low_points)
    if low_pattern not in ALLOWED_LOW_PATTERNS:
        return None

    l4_index, l4_low, l4_atr30 = low_points[-1]

    # T ~ T-5 最低价仍落在 L4 附近
    recent_lows = lows[index + 1 - RECENT_SUPPORT_LOOKBACK : index + 1]
    if len(recent_lows) < RECENT_SUPPORT_LOOKBACK or np.isnan(recent_lows).any():
        return None
    recent_low = float(np.min(recent_lows))
    if not (
        l4_low - l4_atr30 * RECENT_LOW_MAX_BELOW_L4_ATR_MULTIPLE
        <= recent_low
        <= l4_low + l4_atr30 * RECENT_LOW_MAX_ABOVE_L4_ATR_MULTIPLE
    ):
        return None

    # T 日收盘价仍在合理买点区间
    current_close = float(closes[index])
    rise_count = sum(1 for item in low_pattern if item == LOW_CHANGE_RISE)
    upper_multiple = (
        CURRENT_CLOSE_MAX_ABOVE_L4_STRONG_ATR_MULTIPLE
        if rise_count >= 2
        else CURRENT_CLOSE_MAX_ABOVE_L4_NORMAL_ATR_MULTIPLE
    )
    if current_close > l4_low + l4_atr30 * upper_multiple:
        return None
    if current_close > recent_low + l4_atr30 * CURRENT_CLOSE_MAX_ABOVE_RECENT_LOW_ATR_MULTIPLE:
        return None

    # L4 到 T 的右侧区间未真实破坏 L4 支撑
    post_lows = lows[l4_index : index + 1]
    post_closes = closes[l4_index : index + 1]
    if np.isnan(post_lows).any() or np.isnan(post_closes).any():
        return None
    if float(np.min(post_lows)) < l4_low - l4_atr30 * RECENT_LOW_MAX_BELOW_L4_ATR_MULTIPLE:
        return None
    if float(np.min(post_closes)) < l4_low - l4_atr30 * POST_L4_CLOSE_MAX_BELOW_L4_ATR_MULTIPLE:
        return None

    # 最近 5 日 MA20 斜率至少 3 次相邻改善
    recent_slopes = ma20_slopes[index + 1 - MAX_MA20_SLOPE_IMPROVING_DAYS : index + 1]
    if len(recent_slopes) < MAX_MA20_SLOPE_IMPROVING_DAYS or np.isnan(recent_slopes).any():
        return None
    improving_steps = int(np.sum(np.diff(recent_slopes) > 0))
    if improving_steps < MIN_MA20_SLOPE_IMPROVING_STEPS:
        return None

    # L3 ~ L4 之间最高价与最高收盘价（后者作为止盈可达性的阻力参考）
    l3_index = low_points[-2][0]
    between_highs = highs[l3_index : l4_index + 1]
    between_closes = closes[l3_index : l4_index + 1]
    if len(between_highs) == 0 or np.isnan(between_highs).any() or np.isnan(between_closes).any():
        return None
    l3_l4_high = float(np.max(between_highs))
    l3_l4_max_close = float(np.max(between_closes))
    return l4_low, l4_atr30, l3_l4_high, l3_l4_max_close


def _structure_window() -> int:
    """结构窗口 = 框架统一传入的 400 根回看窗口。"""
    from app.services.signal_window import SIGNAL_WINDOW_BARS

    return SIGNAL_WINDOW_BARS


def _classify_low_changes(
    low_points: list[tuple[int, float, float]],
) -> tuple[str, ...]:
    changes: list[str] = []
    for (_pi, previous_low, _pa), (_ni, next_low, next_atr) in zip(low_points, low_points[1:]):
        delta = next_low - previous_low
        threshold = next_atr * STRUCTURE_NOISE_ATR_MULTIPLE
        if delta > threshold:
            changes.append(LOW_CHANGE_RISE)
        elif delta < -threshold:
            changes.append(LOW_CHANGE_FALL)
        else:
            changes.append(LOW_CHANGE_FLAT)
    return tuple(changes)


# ---------------------------------------------------------------------------
# 数值工具（仅保留宽表未覆盖的派生计算：滚动线性拟合斜率、转折点）
# ---------------------------------------------------------------------------

def _rolling_linear_slopes(values: np.ndarray, window: int) -> np.ndarray:
    """对序列做窗口内最小二乘线性拟合，返回每个位置的斜率（前 window-1 个为 nan）。

    nan 输入会自然传播：窗口内含 nan 的位置结果为 nan。
    """
    size = len(values)
    result = np.full(size, np.nan)
    if window <= 1 or size < window:
        return result
    x = np.arange(window, dtype=float)
    x_mean = (window - 1) / 2.0
    denominator = float(np.sum((x - x_mean) ** 2))
    kernel = (x - x_mean) / denominator
    # convolve 在窗口含 nan 时输出 nan，正符合"数据不足不出值"的语义
    result[window - 1 :] = np.convolve(values, kernel[::-1], mode="valid")
    return result


def _negative_to_positive_turns(slopes: np.ndarray) -> np.ndarray:
    previous = slopes[:-1]
    current = slopes[1:]
    mask = (previous < 0) & (current >= 0)
    return np.where(mask)[0] + 1


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


# ---------------------------------------------------------------------------
# MACD 背离过滤（当前关闭，不参与信号筛选）
# 启用时把 "macd_dif_12_26_9"、"macd_hist_12_26_9" 加入 DEMO_REQUIRED_COLUMNS，
# 直接使用宽表列（注意宽表 hist = dif - dea，国际口径不乘 2）。
# ---------------------------------------------------------------------------

MACD_DIVERGENCE_LOOKBACK = 120
PIVOT_NEIGHBOR_WINDOW = 3
MIN_PRICE_HIGHER_HIGH_RATIO = 0.01
MIN_MACD_WEAKEN_RATIO = 0.05
MACD_ZERO_EPSILON = 1e-9


def _has_bearish_macd_divergence(
    closes: np.ndarray,
    macd_dif: np.ndarray,
    macd_hist: np.ndarray,
    index: int,
) -> bool:
    start_index = max(index + 1 - MACD_DIVERGENCE_LOOKBACK, 0)
    pivots = _find_price_high_pivots(closes, start_index=start_index, end_index=index)
    if len(pivots) < 2:
        return False
    for previous_index, current_index in zip(pivots, pivots[1:]):
        previous_price = closes[previous_index]
        current_price = closes[current_index]
        if current_price <= previous_price * (1 + MIN_PRICE_HIGHER_HIGH_RATIO):
            continue
        if _is_indicator_weaker(macd_dif[previous_index], macd_dif[current_index]):
            return True
        if _is_indicator_weaker(macd_hist[previous_index], macd_hist[current_index]):
            return True
    return False


def _find_price_high_pivots(
    values: np.ndarray,
    *,
    start_index: int,
    end_index: int,
) -> list[int]:
    pivots: list[int] = []
    start = max(start_index, PIVOT_NEIGHBOR_WINDOW)
    end = min(end_index, len(values) - 1 - PIVOT_NEIGHBOR_WINDOW)
    for index in range(start, end + 1):
        current = values[index]
        left = values[index - PIVOT_NEIGHBOR_WINDOW : index]
        right = values[index + 1 : index + 1 + PIVOT_NEIGHBOR_WINDOW]
        if current >= np.max(left) and current > np.max(right):
            pivots.append(index)
    return pivots


def _is_indicator_weaker(previous: float, current: float) -> bool:
    baseline = max(abs(previous), MACD_ZERO_EPSILON)
    return current < previous - baseline * MIN_MACD_WEAKEN_RATIO
