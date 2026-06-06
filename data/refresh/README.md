## Source 数据每日更新流程

后端更新入口为 `POST /api/v1/data-assets/stocks/refresh`。接口只创建 `source_update` 任务并立即返回 `task_id`，实际同步在后端后台线程执行。前端通过 `GET /api/v1/data-assets/source-update-task?task_id=...` 轮询 `meta.my_task` 的日志和状态。

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

当前 `source_update` 已完成任务和运行框架：

1. 创建 `meta.my_task`，任务类型固定为 `source_update`。
2. 限制同一时间只允许一个 `running` 状态的 `source_update`。
3. 创建 `meta.run_log`，命令为 `daily_source_refresh`。
4. 检查 `meta.api_quota_daily` 是否 blacklisted。
5. 清理过期 `meta.chunk_state.lease_*`。
6. 先更新 `source.trade_calendar` 到 `today + 7`，再计算最近确认交易日。
7. 按 `meta.dataset_catalog.priority` 遍历 enabled 数据集。
8. 已接入真实写入的轻量适配器：
   - `source.trade_calendar`
   - `source.security_master`
   - `source.all_stock_snapshot`
9. 适配器完成后写入：
   - `meta.chunk_state`
   - `meta.validation_result`
   - `meta.dataset_watermark`
   - `meta.run_log`
   - `meta.my_task.logs`

### 后续适配器

以下数据集已有 catalog 和任务框架，但还需要逐个补充 chunk adapter：

| 数据集 | 分片策略 |
| --- | --- |
| `bar_1d_raw` | `code_full_then_fallback_year` |
| `bar_5m_raw` | `code_year_then_fallback_quarter` |
| `adjust_factor` | `code_full` |
| `dividend` | `code_year_type` |
| `profit` / `operation` / `growth` / `balance` / `cash_flow` / `dupont` | `dataset_code_year_quarter` |
| `performance_express` / `forecast` | `code_yearly_date_window` |
| `deposit_rate` / `loan_rate` / `reserve_ratio` / `money_supply_month` / `money_supply_year` | `small_full_table` |
| `industry_snapshot` | `snapshot_date` |
| `index_member_snapshot` | `index_code_date` |

未实现适配器的数据集在当前任务中只写日志并跳过，不推进水位。
