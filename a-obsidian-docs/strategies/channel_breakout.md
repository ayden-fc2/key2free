# 趋势通道回踩左高策略

> 后端策略名：`channel_breakout`。该策略寻找长震荡通道后的首次冲高，冲高转弱后进入观察池，后续盘中重新打到左侧收盘高点再买入，次日开盘卖出。

## 一、算法思想

1. 先用趋势通道算法识别 `B` 日之前的长震荡通道。
2. `B` 日出现有效冲高，收盘突破通道右侧折算高点。
3. 从 `B` 日开始只关注收盘价，忽略开盘价、盘中价扰动，记录冲高段的左侧收盘价高点。
4. 冲高过程中第一次出现收盘价转弱时，认为跌破左侧收盘价高点，进入观察池。
5. 观察池内最多等待 12 个交易日，盘中价格打到左高的 1.01 倍时买入，次日开盘价卖出。

## 二、信号指标

信号日记为 `T`，首次冲高日记为 `B`。

1. `B-20 ~ B-1` 是趋势通道，长度为 20 个交易日：

```text
channel.end == B-1
channel.length == 20
```

2. 趋势通道折算的 K 实体宽度不超过 6%：

```text
channel_width_ratio <= 6%
```

3. 通道末尾收盘价相比通道起点收盘价，可以下跌，涨幅不超过 8%：

```text
close(B-1) / close(B-20) - 1 <= 8%
```

4. `B` 日实体涨幅不低于 6%：

```text
(close(B) - open(B)) / open(B) >= 6%
```

5. `B` 日收盘价突破通道右侧折算高点至少 3%：

```text
close(B) >= 1.03 * channel.upper_line_end
```

6. `B ~ T-1` 是收盘价不下降的冲高段，`T` 是第一次收盘转弱：

```text
close(B) <= close(B+1) <= ... <= close(T-1)
close(T) < close(T-1)
```

7. 左侧收盘价高点：

```text
left_close_high = max(close(B), close(B+1), ..., close(T-1))
```

8. 左侧收盘价高点不能离通道末尾过远：

```text
left_close_high <= 1.12 * close(channel.end)
```

9. `B` 到 `T` 的最长冲高识别窗口为 5 个交易日。

## 三、交易

`T` 日收盘后进入观察池，不允许 `T` 当日买入。

观察池最长等待 12 个交易日：

```text
max_watch_days = 12
```

观察池内，当 `D` 日盘中最高价触及左高的 1.01 倍时，计算计划买入价：

```text
entry_trigger_price = left_close_high * 1.01
buy_price = max(open(D), entry_trigger_price)
```

买入价相对 `D-1` 日 MA10 必须处在 3% 到 10% 区间内，避免盘中买入时使用 `D` 日收盘后才知道的 MA10：

```text
1.03 * MA10(D-1) <= buy_price <= 1.10 * MA10(D-1)
```

买入后只持仓 1 个交易日，次日开盘价卖出：

```text
max_holding_days = 1
time_exit_price = open
```

仓位使用固定比例：

```text
position_fraction = 1/4
```
