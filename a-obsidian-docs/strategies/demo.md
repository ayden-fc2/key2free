# demo 策略

`demo` 是当前策略系统的标准接入样例，用于定义策略目录、函数命名、注册方式和信号系统调用形态。当前信号策略已加入基础成分筛选和趋势筛选，用于验证完整信号流程。

## 基本信息

| 项目 | 内容 |
| --- | --- |
| 策略注册名 | `demo` |
| 后端目录 | `backend/strategies/demo/` |
| 策略文件 | `backend/strategies/demo/strategy.py` |
| 注册位置 | `backend/app/services/strategy_registry.py` |
| 当前用途 | 策略接入规范样例和基础趋势信号样例 |
| 当日信号历史窗口 | 每只股票最多读取 `T` 及以前最近 380 根前复权日线 |

## 目录结构

```text
backend/strategies/demo/
  __init__.py
  strategy.py
```

## 策略函数

| 函数 | 类型 | 当前行为 |
| --- | --- | --- |
| `demo_signal_strategy` | 信号策略 | 接收 `StockDataContext`，执行成分筛选和趋势筛选。 |
| `demo_universe_filter` | 成分预过滤 | 只基于 `universe_daily` 的 `T` 日字段筛普通 A 股，用于在读取历史 K 线前缩小股票池。 |
| `demo_entry_strategy` | 入场策略 | 当前占位，统一返回 `-1`。 |
| `demo_exit_strategy` | 出场策略 | 当前占位，统一返回 `-1`。 |

## 信号规则

### 1. 成分筛选

只保留普通 A 股：

- `security_type == 1`。
- `list_status == 1`。
- 排除科创板：`sh.688*`。
- 排除创业板：`sz.300*`、`sz.301*`。
- 排除 ST：股票名称包含 `ST`、`*` 或 `＊` 时剔除。
- 代码需属于主板形态：`sh.6*` 或 `sz.0*`。

### 2. 趋势筛选

基于 `bars_1d_qfq` 计算：

- `T-1` 日 `MA20 < MA30`。
- `T` 日 `MA20 > MA30`。
- 对 `MA20` 做 10 日滚动线性拟合。
- `T` 日拟合斜率用 `ATR14` 标准化后必须大于阈值。
- 最近 10 日标准化斜率需要呈现由负值到接近 0 再到正值的过程。
- 对过去 300 个交易日的 `MA30` 做 10 日滚动线性拟合，找到斜率由负转正的点位。
- 在相邻负转正点之间提取价格区间低点和高点。
- 要求区间低点数量不少于 3。
- 区间低点和高点分别进入结构筛选，二者都必须通过。
- 高点或低点结构使用 `ATR30` 做标准化，避免用短期波动衡量 300 日结构。
- 对高点或低点序列做线性拟合，使用 `RMSE / ATR30` 衡量离散度，使用 `斜率 / ATR30` 衡量上升力度。
- 当 `RMSE / ATR30 <= 0.8` 时，视为低离散度结构：要求拟合斜率为正，且 `斜率 / ATR30 > 0.08`；允许少量相邻点小幅回落，但最近两个高点或最近两个低点不能下降。这会过滤掉整体还向上、但尾部已经走弱的形态。
- 当 `RMSE / ATR30 > 0.8` 时，视为高离散度结构：只接受“前期先下降、近期重新上升”的修复结构，即最低点不能出现在序列最前或最后，最低点前的拟合斜率需要小于等于 0，最低点后的拟合斜率需要重新转正且 `斜率 / ATR30 > 0.08`，最后两个点必须继续抬升，并且最后一个点相对最低点至少修复 `0.3 * ATR30`。
- 计算 MACD：`DIF = EMA12 - EMA26`，`DEA = EMA(DIF, 9)`，`MACD = 2 * (DIF - DEA)`。
- 在最近 120 个交易日内按收盘价寻找价格局部高点。
- 扫描相邻局部高点组合；只要后一个局部高点比前一个局部高点至少高出 1%，但对应 `DIF` 或 `MACD` 柱低于前一个高点处的值超过 5%，就视为不利多的顶背离，直接过滤。
- `DIF` 和 `MACD` 柱只要任一项出现明显走弱，就触发背离过滤；接近 0 或负值区域也按“当前值进一步降低”为走弱处理。
- 当前策略文件预留 `_average_volume_true_range`，按成交量相邻日绝对变化的移动平均计算 `Volume ATR30`。它暂不参与 demo 筛选，后续可用于识别放量、异常大量或量能波动。

## 信号策略输入

`demo_signal_strategy` 接收信号系统构造的 `StockDataContext`。其中 `bars_1d_qfq` 默认包含该股票在 `T` 及以前所有交易日的前复权日线历史。这个上下文也可作为后续回测渲染、均线绘制、MACD 绘制和其他指标 utils 的统一数据基准。

当前 demo 在注册表中配置了当日信号历史窗口，后端执行 `/signals/daily` 时只会为 demo 读取每只股票 `T` 及以前最近 380 根前复权日线。该窗口覆盖 MA30、300 日结构、ATR30、MA20 斜率和 120 日 MACD 背离所需数据，不读取 `T` 之后的数据，因此不引入未来函数。前端图表用的 `stock-contexts` 接口仍会拉取数据库中的全量 `StockDataContext`。

前端当日信号页拿到 demo 信号后，会再批量拉取这些股票在数据库中的全量 `StockDataContext`，并通过可复用图表组件渲染日 K、MA5/MA10/MA20/MA30、MACD 和成交量。图表默认显示最后 60 个交易日，三个视图共享缩放拖动。

```python
def demo_signal_strategy(context: StockDataContext) -> bool:
    ...
```

核心字段见 [[2. 信号系统#信号系统输入输出规范]] 和 [[4. 具体股票策略#信号策略]]。

## 注册方式

在 `STRATEGY_REGISTRY` 中注册：

```python
"demo": StrategyRegistration(
    name="demo",
    signal_strategy=demo_signal_strategy,
    entry_strategy=demo_entry_strategy,
    exit_strategy=demo_exit_strategy,
    universe_filter=demo_universe_filter,
    daily_signal_history_limit=380,
)
```

前端选择策略时使用同一个注册名 `demo`。

## 后续扩展准则

- 新策略应复制 `demo` 的目录结构。
- 每个策略必须提供信号策略、入场策略、出场策略三个函数。
- 策略注册名应稳定，前端和后端都用注册名识别策略。
- 信号策略只判断是否爆信号，不处理资金、仓位、成交、止盈止损。
- 入场策略和出场策略当前仍是占位接口，等回测模块确定输入输出后再补充。
