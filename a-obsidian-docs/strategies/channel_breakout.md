# 趋势通道黄金碗策略

> 后端策略名：`channel_breakout`。该策略寻找长震荡通道后的黄金碗结构：左侧冲高形成前高，中间回落形成洼地，右侧阳线重新接近左高后进入短观察，盘中突破左高再买入，次日开盘卖出。

## 一、算法思想

1. 使用趋势通道算法识别 20 个交易日的长震荡通道。
2. 黄金碗不要求紧接着长震荡。只要黄金碗结构的突破日 `B` 往前 10 个交易日内存在长震荡结束点即可。
3. 长震荡后可以出现连续多个黄金碗，每个黄金碗都独立识别。
4. `B ~ T` 之间形成黄金碗结构：
   - 左侧有收盘价前高 `left_close_high`。
   - 中间有低于左高的收盘价洼地 `bowl_trough_close`。
   - 右侧最后一根 `T` 是阳线。
   - `T` 日收盘价达到左高的 0.98 倍。
5. `T` 日收盘后进入观察池，只观察 3 个交易日。
6. 观察期内任意一天盘中价格达到左高的 1.01 倍时买入，次日开盘卖出。

## 二、长震荡结构

在 `B` 之前最多 10 个交易日内，必须存在一个 20 日趋势通道结束点：

```text
1 <= B - channel.end <= 10
channel.length == 20
```

趋势通道折算的 K 实体宽度不超过 6%：

```text
channel_width_ratio <= 6%
```

通道末尾收盘价相比通道起点收盘价，可以下跌，涨幅不超过 8%：

```text
close(channel.end) / close(channel.start) - 1 <= 8%
```

## 三、突破 K 线

`B` 日实体涨幅不低于 6%：

```text
(close(B) - open(B)) / open(B) >= 6%
```

`B` 日收盘价突破通道右侧折算高点至少 3%：

```text
close(B) >= 1.03 * channel.upper_line_end
```

左侧前高不能离通道末尾过远：

```text
left_close_high <= 1.12 * close(channel.end)
```

## 四、黄金碗结构

信号日记为 `T`。在 `B ~ T` 的窗口内：

```text
left_close_high = max(close(B), close(B+1), ..., close(T-1))
bowl_trough_close = min(close(left_high_date+1), ..., close(T-1))
```

黄金碗必须满足：

```text
left_high_date < trough_date < T
bowl_trough_close < left_close_high
close(T) > open(T)
close(T) >= 0.98 * left_close_high
```

黄金碗识别参数：

```text
min_bowl_width = 3
max_bowl_width = 12
min_bowl_depth_ratio = 3%
max_bowl_depth_ratio = 20%
right_close_to_left_high_ratio = 0.98
max_channel_end_to_breakout_gap = 10
```

其中：

```text
bowl_width = T - left_high_date
bowl_depth_ratio = left_close_high / bowl_trough_close - 1
channel_end_to_breakout_gap = B - channel.end
```

黄金碗算法已解耦为通用模块：

```text
backend/strategies/algorithms/golden_bowl.py
```

## 五、交易

`T` 日收盘后进入观察池，不允许 `T` 当日买入。

观察池最长等待 3 个交易日：

```text
max_watch_days = 3
```

观察池内，当 `D` 日盘中最高价触及左高的 1.01 倍时，计算计划买入价：

```text
entry_trigger_price = left_close_high * 1.01
buy_price = max(open(D), entry_trigger_price)
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
