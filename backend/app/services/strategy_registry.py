from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from app.entities.stock_data_context import SignalDecision, StockDailyFrame
from strategies.demo import (
    DEMO_MAX_HOLDING_DAYS,
    DEMO_REQUIRED_COLUMNS,
    demo_batch_signal_strategy,
    demo_code_filter,
)
from strategies.golden_pillar import (
    GOLDEN_PILLAR_MAX_HOLDING_DAYS,
    GOLDEN_PILLAR_POSITION_FRACTION,
    GOLDEN_PILLAR_REQUIRED_COLUMNS,
    golden_pillar_batch_signal_strategy,
    golden_pillar_code_filter,
    golden_pillar_exit_plan,
)
from strategies.jiangshen import (
    JIANGSHEN_MAX_HOLDING_DAYS,
    JIANGSHEN_POSITION_FRACTION,
    JIANGSHEN_REQUIRED_COLUMNS,
    jiangshen_batch_signal_strategy,
    jiangshen_code_filter,
    jiangshen_exit_plan,
)


class BatchSignalFn(Protocol):
    """逐股批量信号评估函数。

    输入单只股票的宽表列式数据（含评估区间前的 400 根回看窗口）和
    目标评估位置（保证每个位置之前至少有 400 根历史，含该位置）。
    返回 {位置索引: SignalDecision}，只需要包含 triggered=True 的位置。
    """

    def __call__(
        self,
        frame: StockDailyFrame,
        target_indices: list[int],
    ) -> dict[int, SignalDecision]:
        ...


@dataclass(frozen=True)
class StrategyRegistration:
    """策略注册项（v2）。

    - batch_signal_strategy: 必须，逐股批量信号评估。
    - required_columns: 策略需要的宽表列（框架基础列之外的部分）。
    - code_filter: 可选，代码级静态预过滤（板块/交易所），用于减少历史加载量；
      与交易日相关的成分条件（如 is_st）在信号函数内基于宽表列判断。
    - entry_mode: "limit_signal_close"（默认，signal_close 限价）或
      "next_open"（次日开盘市价买入，停牌/一字板放弃）。
    - position_sizing: "risk"（默认，2% 风险定仓）或 "fraction"（总资产固定比例）。
    - risk_price_basis: 风险定仓参考价，"buy_price" 使用实际成交价，
      "signal_close" 使用信号日收盘价。
    - position_cap_fraction: 可选，单笔买入市值不超过总资产的固定比例上限。
    - exit_plan_builder: 可选，成交时落定止损/止盈价位数组：
      输入 (买入成交价, 信号 dict)，返回 (stop_losses, take_profits)；
      返回 None 表示该成交价下风险无法界定，放弃买入。
      缺省直接使用信号中携带的 stop_losses / take_profits。
    - max_holding_days: 可选，持仓时限（交易日），到期日收盘强制卖出。
    - entry_strategy / exit_strategy: 可选，完全覆写入场/出场判定（一般不需要）。
    """

    name: str
    batch_signal_strategy: BatchSignalFn
    required_columns: tuple[str, ...] = ()
    code_filter: Callable[[str], bool] | None = None
    entry_mode: str = "limit_signal_close"
    position_sizing: str = "risk"
    risk_per_trade: float = 0.02
    risk_price_basis: str = "buy_price"
    position_cap_fraction: float | None = None
    position_fraction: float = 1.0 / 3.0
    exit_plan_builder: (
        Callable[[float, dict], tuple[list[float], list[float]] | None] | None
    ) = None
    max_holding_days: int | None = None
    entry_strategy: Callable[..., Any] | None = None
    exit_strategy: Callable[..., Any] | None = None


STRATEGY_REGISTRY: dict[str, StrategyRegistration] = {
    "demo": StrategyRegistration(
        name="demo",
        batch_signal_strategy=demo_batch_signal_strategy,
        required_columns=DEMO_REQUIRED_COLUMNS,
        code_filter=demo_code_filter,
        entry_mode="next_open",
        risk_price_basis="signal_close",
        position_cap_fraction=1.0 / 4.0,
        max_holding_days=DEMO_MAX_HOLDING_DAYS,
    ),
    "golden_pillar": StrategyRegistration(
        name="golden_pillar",
        batch_signal_strategy=golden_pillar_batch_signal_strategy,
        required_columns=GOLDEN_PILLAR_REQUIRED_COLUMNS,
        code_filter=golden_pillar_code_filter,
        entry_mode="next_open",
        position_sizing="fraction",
        position_fraction=GOLDEN_PILLAR_POSITION_FRACTION,
        exit_plan_builder=golden_pillar_exit_plan,
        max_holding_days=GOLDEN_PILLAR_MAX_HOLDING_DAYS,
    ),
    "jiangshen": StrategyRegistration(
        name="jiangshen",
        batch_signal_strategy=jiangshen_batch_signal_strategy,
        required_columns=JIANGSHEN_REQUIRED_COLUMNS,
        code_filter=jiangshen_code_filter,
        entry_mode="next_open",
        position_sizing="fraction",
        position_fraction=JIANGSHEN_POSITION_FRACTION,
        exit_plan_builder=jiangshen_exit_plan,
        max_holding_days=JIANGSHEN_MAX_HOLDING_DAYS,
    ),
}


def get_strategy(name: str) -> StrategyRegistration | None:
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    return sorted(STRATEGY_REGISTRY)
