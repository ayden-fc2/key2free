---
title: Meta 数据资产
tags:
  - data-asset/meta
---

# Meta 数据资产

数据维护、运行状态、任务、水位、校验和治理元数据。

> [!info]
> 本文档由 `data/data.duckdb` 的真实结构生成。字段、类型和示例以当前 DuckDB 为准。

## 对象索引

- [[meta#meta.api_quota_daily|meta.api_quota_daily]] `BASE TABLE`
- [[meta#meta.chunk_state|meta.chunk_state]] `BASE TABLE`
- [[meta#meta.dataset_catalog|meta.dataset_catalog]] `BASE TABLE`
- [[meta#meta.dataset_watermark|meta.dataset_watermark]] `BASE TABLE`
- [[meta#meta.my_task|meta.my_task]] `BASE TABLE`
- [[meta#meta.repair_manifest|meta.repair_manifest]] `BASE TABLE`
- [[meta#meta.run_log|meta.run_log]] `BASE TABLE`
- [[meta#meta.schema_snapshot|meta.schema_snapshot]] `BASE TABLE`
- [[meta#meta.security_capability|meta.security_capability]] `BASE TABLE`
- [[meta#meta.validation_result|meta.validation_result]] `BASE TABLE`

## meta.api_quota_daily

- 类型：`BASE TABLE`
- 用途：BaoStock 每日调用额度与限流状态表。
- 行数：19

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `quota_date` | `DATE` | `YES` | `2026-03-25` |
| `quota_channel` | `VARCHAR` | `YES` | `direct` |
| `request_count` | `BIGINT` | `YES` | `8` |
| `retry_count` | `BIGINT` | `YES` | `0` |
| `login_count` | `BIGINT` | `YES` | `1` |
| `blacklisted` | `SMALLINT` | `YES` | `0` |
| `soft_stop_at` | `TIMESTAMP` | `YES` | `` |
| `hard_stop_at` | `TIMESTAMP` | `YES` | `` |
| `last_run_id` | `BIGINT` | `YES` | `5` |

## meta.chunk_state

- 类型：`BASE TABLE`
- 用途：数据同步分片状态表。
- 行数：1108537

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `dataset_name` | `VARCHAR` | `YES` | `security_master` |
| `chunk_key` | `VARCHAR` | `YES` | `smoke_full` |
| `scope_json` | `VARCHAR` | `YES` | `{"mode":"smoke"}` |
| `status` | `VARCHAR` | `YES` | `success` |
| `attempts` | `SMALLINT` | `YES` | `1` |
| `lease_run_id` | `BIGINT` | `YES` | `` |
| `lease_expires_at` | `TIMESTAMP` | `YES` | `` |
| `last_error_code` | `VARCHAR` | `YES` | `` |
| `last_error_msg` | `VARCHAR` | `YES` | `` |
| `row_count` | `BIGINT` | `YES` | `8657` |
| `checksum` | `VARCHAR` | `YES` | `cf5adb017bab810a7b67c46670c941a78c73839a` |
| `last_success_at` | `TIMESTAMP` | `YES` | `2026-03-25 17:29:55.060781` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-03-25 17:29:55.060781` |
| `lease_token` | `VARCHAR` | `YES` | `` |

## meta.dataset_catalog

- 类型：`BASE TABLE`
- 用途：source 数据集维护目录表。
- 行数：22

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `dataset_name` | `VARCHAR` | `YES` | `security_master` |
| `endpoint` | `VARCHAR` | `YES` | `query_stock_basic` |
| `tier` | `VARCHAR` | `YES` | `core` |
| `enabled` | `SMALLINT` | `YES` | `1` |
| `asset_scope` | `VARCHAR` | `YES` | `all` |
| `chunk_strategy` | `VARCHAR` | `YES` | `table_once` |
| `replace_strategy` | `VARCHAR` | `YES` | `full_table` |
| `logical_key_json` | `VARCHAR` | `YES` | `["code"]` |
| `expected_columns_json` | `VARCHAR` | `YES` | `["code","code_name","ipo_date","out_date","security_type","list_status","first_seen_date","last_seen_date","updated_at"]` |
| `duckdb_schema_json` | `VARCHAR` | `YES` | `{"code": "VARCHAR", "code_name": "VARCHAR", "first_seen_date": "DATE", "ipo_date": "DATE", "last_seen_date": "DATE", "list_status": "SMALLINT", "out_date": "DATE", "security_type":` |
| `validation_rules_json` | `VARCHAR` | `YES` | `["schema","logical_key"]` |
| `priority` | `SMALLINT` | `YES` | `10` |

## meta.dataset_watermark

- 类型：`BASE TABLE`
- 用途：source 数据集稳定同步水位表。
- 行数：21

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `dataset_name` | `VARCHAR` | `YES` | `trade_calendar` |
| `asset_scope` | `VARCHAR` | `YES` | `cn` |
| `watermark_value` | `VARCHAR` | `YES` | `2026-05-14` |
| `repair_backfill_from` | `VARCHAR` | `YES` | `` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-05-14 16:25:30.967831` |

## meta.my_task

- 类型：`BASE TABLE`
- 用途：前端轮询的本地任务状态和日志表。
- 行数：0

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `id` | `BIGINT` | `YES` | `` |
| `type` | `VARCHAR` | `YES` | `` |
| `logs` | `VARCHAR` | `YES` | `` |
| `status` | `VARCHAR` | `YES` | `` |

## meta.repair_manifest

- 类型：`BASE TABLE`
- 用途：数据修复和回补清单表。
- 行数：0

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `repair_id` | `VARCHAR` | `YES` | `` |
| `dataset_name` | `VARCHAR` | `YES` | `` |
| `scope_json` | `VARCHAR` | `YES` | `` |
| `reason` | `VARCHAR` | `YES` | `` |
| `source_doc_hash` | `VARCHAR` | `YES` | `` |
| `status` | `VARCHAR` | `YES` | `` |
| `created_at` | `TIMESTAMP` | `YES` | `` |
| `closed_at` | `TIMESTAMP` | `YES` | `` |

## meta.run_log

- 类型：`BASE TABLE`
- 用途：数据同步或校验任务运行日志表。
- 行数：63

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `run_id` | `BIGINT` | `YES` | `1` |
| `command` | `VARCHAR` | `YES` | `validate run` |
| `tier` | `VARCHAR` | `YES` | `all` |
| `started_at` | `TIMESTAMP` | `YES` | `2026-03-25 17:13:00.981185` |
| `ended_at` | `TIMESTAMP` | `YES` | `2026-03-25 17:18:11.066203` |
| `status` | `VARCHAR` | `YES` | `aborted` |
| `exit_reason` | `VARCHAR` | `YES` | `stale_process_recovered` |
| `request_count` | `BIGINT` | `YES` | `0` |
| `retry_count` | `BIGINT` | `YES` | `0` |
| `login_count` | `BIGINT` | `YES` | `0` |
| `chunk_success` | `BIGINT` | `YES` | `0` |
| `chunk_failed` | `BIGINT` | `YES` | `0` |
| `blacklisted` | `SMALLINT` | `YES` | `0` |
| `error_summary` | `VARCHAR` | `YES` | `` |

## meta.schema_snapshot

- 类型：`BASE TABLE`
- 用途：接口或表结构快照表。
- 行数：1804

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `dataset_name` | `VARCHAR` | `YES` | `security_master` |
| `endpoint` | `VARCHAR` | `YES` | `query_stock_basic` |
| `doc_file` | `VARCHAR` | `YES` | `G:\data\baostock_db\help\证券基本资料：query_stock_basic().md` |
| `doc_hash` | `VARCHAR` | `YES` | `1be8652df16c8302b7ce80c3a5773de2112a7983` |
| `fields_json` | `VARCHAR` | `YES` | `["code","code_name","ipoDate","outDate","type","status"]` |
| `captured_at` | `TIMESTAMP` | `YES` | `2026-03-25 17:12:26.801767` |

## meta.security_capability

- 类型：`BASE TABLE`
- 用途：证券类型对数据集和频率的支持能力表。
- 行数：9

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `security_type` | `SMALLINT` | `YES` | `2` |
| `dataset_name` | `VARCHAR` | `YES` | `bar_5m_raw` |
| `frequency` | `VARCHAR` | `YES` | `5m` |
| `supported` | `SMALLINT` | `YES` | `0` |
| `supported_from` | `DATE` | `YES` | `` |
| `note` | `VARCHAR` | `YES` | `Indices do not support minute bars in BaoStock.` |

## meta.validation_result

- 类型：`BASE TABLE`
- 用途：数据校验结果表。
- 行数：316

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `run_id` | `BIGINT` | `YES` | `1` |
| `dataset_name` | `VARCHAR` | `YES` | `security_master` |
| `scope_json` | `VARCHAR` | `YES` | `{}` |
| `rule_name` | `VARCHAR` | `YES` | `schema` |
| `severity` | `VARCHAR` | `YES` | `info` |
| `passed` | `SMALLINT` | `YES` | `1` |
| `sample_count` | `BIGINT` | `YES` | `0` |
| `detail_json` | `VARCHAR` | `YES` | `{"actual":[["code","VARCHAR"],["code_name","VARCHAR"],["ipo_date","DATE"],["out_date","DATE"],["security_type","SMALLINT"],["list_status","SMALLINT"],["first_seen_date","DATE"],["l` |
| `created_at` | `TIMESTAMP` | `YES` | `2026-03-25 17:13:00.996351` |
