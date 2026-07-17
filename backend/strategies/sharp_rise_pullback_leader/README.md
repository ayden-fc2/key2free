# 龙头冲高回踩策略

注册名：`sharp_rise_pullback_leader`

策略版本：`1.0.0`

策略在信号日 T 收盘后建立 `S -> H -> L -> T` 四点结构，并冻结观察买入价 `bug_price`。信号函数只能读取截至 T 日的数据；买入和卖出阶段只能读取观察日或持仓日当时已经可见的行情，不读取未来交易日数据。

价格口径：

- 基础价格过滤使用未复权 `close`。
- S、H、L、T 结构、MA 和买卖价格统一使用前复权 `qfq_*` 口径。
- `bug_price` 是策略数据模型字段，同时写入框架标准字段 `entry_trigger_price`。

## 一、信号函数与数据模型

### 1. T：锚点日

T 日必须同时满足：

1. 排除股票名称包含 `ST` 或宽表字段 `is_st != 0` 的股票。
2. 排除代码以 `sh.688` 开头的科创板股票。
3. `MA10 > MA20 > MA30`。
4. T 日换手率位于 `8% <= turnover_rate <= 12%`，包含边界。
5. T 日 `BIAS20 >= 10%`，其中 `BIAS20 = T_qfq_close / T_MA20 - 1`，宽表以小数保存，因此代码阈值为 `0.10`。
6. T 日未复权收盘价 `close >= 10`。
7. T 日前复权收盘价位于 MA10 附近：`T_MA10 * 0.95 <= T_qfq_close <= T_MA10 * 1.02`。

`1.0.0` 不使用 T 日五日量比过滤，`volume_ratio_5` 不参与信号判定。

### 2. S：多头排列起点

从 T 向前连续寻找 `MA10 > MA20 > MA30` 的当前多头排列区间，区间最早一日记为 S。

- S 到 T 的交易日索引距离必须 `>= 17`。
- S、T 都计入当前连续多头排列区间。

### 3. H：区间最高点

在 `[S, T)` 中寻找前复权盘中最高价 `qfq_high` 最大的一日，记为 H；若最高价并列，取日期较晚的一日。

- H 到 T 的交易日索引距离必须在 `3 ~ 10` 之间，包含边界。
- `H_qfq_high / S_qfq_close - 1` 只作为信号诊断字段记录，不参与信号过滤。

### 4. L：回踩最低点

在 `[H, T]` 中寻找前复权盘中最低价 `qfq_low` 最小的一日，记为 L；若最低价并列，取日期较晚的一日。

- L 可以与 H 同一天，也可以与 T 同一天。
- `L_low >= L_MA20 * 0.95`。
- `L_low <= L_MA10 * 1.02`。
- H 到 L 的回撤幅度 `(H_high - L_low) / H_high >= 7%`。

### 5. bug_price：观察买入价

买入价不再根据 L 相对 MA10、MA20 的位置分段计算，而是只确认 T 日已回到 MA10 附近，并取 MA10 与 T 日收盘后再上涨 2% 两者中的较高值：

```text
bug_price = max(T_MA10, T_qfq_close * 1.02)
```

信号冻结字段至少包含：

- T：日期、`qfq_close`、`MA10`、`MA20`、`MA30`、未复权 `close`、换手率、`BIAS20`。
- S：日期、`qfq_close`、S 到 T 的交易日距离。
- H：日期、`qfq_high`、`H_qfq_high / S_qfq_close - 1`、H 到 T 的交易日距离。
- L：日期、`qfq_low`、`MA10`、`MA20`、H 到 L 的回撤幅度。
- `bug_price`、`entry_trigger_price`、`stop_loss_price`、`max_watch_days = 5`。

除以上条件外，信号函数不增加其他板块范围、涨停次数、价格上限、L/T 收盘关系或其他形态过滤。

## 二、买入函数

信号在 T 日收盘后加入观察池，只观察 T+1 至 T+5，共 5 个交易日。

每个观察日按以下规则处理：

1. 若观察日前复权最低价 `qfq_low <= L_low`，结构失效，当日不买入，收盘后移出观察池。
2. 若观察日价格范围覆盖 `bug_price`，即 `qfq_low <= bug_price <= qfq_high`，按 `bug_price` 买入，并移出观察池。
3. 若观察日开盘价高于 `bug_price`，且全天最低价仍高于 `bug_price`，即 `qfq_open > bug_price` 且 `qfq_low > bug_price`，说明全天在买入价上方且没有回踩，不买入，收盘后移出观察池。
4. 其余情况继续观察；T+5 结束仍未买入则移出观察池。

若同一观察日同时出现 `qfq_low <= L_low` 和价格覆盖 `bug_price`，结构失效优先，不根据未知的日内先后顺序假设能够买入。

重复信号不按 S、H、L 结构去重：

- 同一股票在观察期间再次产生信号时，使用最新 T 信号覆盖原观察项，从最新信号日重新观察 5 个交易日，并同步更新冻结的 `bug_price`、`L_low` 和 `stop_loss_price`。
- 旧观察项当日到期或失效时，只要当日收盘重新满足信号函数，最新 T 信号仍可重新建立观察项。
- 已持仓股票忽略所有新信号，不重复加入观察池，也不根据新信号修改持仓的买入价或卖出规则。

`1.0.0` 采用四仓真实交易仓位：

1. 最多同时持有 `4` 只股票，已有持仓占用对应仓位。
2. 每笔目标买入金额为买入当日总资产的四分之一：`target_amount = total_asset / 4`。
3. 实际买入金额不超过目标金额，同时受可用现金和手续费约束，并按 A 股 `100` 股整数手向下取整。
4. 同一交易日有多个候选时继续复用回测框架的随机候选顺序；达到4仓或可用现金不足后停止成交，避免按代码顺序产生固定偏差。

当日信号模块的 10 日生命周期回放不使用正式4仓上限，并继续固定每只买入100股，用于完整展示观察池和持仓池；该覆盖不改变正式回测仓位逻辑。

## 三、卖出函数

卖出遵守 A 股 T+1，买入当日不卖出。

### 1. 结构与T日价格约束收盘止损

信号日冻结止损价：

```text
stop_loss_price = max(L_low, T_qfq_close * 0.92)
```

若持仓日收盘价 `qfq_close <= stop_loss_price`，按当日前复权收盘价卖出。该规则保留 L 结构低点止损，同时确保止损线不低于 T 日收盘价的 92%。观察池在买入前仍使用 `L_low` 判断结构失效，不使用持仓止损价。

### 2. 浮盈达到 6% 后收盘走弱卖出

买入后持续记录已经确认的持仓最高价：

```text
activation_price = 买入价 * 1.06
daily_close_return = 当日收盘价 / 昨日收盘价 - 1
```

买入后的已确认最高价 `>= activation_price` 后，若 `daily_close_return <= 1.5%`，按当日前复权收盘价卖出。累计浮盈尚未达到 6% 时，不执行收盘走弱退出。

累计浮盈是否达到 6% 使用买入后已经确认的最高价判断；收盘涨幅使用当日 `qfq_close` 与昨日 `qfq_close` 计算。两项数据在当日收盘时均已确定，因此按当日收盘价卖出不依赖未知盘中顺序。

当前启用累计浮盈达到 6% 后的收盘走弱退出，不启用盘中最高价回撤退出。

## 四、核心参数

```text
MIN_UNADJUSTED_CLOSE = 10
STRATEGY_VERSION = "1.0.0"
MIN_TURNOVER_RATE = 8
MAX_TURNOVER_RATE = 12
MIN_BIAS_20 = 0.10
MIN_MA_STACK_DISTANCE = 17
HIGH_TO_T_MIN_BARS = 3
HIGH_TO_T_MAX_BARS = 10
MIN_HIGH_TO_LOW_DRAWDOWN = 0.07
L_MA20_MIN_MULTIPLE = 0.95
L_MA10_MAX_MULTIPLE = 1.02
T_CLOSE_MA10_MIN_MULTIPLE = 0.95
T_CLOSE_MA10_MAX_MULTIPLE = 1.02
BUY_T_CLOSE_CONFIRMATION_MULTIPLE = 1.02
T_CLOSE_STOP_MULTIPLE = 0.92
WATCH_MAX_DAYS = 5
PROFIT_ACTIVATION_GAIN = 0.06
ENABLE_TRAILING_EXIT = false
ENABLE_CLOSE_WEAKNESS_EXIT = true
CLOSE_WEAKNESS_MAX_DAILY_RETURN = 0.015
TRAILING_DRAWDOWN = 0.04
MAX_HOLDINGS = 4
POSITION_ASSET_FRACTION = 1 / 4
BUY_LOT_SIZE = 100
```

## 五、无未来函数约束

1. 信号选择在 T 日收盘后运行，只使用 `trade_date <= T` 的宽表记录。
2. S、H、L 及 S 收盘到 H 最高价的累计涨幅均从截至 T 日可见的历史窗口中确定，不读取 T+1 或更晚数据。
3. T+1 至 T+5 的买入判断只使用当日可观察的前复权开盘、最高和最低价，以及信号日冻结的 `L_low` 和 `bug_price`。
4. `stop_loss_price` 在 T 日收盘后由当时已知的 `L_low` 和 `T_qfq_close` 冻结；结构止损只在持仓日收盘后使用当日收盘价确认。
5. 收盘走弱退出只在累计浮盈达到 6% 后激活，使用已经确认的持仓最高价、当日收盘价和昨日收盘价，不读取未来行情。
