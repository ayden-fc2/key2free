"""姜神战法（强势回踩均线）。

来源：真实交易者 T/T+1 决策逻辑的逆向工程，参数用其 13 笔实盘买入的
决策日快照校准。详见 a-obsidian-docs/strategies/姜神/姜神战法.md。
"""
from __future__ import annotations

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


# ---------------------------------------------------------------------------
# 信号参数（数据锚点见策略文档第七节）
# ---------------------------------------------------------------------------

MIN_ROC_20 = 0.25                 # 强势池：20 日涨幅 >= 25%（13 样本中位 +42%）
TOUCH_MA10_TOLERANCE = 1.005      # 回踩触线：low <= ma_10 * 1.005（8/13 触及）
MIN_DRAWDOWN_FROM_HIGH = 0.03     # 距 20 日收盘高点回撤下限（排除新高日）
MAX_DRAWDOWN_FROM_HIGH = 0.20     # 回撤上限（排除主升已崩塌）
MAX_VOLUME_RATIO_10 = 1.2         # 缩量（13 样本中位 0.92）
HIGH_LOOKBACK = 20

# 交易参数（单层止盈止损）
JIANGSHEN_POSITION_FRACTION = 1.0 / 3.0
JIANGSHEN_MAX_HOLDING_DAYS = 3    # 持股 1~3 天，到期收盘卖出
MAX_WATCH_DAYS = 1                # 仅 T+1 开盘入场
STOP_LOSS_FLOOR_RATIO = 0.93      # 止损兜底：买入价 -7%（他的实盘砍仓纪律）
TAKE_PROFIT_RATIO = 1.10          # 止盈：买入价 +10%（盘中触及，约 1.4 倍盈亏比）

JIANGSHEN_REQUIRED_COLUMNS: tuple[str, ...] = (
    "roc_20",
    "ma_10",
    "ma_20",
    "ma_30",
    "volume_ratio_10",
)


def jiangshen_code_filter(code: str) -> bool:
    """主板普通 A 股代码形态（与 demo 同口径）。"""
    value = code.lower()
    if value.startswith("sh.688") or value.startswith("sz.300") or value.startswith("sz.301"):
        return False
    return value.startswith("sh.6") or value.startswith("sz.0")


def jiangshen_batch_signal_strategy(
    frame: StockDailyFrame,
    target_indices: list[int],
) -> dict[int, SignalDecision]:
    if not target_indices or len(frame) == 0:
        return {}
    columns = frame.columns
    opens = columns["qfq_open"]
    lows = columns["qfq_low"]
    closes = columns["qfq_close"]
    roc_20 = columns["roc_20"]
    ma_10 = columns["ma_10"]
    ma_20 = columns["ma_20"]
    ma_30 = columns["ma_30"]
    volume_ratio_10 = columns["volume_ratio_10"]
    st_blocked = _st_blocked_series(columns)

    results: dict[int, SignalDecision] = {}
    with np.errstate(invalid="ignore"):
        for index in target_indices:
            if index < HIGH_LOOKBACK or st_blocked[index]:
                continue
            # 1. 强势池：近期涨幅大 + 多头排列
            if not roc_20[index] >= MIN_ROC_20:
                continue
            if not ma_10[index] > ma_20[index] > ma_30[index]:
                continue
            # 2. 回踩触线：影线触及 MA10，收盘守住 MA20，回撤幅度适中
            if not lows[index] <= ma_10[index] * TOUCH_MA10_TOLERANCE:
                continue
            if not closes[index] >= ma_20[index]:
                continue
            high_20d = float(np.nanmax(closes[index - HIGH_LOOKBACK + 1 : index + 1]))
            if not high_20d > 0:
                continue
            drawdown = 1.0 - float(closes[index]) / high_20d
            if not (MIN_DRAWDOWN_FROM_HIGH <= drawdown <= MAX_DRAWDOWN_FROM_HIGH):
                continue
            # 3. 缩量企稳：量能收缩 + 收阳
            if not volume_ratio_10[index] <= MAX_VOLUME_RATIO_10:
                continue
            if not closes[index] >= opens[index]:
                continue
            results[index] = SignalDecision(
                triggered=True,
                signal_close=float(closes[index]),
                # 止损/止盈依赖 T+1 成交价，由引擎在成交时通过 exit_plan 落定
                stop_losses=(),
                take_profits=(),
                max_watch_days=MAX_WATCH_DAYS,
                extras={
                    "ma_10": float(ma_10[index]),
                    "ma_20": float(ma_20[index]),
                    "roc_20": float(roc_20[index]),
                    "high_20d": high_20d,
                    "drawdown_from_high": drawdown,
                    "volume_ratio_10": float(volume_ratio_10[index]),
                },
            )
    return results


def jiangshen_exit_plan(
    buy_price: float,
    signal: dict,
) -> tuple[list[float], list[float]] | None:
    """单层止盈止损：止损 = max(T 日 MA20, 买入价×0.93)（收盘确认），止盈 = 买入价×1.10（盘中）。

    开盘已低于止损位（跳空砸穿支撑）时放弃买入。
    """
    extras = signal.get("extras") or {}
    ma_20 = extras.get("ma_20")
    if not isinstance(ma_20, (int, float)):
        return None
    stop = max(float(ma_20), buy_price * STOP_LOSS_FLOOR_RATIO)
    if buy_price <= stop:
        return None
    return ([stop], [buy_price * TAKE_PROFIT_RATIO])


def _st_blocked_series(columns: dict) -> np.ndarray:
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
