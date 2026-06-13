from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SignalDecision:
    """信号策略标准输出（v2）。

    - signal_close: T 日前复权收盘价，同时是确认买入价（观望期内触及即成交）。
    - stop_losses / take_profits: 等长的档位数组，持仓初始在第 0 档；
      触发非末档止盈卖出一半并升档，触发当前档止损全部卖出，触发末档止盈全部卖出。
    - extras: 策略自定义参考值（如 signal_atr30、结构低点），框架透传，不参与撮合。
    """

    triggered: bool
    signal_close: float | None = None
    stop_losses: tuple[float, ...] = ()
    take_profits: tuple[float, ...] = ()
    max_watch_days: int | None = None
    extras: dict[str, Any] | None = None


@dataclass(frozen=True)
class StockDailyFrame:
    """单只股票的宽表列式窗口，按交易日升序。

    columns 中数值列为 float 数组（numpy.ndarray，缺失为 nan），
    文本列（如 name）为 object 数组。
    """

    code: str
    trade_dates: list[date]
    columns: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.trade_dates)


@dataclass(frozen=True)
class StockDataContext:
    """前端图表等展示场景使用的单股全量上下文（非信号策略输入）。"""

    code: str
    trade_date: date
    universe: dict[str, Any]
    bars_1d_qfq: list[dict[str, Any]]
