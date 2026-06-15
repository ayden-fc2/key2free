# Demo 演示策略

> 后端策略名：`demo`。该策略只用于验证信号、入场、持仓和出场框架，不再承载真实选股逻辑。

## 一、信号

所有输入股票只在固定日期爆信号：

```text
T = 2026-06-15
```

信号日收盘价记为 `signal_close`。

## 二、交易

信号出现后只观察下一个交易日：

```text
max_watch_days = 1
```

入场使用回测框架通用 `next_open`：

```text
T+1 开盘价买入
```

买入后只持仓 1 个交易日：

```text
max_holding_days = 1
```

到期按收盘价卖出：

```text
买入后的下一个交易日收盘价卖出
```

仓位使用回测框架通用风险定仓，并保留单票市值上限：

```text
position_cap_fraction = 1/4
```

## 三、通用算法挂载

Demo 策略已挂载策略通用算法目录：

```text
backend/strategies/algorithms/
```

当前包含：

- `trend_channel.py`：趋势通道长震荡识别，支持上升、平稳、下降通道。
- `n_bottom.py`：基于 MA 斜率极值的 N 字折线识别。

Demo 只把这些算法的预览结果写入 `extras.algorithm_modules`，不使用它们决定是否爆信号。
