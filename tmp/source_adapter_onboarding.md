# Source 数据资产同步适配规范

本文档作为后续逐步接入剩余 19 个 source 资产的实现准则。当前稳定基线是：

- `backend/app/services/source_adapters.py`
- `backend/app/services/source_refresh_service.py`
- `backend/app/repositories/data_asset_repository.py`
- `meta.dataset_catalog`
- `meta.dataset_watermark`
- `meta.chunk_state`
- `meta.validation_result`
- `meta.run_log`

## 当前稳定流程

`SourceRefreshService` 只做编排，不直接写具体 BaoStock 字段映射：

1. 创建 `meta.run_log`。
2. 检查 `meta.api_quota_daily` blacklisted 状态。
3. 清理过期 `meta.chunk_state` lease。
4. 读取 `meta.dataset_catalog` enabled 数据集。
5. 从 `ADAPTER_REGISTRY` 找对应 adapter。
6. adapter 调 BaoStock 并返回标准 `AdapterResult`。
7. service 写 `chunk_state=running`。
8. repository 写入临时 staging。
9. 校验 staging：
   - schema
   - logical key
   - chunk scope 行数
10. 校验失败则 rollback，不替换目标 source 表，不推进水位。
11. 校验通过后事务性替换目标 source 表 scope。
12. 写 `meta.validation_result`。
13. 写 `chunk_state=success`。
14. 推进 `meta.dataset_watermark`。
15. 更新 `meta.run_log` 与 `meta.api_quota_daily`。

## Adapter 职责边界

adapter 只负责“BaoStock 返回如何变成标准 source rows”。

adapter 必须做：

- 调用一个明确的 BaoStock endpoint。
- 根据 `chunk_strategy` 和 runtime 计算本次 chunk scope。
- 将 BaoStock 原字段映射为 source 表字段。
- 做基础类型转换。
- 补齐 source 表需要的系统字段。
- 返回 `AdapterResult`。

adapter 不允许做：

- 不直接写 DuckDB。
- 不更新 `dataset_watermark`。
- 不写 `chunk_state`。
- 不写 `validation_result`。
- 不自己决定 run 成功/失败。

## AdapterResult 约定

每个 adapter 返回：

```python
AdapterResult(
    dataset_name="...",
    chunk_key="...",
    scope={...},
    rows=[...],
    watermark="YYYY-MM-DD",
    request_count=1,
)
```

字段含义：

- `dataset_name`：必须等于 `meta.dataset_catalog.dataset_name`。
- `chunk_key`：分片唯一键，应稳定、可重跑。
- `scope`：必须能驱动 `replace_strategy` 删除目标范围。
- `rows`：字段必须与 `expected_columns_json` 一致。
- `watermark`：本次 adapter 候选水位；只有校验成功后由 service 推进。
- `request_count`：本 adapter 对 BaoStock 的请求数。

## 字段转换规范

统一使用 `source_adapters.py` 里的转换工具，后续可扩展：

- `empty_to_none`
- `parse_date`
- `parse_int`

后续需要新增：

- `parse_float`
- `parse_datetime`
- `parse_year_month_date`
- `parse_baostock_bar_time`
- `derive_fiscal_year`
- `derive_fiscal_quarter`

约定：

- 空字符串、空白字符串统一转 `None`。
- BaoStock 中的异常短横线、中文破折号等应在数值转换前归一为空或负号。
- 日期字段入库为 `date`。
- 分钟行情 `time` 入库同时保留 `time_raw`，并派生 `bar_time`。
- 有 `ingest_run_id` 的表必须补当前 `run_id`。
- 有 `loaded_at` 的表必须补当前加载时间。

## 新增 Adapter 步骤

每接入一个 source 资产，按以下步骤执行：

1. 打开对应 `data/help/*.md`，确认 BaoStock 返回字段。
2. 对照 `meta.dataset_catalog.expected_columns_json` 和真实 `source.*` 表字段。
3. 在 `source_adapters.py` 将对应 `NotImplementedSourceAdapter` 替换为真实 adapter 类。
4. adapter 内部只实现：
   - chunk scope 计算
   - BaoStock 请求
   - 字段映射
   - 类型转换
   - 系统字段补齐
   - `AdapterResult` 返回
5. 如该表尚未在 `SOURCE_TABLE_COLUMNS` 中登记，先补全字段顺序。
6. 如该表使用新的 `replace_strategy`，在 repository 补 `_delete_source_scope` 分支。
7. 如该表需要特殊 scope 行数校验，在 `_validate_dataset_relation` 补 dataset 分支。
8. 用 fake BaoStockClient + 临时 DuckDB 副本做无网络验证。
9. 再做真实小范围 smoke。
10. 最后再允许纳入每日调度。

## 剩余资产接入顺序

按 `meta.dataset_catalog.priority` 逐步推进。

| 顺序 | dataset | endpoint | help 文档 | 关键点 |
| ---: | --- | --- | --- | --- |
| 1 | `bar_1d_raw` | `query_history_k_data_plus` | `获取历史A股K线数据.md` | 日线字段、估值字段、指数/股票/ETF 资产范围、`trade_year`、`ingest_run_id`、`loaded_at` |
| 2 | `bar_5m_raw` | `query_history_k_data_plus` | `获取历史A股K线数据.md` | 分钟线不支持指数、`time_raw`、`bar_time`、近 5 年窗口 |
| 3 | `adjust_factor` | `query_adjust_factor` | `复权因子.md` | 复权因子窗口应回看，服务 mart 复权视图 |
| 4 | `dividend` | `query_dividend_data` | `除权除息信息.md` | `query_year`、`query_year_type`、按年回扫，分红日期可能为空 |
| 5 | `profit` | `query_profit_data` | `季频盈利能力.md` | 年/季 chunk，补 `fiscal_year/fiscal_quarter` |
| 6 | `operation` | `query_operation_data` | `季频营运能力.md` | 年/季 chunk，字段多为空要允许 |
| 7 | `growth` | `query_growth_data` | `季频成长能力.md` | 年/季 chunk，YOY 字段大小写映射 |
| 8 | `balance` | `query_balance_data` | `季频偿债能力.md` | 年/季 chunk，YOYLiability 映射 |
| 9 | `cash_flow` | `query_cash_flow_data` | `季频现金流量.md` | 年/季 chunk，CFO 字段映射 |
| 10 | `dupont` | `query_dupont_data` | `季频杜邦指数.md` | 年/季 chunk，dupont 字段映射 |
| 11 | `performance_express` | `query_performance_express_report` | `季频公司业绩快报.md` | `performanceExp*` 字段映射，按披露日期窗口回扫 |
| 12 | `forecast` | `query_forecast_report` | `季频公司业绩预告.md` | BaoStock 文档拼写 `Forcast`，source 也保持 `forcast` |
| 13 | `deposit_rate` | `query_deposit_rate_data` | `存款利率.md` | 小表全量重拉，字段映射较直接 |
| 14 | `loan_rate` | `query_loan_rate_data` | `贷款利率.md` | 小表全量重拉，mortgate 拼写保持 source 现状 |
| 15 | `reserve_ratio` | `query_required_reserve_ratio_data` | `存款准备金率.md` | 水位建议按 `effective_date` 或 catalog 当前定义一致处理 |
| 16 | `money_supply_month` | `query_money_supply_data_month` | `货币供应量.md` | `statYear/statMonth` 派生 `stat_date=YYYY-MM-01` |
| 17 | `money_supply_year` | `query_money_supply_data_year` | `货币供应量(年底余额).md` | `statYear` 派生 `stat_date=YYYY-12-31` |
| 18 | `industry_snapshot` | `query_stock_industry` | `行业分类.md` | 单日快照，`industryClassification` 映射 |
| 19 | `index_member_snapshot` | `query_index_members` | `上证50成分股.md`、`沪深300成分股.md`、`中证500成分股.md` | 需要按 `index_code` 分发具体接口，再统一落表 |

## replace_strategy 接入注意

已稳定：

- `full_table`
- `date_window`
- `single_date`

后续需要补：

- `code_or_code_year`
- `code_year_or_quarter`
- `code_date_window`
- `code_year_type`
- `code_year_quarter`
- `index_code_date`

新增策略必须满足：

- scope 字段完整。
- delete 条件只覆盖本 chunk。
- staging 校验失败不得改目标表。
- 同一 chunk 重跑幂等。

## chunk_strategy 接入注意

后续不要在 service 里硬编码 chunk 生成。优先让 adapter 或独立 planner 负责：

- `code_full_then_fallback_year`
- `code_year_then_fallback_quarter`
- `code_full`
- `code_year_type`
- `dataset_code_year_quarter`
- `code_yearly_date_window`
- `small_full_table`
- `snapshot_date`
- `index_code_date`

第一阶段可以在 adapter 内实现最小可用 chunk；当重复变多时，再抽 `ChunkPlanner`。

## 水位推进规则

通用原则：

- 单 chunk 校验通过后才能返回 watermark candidate。
- dataset 级水位只能在必要 chunk 都成功后推进。
- 当前三张表是单 chunk，所以可直接推进。
- 多 code、多季度、多年份数据集接入时，不能每个 chunk 立即推进到最终水位；需要 dataset-level 汇总判断。

各类建议：

- 行情类：按目标交易日推进。
- 分钟类：按所有支持分钟线资产完成后的最大 `trade_date` 推进。
- 财务类：按 `stat_date`，但每日回扫最近 4 到 8 个季度。
- 公告类：按 `pub_date` 或 update date，窗口回扫至少 1 到 2 年。
- 宏观小表：全量重拉后按表内最大日期推进。
- 快照类：按快照 `update_date` 推进。

## 验证要求

每个新增 adapter 至少做两类验证：

1. fake client + 临时 DuckDB 副本：
   - 成功写入
   - staging 校验失败不污染目标表
   - `chunk_state.attempts` 语义正常
   - 水位只在成功后推进
2. 真实 BaoStock 小范围 smoke：
   - 控制请求量
   - 只跑少量 code/date
   - 确认返回字段名与 help 文档一致
   - 确认空值和类型转换正确

## 禁止事项

- 不要在 `SourceRefreshService.run` 里继续堆具体字段映射。
- 不要绕过 staging 直接 delete/insert 目标表。
- 不要校验失败后推进水位。
- 不要为未完成的多 chunk dataset 做乐观水位推进。
- 不要把 mart 视图作为 BaoStock 同步目标。
- 不要为了接一个 dataset 改坏已有三张表的稳定路径。
