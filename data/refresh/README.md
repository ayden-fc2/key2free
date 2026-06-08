## Source 数据每日更新流程

后端更新入口为 `POST /api/v1/data-assets/stocks/refresh`。接口只创建 `source_update` 任务并立即返回 `task_id`，实际同步在后端后台线程执行。前端通过 `GET /api/v1/data-assets/source-update-task?task_id=...` 轮询 `meta.my_task` 的日志和状态。

`data/refresh/refresh.py` 目前不是实际执行入口；刷新逻辑以 `backend/app/services/source_refresh_service.py` 和 `backend/app/services/source_adapters.py` 为准。

### 控制表

`meta.dataset_catalog` 是每日同步的控制表，记录要从 BaoStock 维护的 source 数据资产：

| 字段 | 用途 |
| --- | --- |
| `endpoint` | BaoStock 接口名 |
| `asset_scope` | 资产范围 |
| `chunk_strategy` | 分片策略 |
| `replace_strategy` | 目标表覆盖策略 |
| `logical_key_json` | 幂等键 |
| `expected_columns_json` | 期望字段 |
| `duckdb_schema_json` | DuckDB 字段类型 |
| `validation_rules_json` | 校验规则 |
| `priority` | 每日执行顺序 |

### 当前后端实现

当前 `source_update` 已完成任务、断点续跑、分片校验和真实写入：

1. 创建 `meta.my_task`，任务类型固定为 `source_update`。
2. 限制同一时间只允许一个 `running` 状态的 `source_update`。
3. 创建 `meta.run_log`，命令为 `daily_source_refresh`。
4. 检查 `meta.api_quota_daily` 是否 blacklisted。
5. 清理过期 `meta.chunk_state.lease_*`。
6. 先更新 `source.trade_calendar` 到 `today + 7`，再计算最近确认交易日。
7. 按 `meta.dataset_catalog.priority` 遍历 enabled 数据集。
8. 先同步基础表 `trade_calendar`、`security_master`、`all_stock_snapshot`，随后重新加载 catalog 和资产范围，再执行其他数据集。
9. 每个 adapter 会先 plan 分片、校验分片覆盖、跳过已完成分片，并在请求预算不足时跳过本轮剩余数据集。
10. 支持 chunk 重试和部分 fallback 拆分：`bar_1d_raw` 失败后可按年拆，`bar_5m_raw` 失败后可按季度拆。
11. 适配器完成后写入：
   - `meta.chunk_state`
   - `meta.validation_result`
   - `meta.dataset_watermark`
   - `meta.run_log`
   - `meta.my_task.logs`

### 已接入 adapter

当前 `backend/app/services/source_adapters.py` 的 `ADAPTER_REGISTRY` 已注册以下真实 adapter，均为 `implemented=True`：

| 数据集 | 写入表 | 分片/刷新策略 |
| --- | --- | --- |
| `trade_calendar` | `source.trade_calendar` | 滚动维护 `today - 14` 到 `today + 7` 的交易日窗口 |
| `security_master` | `source.security_master` | 全量刷新证券基础资料 |
| `all_stock_snapshot` | `source.all_stock_snapshot` | 最近确认交易日的全市场快照 |
| `bar_1d_raw` | `source.bar_1d_raw` | 按资产代码拉取日频不复权 K 线；从 IPO/水位后一天到最近交易日，失败后按年 fallback |
| `bar_5m_raw` | `source.bar_5m_raw` | 按资产代码和年份拉取近 5 年 5 分钟 K 线，失败后按季度 fallback |
| `adjust_factor` | `source.adjust_factor` | 按资产代码拉取复权因子；有水位时回看 365 天 |
| `dividend` | `source.dividend` | 按资产代码、年份和 `year_type=report/operate` 拉取分红除权数据 |
| `profit` | `source.profit` | 按资产代码、年、季度拉取盈利能力数据；有水位时回看最近 8 个季度 |
| `operation` | `source.operation` | 按资产代码、年、季度拉取营运能力数据；有水位时回看最近 8 个季度 |
| `growth` | `source.growth` | 按资产代码、年、季度拉取成长能力数据；有水位时回看最近 8 个季度 |
| `balance` | `source.balance` | 按资产代码、年、季度拉取偿债能力数据；有水位时回看最近 8 个季度 |
| `cash_flow` | `source.cash_flow` | 按资产代码、年、季度拉取现金流量数据；有水位时回看最近 8 个季度 |
| `dupont` | `source.dupont` | 按资产代码、年、季度拉取杜邦指数数据；有水位时回看最近 8 个季度 |
| `performance_express` | `source.performance_express` | 按资产代码和年度日期窗口拉取业绩快报；有水位时回看 2 年 |
| `forecast` | `source.forecast` | 按资产代码和年度日期窗口拉取业绩预告；有水位时回看 2 年 |
| `deposit_rate` | `source.deposit_rate` | 小表全量刷新，时间范围 `1990-01-01` 到最近交易日 |
| `loan_rate` | `source.loan_rate` | 小表全量刷新，时间范围 `1990-01-01` 到最近交易日 |
| `reserve_ratio` | `source.reserve_ratio` | 小表全量刷新，时间范围 `1990-01-01` 到最近交易日，`year_type=1` |
| `money_supply_month` | `source.money_supply_month` | 小表全量刷新，时间范围 `1990-01` 到最近年月 |
| `money_supply_year` | `source.money_supply_year` | 小表全量刷新，时间范围 `1990` 到最近年份 |
| `industry_snapshot` | `source.industry_snapshot` | 最近确认交易日的行业分类快照 |
| `index_member_snapshot` | `source.index_member_snapshot` | 最近确认交易日的上证50、沪深300、中证500成分股快照 |

如果未来 catalog 中出现未注册 adapter，任务会报错并记录失败；如果 adapter 注册但 `implemented=False`，任务会记录跳过且不推进水位。当前注册表没有这种未实现 adapter。
