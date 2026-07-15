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
- 策略注册了 `signal_index_codes` 时，额外提供这些指数截至 T 日的日线历史窗口。
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

成交费用由回测框架统一计算，买入和卖出双边费率均为 `0.05%`，每笔成交最低手续费 `5` 元。费用会从现金中扣除，并记录在买入单、卖出单的 `fee` 字段。

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

信号阶段还支持可选的指数历史。策略必须通过注册项 `signal_index_codes` 显式声明需要的指数，框架会从白名单指数资产中加载截至批次末日的全部历史，并在 `SignalDataView` 访问时按当前 T 日裁剪为 `trade_date <= T`。可用入口包括：

- `view.index_daily_history(ts_code, columns=None, window=None)`：返回指定指数截至 T 日的日线历史，来自 `tushare.index_daily`。
- `view.index_dailybasic_history(ts_code, columns=None, window=None)`：返回指定指数截至 T 日的每日指标历史，来自 `tushare.index_dailybasic`。
- `view.index_history(ts_code, columns=None, window=None)`：兼容旧策略的日线别名，等同于 `index_daily_history`。

`window=None` 时指数视图返回 T 日及以前的全部可用历史；传入正数时才截取末尾窗口。若某个指数未在对应白名单资产中，或尚无对应历史数据，相关视图会返回空表，策略应保守处理。

信号系统和回测系统共享同一条信号预计算路径。回测在撮合前调用 `SignalService.get_signals_for_dates_by_stock()` 得到原始信号；启用交易时钟的策略默认只在对应周期末产生信号，也可以通过注册项指定周期内第 N 个开市日产生信号，非信号日返回空信号。指数环境过滤会同时作用于单日信号查询和回测信号池；不会在买入或卖出阶段重新查询指数，也不会把 T 日之后的指数表现带入交易判断。

## 宽表重建备份

`tushare.stock_daily_technical` 重建耗时较长。重建逻辑在清空旧宽表前，会先把当前宽表导出到 `data/backups/stock_daily_technical_before_rebuild_*.parquet`。如果重建中途失败，可以先停后端释放 DuckDB 文件锁，再用 DuckDB 执行：

```sql
delete from tushare.stock_daily_technical;
insert into tushare.stock_daily_technical
select * from read_parquet('data/backups/<backup-file>.parquet');
```

手动恢复后再重启后端即可继续信号/回测流程。

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
- `signal_index_codes`：信号阶段需要的指数代码列表，例如中证500为 `000905.SH`。未声明时不会加载指数数据；只会加载后端白名单中存在的指数日线和每日指标。
- `trading_clock_period`：可选交易时钟周期；当前支持 `"W"` 周频。启用后，框架按 `tushare.trade_cal` 构造交易时钟；回测撮合阶段会在 `context.params.trading_clock` 传入本周期交易日、前后开市日窗口、周期起止、周期内第几个开市日 `period_day_index`、周期内开市日总数 `period_day_count`、`is_period_start` 和 `is_period_end`。兼容字段 `is_rebalance_period_start`、`is_signal_period_end` 仍会同步传入。
- `signal_period_day`：启用交易时钟时可选，指定周期内第几个开市日收盘后调用 `select_signals`；未设置时默认使用周期最后一个开市日。
- `rebalance_period_day`：启用交易时钟时可选，指定周期内第几个开市日开盘执行策略调仓；未设置时默认使用周期第一个开市日。
- `required_columns`：买卖阶段 `history_by_code` 额外需要的宽表字段，不影响信号阶段字段。买卖阶段固定只提供截至 T-1 的最近 10 个交易日窗口。
- `code_filter`：框架加载数据后用于过滤股票代码范围。

默认信号字段来自 `tushare.stock_daily_technical` 的日频宽表，不包含分钟线明细或分钟线派生字段。宽表内置的趋势/波动指标包括 MA、ER、BOLL、MACD、RSI、ROC、KDJ、ATR，滚动成交量均值 `avg_volume_5/10/20`、滚动成交额均值 `avg_amount_5/10/20/30`，以及基于前复权高低价滚动回归斜率的 `rsrs_5`、`rsrs_10`、`rsrs_20`、`rsrs_30`。所有滚动指标只使用当前 T 日及以前的数据，窗口不足时保持空值。策略确实需要分钟线或分钟线派生字段时，应由策略自己查询分钟线数据，不应假设 `tushare.stock_daily_technical` 提供 `min5_close`。

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
- `index_daily_history(ts_code, columns=None, window=None)`：返回指定指数截至 T 日的日线历史。只有策略在注册中声明且该指数在日线白名单中时才会有数据。
- `index_dailybasic_history(ts_code, columns=None, window=None)`：返回指定指数截至 T 日的每日指标历史。只有策略在注册中声明且该指数在每日指标白名单中时才会有数据。
- `index_history(ts_code, columns=None, window=None)`：旧版日线别名，等同于 `index_daily_history`。

可用数据：

- 可以使用 T 日完整日频宽表，因为该阶段模拟收盘后选信号。
- 可以使用已注册指数截至 T 日的日线数据和每日指标数据做市场环境过滤、择时开关或仓位信号。
- 不默认包含分钟线字段；不得假设 `min5_close` 或分钟线明细存在。

输出：`list[dict]`，每个元素至少包含：

- `code`：股票代码。
- `code_name`：股票名称，可为空。
- `trade_date`：信号日期，通常为 T 日。
- `universe`：用于展示和记录的选股上下文。
- `signal`：策略信号载荷，建议包含 `triggered`, `signal_close`, `entry_trigger_price`, `max_watch_days`, `sell_rules`, `display`, `extras`。

### 信号面板兼容输出

前端信号面板支持在结束交易日前向前选择最近 N 个开市日运行策略信号函数；默认 `lookback_trade_days = 1`，即只看选中交易日。后端会按交易日列表逐日调用同一套 `select_signals`，合并返回每个信号自己的 `trade_date`，不改变回测预计算路径。

为方便实盘操作，新策略应尽量在 `signal` 中维护以下字段：

- `signal_close`：信号日 T 的参考收盘价。
- `entry_trigger_price`：买入触发价；如果不是固定价格，可以写中文或枚举字符串，例如 `next_rebalance_open`。
- `max_watch_days`：最长观察交易日数；组合调仓类策略可填 `1` 或策略自身含义。
- `sell_rules`：卖出触发规则列表。每条规则建议包含 `name`, `rule_type`, `timing`, `trigger_price`, `sell_price`, `description`。`rule_type` 可用 `static` 或 `dynamic` 区分静态价位和依赖持仓过程的规则。
- `display`：给前端直接展示的中文操作计划，建议包含 `title`, `signal_date`, `entry`, `watch`, `sell`。
- `extras`：用于审计和分桶分析的结构化字段，仍保持英文 key，避免影响历史统计脚本。

前端只展示策略返回的中文说明，不在页面硬编码具体策略规则。策略维护者修改买入、观察或卖出逻辑时，应同步更新 `display` 和 `sell_rules`，确保信号面板、回测记录和策略文档一致。

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
- `market.index_history`

`market.index_history` 是交易阶段通用指数宽表，默认合并后端白名单指数最近 200 个可见交易日的日线数据。列名格式为 `<ts_code>__<field>`，例如 `000905.SH__close`、`000905.SH__open`。买入和卖出阶段在交易日 T 只能看到 `< T` 的指数历史，不包含 T 日收盘，也不包含 T+1 或更晚数据。

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

## 小市值低价轮动策略

当前 `small_float_value` 策略不启用中证500市场环境过滤、指数 MA20、Top500 牛熊指标、金叉死叉或 20 日低点过滤；保留周频交易时钟、top6 目标池和 7/7 日常卖出：

- 每个交易周最后一个开市日 T 收盘后使用截至 T 日的宽表横截面计算目标池，并刷新观望池；周五遇节假日时自动使用该交易周实际最后一个开市日。
- 下一交易周第一个开市日开盘执行买入和周频调仓；周一遇节假日时自动顺延到该交易周实际第一个开市日。
- 基础约束为普通主板非 ST、上市满 250 日、EPS 非负、价格和流通市值有效。
- 在基础池中使用不复权收盘价 `close` 筛选全市场最低价 10% 股票，再按 `circ_mv` 从小到大排序，选取第 1-6 名作为目标池。
- 日常卖出规则仍每天执行：上一交易日涨幅不低于 7%，T 日收盘涨幅低于 7% 时按 T 日收盘价卖出。

该策略当前不声明 `signal_index_codes`，因此信号阶段不会加载指数日线或指数每日指标。策略启用周频交易时钟，但不指定 `signal_period_day` 或 `rebalance_period_day`，因此使用默认节奏：周期最后一个开市日收盘后出信号，下一周期第一个开市日开盘调仓。整个流程只使用截至信号日 T 的宽表信号数据、买卖阶段 T-1 股票历史宽表和 T 日交易可观察价格；除公开交易日历用于定位周频周期外，不读取 T+1 或更晚的股票、指数、财务或宽表数据。

正式 `small_float_value` 已移除压测探针参数，信号阶段只加载选股必要字段，`signal_history_window = 0`，只使用信号日 T 的横截面；不再把 `qfq_close`、`total_mv`、`buy_history_probe` 写入信号载荷。

后端只维护当前库中日线和每日指标都能覆盖 2014 年起回测窗口的核心指数：上证指数 `000001.SH`、深证成指 `399001.SZ`、创业板指 `399006.SZ`、中证500 `000905.SH`。北证50、科创综指、中证2000、巨潮小盘等不同时具备 2014 年起日线和每日指标覆盖的指数不进入自动维护池，避免长周期回测因指数历史不足而产生大段空信号。新增维护指数时，刷新链路会检测维护池缺失代码，并从其可用起点补齐指数日线和每日指标，而不是只按全局水位增量刷新。

Tushare 数据资产的每日 `02:30` 自动刷新已迁移到 `nas/data_asset_service`；主后端不再启动本地定时器，但保留手动刷新接口。NAS 自动任务会同步更新 `tushare.stk_mins_5min` 分钟线水位；只有手动调用刷新接口并显式传入 `skip_stk_mins_5min=true` 时才跳过分钟线。日频技术宽表 `tushare.stock_daily_technical` 不依赖分钟线水位。

最高原则：每个策略的信号函数、买入函数、卖出函数都只能看到其交易时点应当可见的信息。T 日完整宽表只允许在收盘后选信号阶段使用；买卖阶段只能使用 T-1 历史宽表和 T 日交易可观察价格。交易日历属于公开可预知信息，框架允许用 T 前后一段开市日排列定位交易周期开始/结束；除此之外，股票、指数、财务、宽表指标都不得读取 T+1 或更晚数据。
