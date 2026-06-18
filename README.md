# herome-a

## 回测系统目标架构

项目的通用回测系统按阶段化生命周期运行。目标是让每个策略单独维护自己的页面、信号函数、买入操作和卖出操作；回测框架只负责通用能力：数据装载、交易日推进、资金和仓位维护、订单记录、快照记录，以及把每天的策略参数和市场视图传给具体策略。

策略只负责五件事：信号判断、观望池处理、买入判断、卖出判断、策略参数解释。

## 生命周期

### 1. 信号预计算

指定交易日或回测日期内，每个 T 日收盘后执行一次。

输入给策略：

- 全市场股票截至 T 日的宽表数据。
- 默认每只股票最多包含最近 `signal_history_window` 条记录。
- 策略通过 `SignalDataView` 选择自己需要的视图：组合排序使用 T 日横截面，单股形态使用个股历史窗口。

策略输出：

- T 日爆出信号的股票列表。
- 信号会进入信号系统或回测系统，供后续观望池和买入逻辑使用。

### 2. 逐日回测

回测系统每天维护四类状态：观望池、持仓池、资金量、交易记录。

每天按顺序执行：

1. 卖出
2. 买入
3. 收盘后更新观望池

### 3. 卖出阶段

调用时点：T 日交易阶段，买入前。

回测系统输入给策略：

- 当前持仓池，持仓股票至少已经持有一天，符合 T+1 卖出约束。
- 持仓份额、持仓时间、资金状态、当前日期、过去交易记录。
- `history_by_code`：截至 T-1 的最近 10 个交易日宽表窗口。
- `today_bars`：T 日交易可观察价格。

策略输出：

- 持仓池中哪些票要卖出。
- 每只票卖出多少手、卖出价格和卖出原因。

约束：

- 开盘卖出只能使用 T 日开盘相关字段。
- 盘中条件可使用 T 日 high/low/vol 等交易中可观察字段。
- 不得使用 T 日 MA、ATR、财务指标等收盘后才能确认的宽表指标。
- 框架会阻止同日买入后同日卖出，保证 T+1。

### 4. 买入阶段

调用时点：T 日卖出执行后。

回测系统输入给策略：

- 卖出后的资金池，允许乐观近似使用当日卖出释放的资金。
- 当前观望池、信号池、持仓池、交易记录。
- `history_by_code`：截至 T-1 的最近 10 个交易日宽表窗口。
- `today_bars`：T 日交易可观察价格。

策略输出：

- 观望池中哪些票要买入。
- 哪些票继续保留，哪些票退出观望。
- 买入价格、买入数量和对应信号载荷。

约束：

- 开盘买入只能使用 T 日开盘相关字段。
- 盘中触发可以买入时，只能使用 T 日 high/low/vol 等交易中可观察字段。
- 不得使用 T 日完整宽表指标进行买入判断。

### 5. 收盘后更新观望池

调用时点：T 日买卖流程完成后。

回测系统输入给策略：

- 当日 `select_signals` 输出的原始信号。
- 收盘后的资金、持仓、观望池和交易记录。

策略输出：

- 新增到观望池的信号。
- 继续保留的代码集合。
- 从观望池移除的代码集合。

## 数据视图

为避免未来函数，回测系统区分两类数据视图：

1. `history_by_code`：截至 T-1 的最近 10 个交易日宽表数据。
2. `today_bars`：T 日只包含交易中可观察价格字段。

只有在“收盘后选信号”阶段，策略才能使用 T 日完整宽表指标。

`today_bars` 字段顺序：

```text
(qfq_open, qfq_high, qfq_low, qfq_close, vol, pct_chg, prev_ma_10, qfq_pre_close)
```

注意：`today_bars` 同时包含开盘、最高、最低、收盘等价格。策略必须按自己的交易时点自律使用字段：开盘交易只看开盘相关字段，盘中触发只看盘中可观察字段，收盘动作才可看收盘字段。

## 策略注册

每个策略通过 `StrategyRegistration` 接入：

- `name`：策略名称。
- `lifecycle`：策略生命周期实现。
- `signal_history_window`：信号函数可见的每股历史行数，默认 `200`。组合轮动策略也可以配置为 `200`，再通过 `view.cross_section()` 使用 T 日横截面，通过 `view.iter_stock_history()` 使用个股历史。
- `signal_required_columns`：信号阶段需要的字段；`None` 表示使用默认日频宽表字段，非空时只查询声明字段，并自动补充 `trade_date` 和 `code`。
- `required_columns`：买卖阶段 `history_by_code` 额外需要的宽表字段，不影响信号阶段字段。买卖阶段固定只提供截至 T-1 的最近 10 个交易日窗口。
- `code_filter`：框架加载数据后用于过滤股票代码范围。

默认信号字段来自 `tushare.stock_daily_technical` 的日频宽表，不默认传入分钟线明细或分钟线派生字段。默认排除 `min5_close`。策略确实需要分钟线或分钟线派生字段时，应在策略注册中显式声明字段，或者由策略自己查询分钟线数据。

注意：`SignalDataView` 在按 `columns` 取字段时会自动忽略不存在的字段，不会因为缺字段立刻报错。策略开发时必须确认 `signal_required_columns` 已声明所有需要字段，否则可能得到缺列后的结果、空结果或 NaN，导致信号异常但不一定显式失败。

## 策略函数接口

### `select_signals`

调用时点：T 日收盘后。

输入：

- `trade_date`：当前 T 日。
- `view`：`SignalDataView`。所有策略统一使用该入口，框架保证只包含截至 T 日可见的数据。

`SignalDataView` 提供：

- `cross_section(columns=None)`：T 日全市场横截面，适合小市值、低价、市值排序等组合选股。
- `history_by_stock(columns=None, window=200, codes=None)`：按股票返回截至 T 日的历史窗口，包含 T 日。
- `iter_stock_history(columns=None, window=200, codes=None)`：逐股迭代历史窗口，适合全市场形态扫描，避免策略自己写 SQL。
- `to_frame(columns=None, window=200, codes=None)`：必要时返回 DataFrame；优先使用上面的结构化视图方法。

可用数据：

- 可以使用 T 日完整日频宽表，因为该阶段模拟收盘后选信号。
- 不默认包含分钟线字段；不得假设 `min5_close` 或分钟线明细存在。

输出：`list[dict]`，每个元素至少包含：

- `code`：股票代码。
- `code_name`：股票名称，可为空。
- `trade_date`：信号日期，通常为 T 日。
- `universe`：用于展示和记录的选股上下文。
- `signal`：策略信号载荷，建议包含 `triggered`, `signal_close`, `max_watch_days`, `extras`。

### `decide_sells`

调用时点：T 日交易阶段，买入前。

输入：

- `context.trade_date`, `context.trade_index`
- `context.cash`, `context.total_asset`
- `context.holdings`
- `context.watch_pool`
- `context.trade_records`
- `market.today_bars`
- `market.previous_bars`
- `market.history_by_code`

输出：`list[StrategySellDecision]`，字段为：

- `code`
- `price`
- `quantity`
- `reason`

### `decide_buys`

调用时点：T 日卖出执行后。

输入字段同 `decide_sells`，但 `context.cash` 已包含当日卖出后的可用资金近似。

输出：`list[StrategyBuyDecision]`，字段为：

- `code`
- `code_name`
- `price`
- `quantity`
- `signal`

### `update_watch_pool`

调用时点：T 日收盘后，买卖流程完成后。

输入：

- `context`：当日收盘后的资金、持仓、观望池和交易记录。
- `raw_signals`：当日 `select_signals` 输出的原始信号列表。

输出：`StrategyWatchDecision`：

- `add`：加入观望池的信号列表。
- `keep`：继续保留的代码集合；为空时由 `remove` 控制。
- `remove`：从观望池移除的代码集合。

## 策略接入清单

新策略建议独立维护在：

```text
backend/strategies/<strategy_name>/strategy.py
```

最小接入内容：

- 实现一个 `StrategyLifecycle`。
- 导出 `<strategy_name>_lifecycle`。
- 按需导出 `REQUIRED_COLUMNS` 和 `code_filter`。
- 在 `backend/app/services/strategy_registry.py` 中注册。
- 明确声明 `signal_required_columns`，并在策略内部确认关键字段存在，避免字段缺失被静默忽略后产生错误信号。

单股形态策略通常通过 `view.iter_stock_history(window=200)` 在每只股票的历史窗口里寻找结构。组合轮动策略也可以配置 `signal_history_window=200`，通过 `view.cross_section()` 在 T 日全市场横截面里排序和选股，同时仍可读取个股历史窗口。

最高原则：每个策略的信号函数、买入函数、卖出函数都只能看到其交易时点应当可见的信息。T 日完整宽表只允许在收盘后选信号阶段使用；买卖阶段只能使用 T-1 历史宽表和 T 日交易可观察价格。
