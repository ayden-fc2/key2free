"""黄金柱战法 —— ❌ 已失败归档（2026-06）。

形态归因（scripts/golden_pillar_analysis.py，2316 样本）证实该形态无选股信息量：
盈亏组在所有宽表特征上无区分度，前向超额收益中位数全程为负。
代码保留供复验与方法论参考，不再迭代。详见 a-obsidian-docs/strategies/黄金柱战法.md。
"""
from __future__ import annotations

import numpy as np

from app.entities.stock_data_context import SignalDecision, StockDailyFrame


# ---------------------------------------------------------------------------
# 参数（口径见 a-obsidian-docs/strategies/黄金柱战法.md，均为待回测校准的初值）
# ---------------------------------------------------------------------------

# T-4 建仓期：趋势效率低 + 长期缩量
# 2026-06 校准（"温和组合2"）：初版七条件连乘下两年仅 2 个信号，
# 单变量敏感性分析后放宽五个阈值到两年约 44 个信号，详见策略文档。
BASE_MAX_ER_10 = 0.25
BASE_MAX_VOLUME_SHRINK_RATIO = 0.85  # avg_volume_5 <= 0.85 * avg_volume_20

# T-3 黄金柱：影线小、实体大、涨幅硬条件、倍量
PILLAR_MIN_BODY_RANGE_RATIO = 0.8
PILLAR_MIN_BODY_ATR14_RATIO = 1.5  # 建仓期 ATR14 偏小，实体阈值取 1.5 倍
# 涨幅硬性条件：建仓期 ATR 很小时，1.5*ATR14 的"大阳"可能只有 2~3 个点，
# 仍属震荡噪音（案例：sh.603217 2021-06）。黄金柱当日涨幅必须 > 5%。
PILLAR_MIN_PCT_CHG = 5.0  # 宽表 pct_chg 为百分比口径
PILLAR_MIN_VOLUME_MULTIPLE = 1.8   # vol(T-3) >= 1.8 * avg_volume_10(T-4)

# 柱前纯净期：黄金柱必须是震荡后的第一根启动柱。柱前 20 个交易日内
# 出现过大实体 K 线（阴阳不限）或显著放量日，都说明启动早已发生、当前柱是
# 二波或区间摆动，拒绝。两个维度互补：
# - 实体维度（案例 sz.000998 2020：柱前 10 日有实体 1.52*ATR 的大阳）
# - 量能维度（案例 sh.603217 2021-06：柱前 20 日有 +6.5%、4.9 倍量的启动柱，
#   但当时 ATR 偏大、实体仅 1.07*ATR，逃过实体阈值——放量本身就是已启动的铁证）
PRE_PILLAR_CLEAN_DAYS = 20
PRE_PILLAR_MAX_BODY_ATR14_RATIO = 1.2
PRE_PILLAR_MAX_VOLUME_RATIO_20 = 3.0

# T-2 ~ T 试盘期：小实体（允许阴线）、缩量、守住柱体 80% 位
TEST_DAYS = 3
TEST_MAX_BODY_ATR14_RATIO = 0.6
TEST_MAX_VOLUME_VS_PILLAR = 0.75
PILLAR_HOLD_RATIO = 0.8  # close >= open(T-3) + 0.8 * 柱体高度

# 交易规则
GOLDEN_PILLAR_POSITION_FRACTION = 1.0 / 3.0
GOLDEN_PILLAR_MAX_HOLDING_DAYS = 15
MAX_WATCH_DAYS = 1  # 仅 T+1 一天，开盘直接买入
TAKE_PROFIT_FIRST_RISK_MULTIPLE = 1.5
TAKE_PROFIT_SECOND_RISK_MULTIPLE = 2.0
STOP_PILLAR_MID_RATIO = 0.5  # 第一止损 = 柱体中点

# 出场价位模式（2026-06 实验定型：柱高锚定。两年对比 base 年化 -5.1% / 盈亏比 0.70，
# 柱高锚定 + 高位过滤 -0.4% / 1.43，详见策略文档实验记录）：
# "pillar_height" —— 默认：全部以柱体实体高度 H 锚定：
#                    止损1=买入价-0.5H、止损2=买入价+0.5H（锁盈）；止盈1=买入价+H、止盈2=买入价+1.5H
# "risk"          —— 旧 base：止损1=柱体中点、止损2=买入价；止盈=买入价+1.5R/2R（R=买入价-止损1）
EXIT_PLAN_MODE = "pillar_height"

# 高位过滤（已退役，默认关闭）——2026-06 形态归因（2316 个放宽候选样本，
# scripts/golden_pillar_analysis.py）显示 roc_120 / bias_120 在盈亏组间零区分度，
# 此前"开启后年化改善"是 2 个信号的小样本巧合。保留开关供复验。
ENABLE_HIGH_POSITION_FILTER = False
HIGH_POSITION_MAX_ROC_120 = 0.5
HIGH_POSITION_MAX_BIAS_120 = 0.3

PILLAR_OFFSET = 3  # 黄金柱在 T-3
BASE_OFFSET = 4    # 建仓期判定在 T-4

GOLDEN_PILLAR_REQUIRED_COLUMNS: tuple[str, ...] = (
    "er_10",
    "avg_volume_5",
    "avg_volume_10",
    "avg_volume_20",
    "body_range_ratio",
    "body_atr14_ratio",
    "roc_120",
    "bias_120",
    "pct_chg",
    "volume_ratio_20",
)


def golden_pillar_code_filter(code: str) -> bool:
    """主板普通 A 股代码形态（与 demo 同口径）。"""
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
    volumes = columns["vol"]
    er_10 = columns["er_10"]
    avg_volume_5 = columns["avg_volume_5"]
    avg_volume_10 = columns["avg_volume_10"]
    avg_volume_20 = columns["avg_volume_20"]
    body_range_ratio = columns["body_range_ratio"]
    body_atr14_ratio = columns["body_atr14_ratio"]
    roc_120 = columns["roc_120"]
    bias_120 = columns["bias_120"]
    pct_chg = columns["pct_chg"]
    volume_ratio_20 = columns["volume_ratio_20"]
    st_blocked = _st_blocked_series(columns)

    results: dict[int, SignalDecision] = {}
    with np.errstate(invalid="ignore"):
        for index in target_indices:
            if index < BASE_OFFSET or st_blocked[index]:
                continue
            # 实验2：高位过滤——过去大涨或当前远离年线的不参与
            if ENABLE_HIGH_POSITION_FILTER:
                if roc_120[index] > HIGH_POSITION_MAX_ROC_120:
                    continue
                if bias_120[index] > HIGH_POSITION_MAX_BIAS_120:
                    continue
            pillar = index - PILLAR_OFFSET
            base = index - BASE_OFFSET

            # 1. T-4 建仓期：长期震荡 + 缩量
            if not er_10[base] <= BASE_MAX_ER_10:
                continue
            if not avg_volume_5[base] <= BASE_MAX_VOLUME_SHRINK_RATIO * avg_volume_20[base]:
                continue

            # 2. T-3 黄金柱：放量大阳线
            pillar_height = closes[pillar] - opens[pillar]
            if not pillar_height > 0:
                continue
            if not body_range_ratio[pillar] >= PILLAR_MIN_BODY_RANGE_RATIO:
                continue
            if not body_atr14_ratio[pillar] >= PILLAR_MIN_BODY_ATR14_RATIO:
                continue
            if not pct_chg[pillar] >= PILLAR_MIN_PCT_CHG:
                continue
            if not volumes[pillar] >= PILLAR_MIN_VOLUME_MULTIPLE * avg_volume_10[base]:
                continue
            # 柱前纯净期：确保是震荡后的第一根启动柱，不追二波柱/区间摆动
            clean_start = pillar - PRE_PILLAR_CLEAN_DAYS
            if clean_start < 0:
                continue
            if np.any(
                body_atr14_ratio[clean_start:pillar] >= PRE_PILLAR_MAX_BODY_ATR14_RATIO
            ):
                continue
            if np.any(
                volume_ratio_20[clean_start:pillar] >= PRE_PILLAR_MAX_VOLUME_RATIO_20
            ):
                continue

            # 3. T-2 ~ T 试盘期：小实体（允许阴线）、缩量、守住柱体 90% 位
            hold_level = opens[pillar] + PILLAR_HOLD_RATIO * pillar_height
            test_ok = True
            for test_index in range(index - TEST_DAYS + 1, index + 1):
                if not body_atr14_ratio[test_index] <= TEST_MAX_BODY_ATR14_RATIO:
                    test_ok = False
                    break
                if not volumes[test_index] <= TEST_MAX_VOLUME_VS_PILLAR * volumes[pillar]:
                    test_ok = False
                    break
                if not closes[test_index] >= hold_level:
                    test_ok = False
                    break
            if not test_ok:
                continue

            pillar_mid = float(opens[pillar] + STOP_PILLAR_MID_RATIO * pillar_height)
            results[index] = SignalDecision(
                triggered=True,
                signal_close=float(closes[index]),
                # 全部出场价位依赖 T+1 成交价，信号日无法确定，由回测引擎在
                # 成交时通过 exit_plan 落定；柱体参考价位放在 extras 供复盘
                stop_losses=(),
                take_profits=(),
                max_watch_days=MAX_WATCH_DAYS,
                extras={
                    "pillar_open": float(opens[pillar]),
                    "pillar_close": float(closes[pillar]),
                    "pillar_volume": float(volumes[pillar]),
                    "pillar_mid": pillar_mid,
                    "hold_level": float(hold_level),
                    "er_10_t4": float(er_10[base]),
                },
            )
    return results


def golden_pillar_exit_plan(
    buy_price: float,
    signal: dict,
) -> tuple[list[float], list[float]] | None:
    """成交时落定价位，按 EXIT_PLAN_MODE 选择锚定方式。

    - "risk"：第一止损=柱体中点，第二止损=买入价，止盈=买入价 + 1.5R/2R；
      买入价不高于柱体中点（开盘直接砸穿结构）时放弃买入。
    - "pillar_height"：以柱体实体高度 H 锚定——止损1=买入价-0.5H、
      止损2=买入价+0.5H（锁盈）；止盈1=买入价+H、止盈2=买入价+1.5H。
    """
    if EXIT_PLAN_MODE == "pillar_height":
        extras = signal.get("extras") or {}
        pillar_open = extras.get("pillar_open")
        pillar_close = extras.get("pillar_close")
        if not isinstance(pillar_open, (int, float)) or not isinstance(pillar_close, (int, float)):
            return None
        height = float(pillar_close) - float(pillar_open)
        if height <= 0:
            return None
        return (
            [buy_price - 0.5 * height, buy_price + 0.5 * height],
            [buy_price + height, buy_price + 1.5 * height],
        )
    extras = signal.get("extras") or {}
    pillar_mid = extras.get("pillar_mid")
    if not isinstance(pillar_mid, (int, float)):
        return None
    risk = buy_price - float(pillar_mid)
    if risk <= 0:
        return None
    return (
        [float(pillar_mid), buy_price],
        [
            buy_price + TAKE_PROFIT_FIRST_RISK_MULTIPLE * risk,
            buy_price + TAKE_PROFIT_SECOND_RISK_MULTIPLE * risk,
        ],
    )


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
