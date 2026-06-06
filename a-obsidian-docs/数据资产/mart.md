---
title: Mart 数据资产
tags:
  - data-asset/mart
---

# Mart 数据资产

策略、回测和查询可直接使用的计算数据。mart 对象由 source 派生，不直接调用 BaoStock 写入。

> [!info]
> 本文档由 `data/data.duckdb` 的真实结构生成。字段、类型和示例以当前 DuckDB 为准。

## 对象索引

- [[mart#mart.bar_15m|mart.bar_15m]] `VIEW`
- [[mart#mart.bar_1d_hfq|mart.bar_1d_hfq]] `VIEW`
- [[mart#mart.bar_1d_qfq|mart.bar_1d_qfq]] `VIEW`
- [[mart#mart.bar_1m|mart.bar_1m]] `VIEW`
- [[mart#mart.bar_1w|mart.bar_1w]] `VIEW`
- [[mart#mart.bar_1y|mart.bar_1y]] `VIEW`
- [[mart#mart.bar_30m|mart.bar_30m]] `VIEW`
- [[mart#mart.bar_5m_hfq|mart.bar_5m_hfq]] `VIEW`
- [[mart#mart.bar_5m_qfq|mart.bar_5m_qfq]] `VIEW`
- [[mart#mart.bar_60m|mart.bar_60m]] `VIEW`
- [[mart#mart.universe_daily|mart.universe_daily]] `BASE TABLE`

## mart.bar_15m

- 类型：`VIEW`
- 用途：由 5 分钟行情聚合的 15 分钟行情视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2019-01-02` |
| `trade_year` | `SMALLINT` | `YES` | `2019` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `bar_time` | `TIMESTAMP` | `YES` | `2019-01-02 09:45:00` |
| `open` | `DOUBLE` | `YES` | `9.74` |
| `high` | `DOUBLE` | `YES` | `9.79` |
| `low` | `DOUBLE` | `YES` | `9.72` |
| `close` | `DOUBLE` | `YES` | `9.72` |
| `volume` | `HUGEINT` | `YES` | `2378300` |
| `amount` | `DOUBLE` | `YES` | `23186334.0` |

## mart.bar_1d_hfq

- 类型：`VIEW`
- 用途：由日 K 和复权因子计算的后复权日线视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2010-08-02` |
| `trade_year` | `SMALLINT` | `YES` | `2010` |
| `code` | `VARCHAR` | `YES` | `sh.600306` |
| `open` | `DOUBLE` | `YES` | `16.1149615` |
| `high` | `DOUBLE` | `YES` | `16.248143` |
| `low` | `DOUBLE` | `YES` | `15.808644049999998` |
| `close` | `DOUBLE` | `YES` | `16.1682341` |
| `preclose` | `DOUBLE` | `YES` | `16.0350526` |
| `volume` | `BIGINT` | `YES` | `1458290` |
| `amount` | `DOUBLE` | `YES` | `17570703.0` |
| `turn` | `DOUBLE` | `YES` | `0.959745` |
| `tradestatus` | `SMALLINT` | `YES` | `1` |
| `pct_chg` | `DOUBLE` | `YES` | `0.8306` |
| `pe_ttm` | `DOUBLE` | `YES` | `-321.352258` |
| `pb_mrq` | `DOUBLE` | `YES` | `4.54746` |
| `ps_ttm` | `DOUBLE` | `YES` | `1.312855` |
| `pcf_ncf_ttm` | `DOUBLE` | `YES` | `15.902877` |
| `is_st` | `SMALLINT` | `YES` | `0` |
| `adjust_factor_value` | `DOUBLE` | `YES` | `1.331815` |

## mart.bar_1d_qfq

- 类型：`VIEW`
- 用途：由日 K 和复权因子计算的前复权日线视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2011-09-27` |
| `trade_year` | `SMALLINT` | `YES` | `2011` |
| `code` | `VARCHAR` | `YES` | `sh.000817` |
| `open` | `DOUBLE` | `YES` | `906.497` |
| `high` | `DOUBLE` | `YES` | `910.084` |
| `low` | `DOUBLE` | `YES` | `894.697` |
| `close` | `DOUBLE` | `YES` | `904.461` |
| `preclose` | `DOUBLE` | `YES` | `0.0` |
| `volume` | `BIGINT` | `YES` | `483229400` |
| `amount` | `DOUBLE` | `YES` | `4704320000.0` |
| `turn` | `DOUBLE` | `YES` | `0.007269` |
| `tradestatus` | `SMALLINT` | `YES` | `1` |
| `pct_chg` | `DOUBLE` | `YES` | `0.0` |
| `pe_ttm` | `DOUBLE` | `YES` | `` |
| `pb_mrq` | `DOUBLE` | `YES` | `` |
| `ps_ttm` | `DOUBLE` | `YES` | `` |
| `pcf_ncf_ttm` | `DOUBLE` | `YES` | `` |
| `is_st` | `SMALLINT` | `YES` | `0` |
| `adjust_factor_value` | `DOUBLE` | `YES` | `1.0` |

## mart.bar_1m

- 类型：`VIEW`
- 用途：由日 K 聚合的月线视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `1990-12-31` |
| `trade_year` | `SMALLINT` | `YES` | `1990` |
| `code` | `VARCHAR` | `YES` | `sh.600601` |
| `open` | `DOUBLE` | `YES` | `185.3` |
| `high` | `DOUBLE` | `YES` | `241.3` |
| `low` | `DOUBLE` | `YES` | `185.3` |
| `close` | `DOUBLE` | `YES` | `241.3` |
| `volume` | `HUGEINT` | `YES` | `11010` |
| `amount` | `DOUBLE` | `YES` | `88450.4` |
| `adjustflag` | `SMALLINT` | `YES` | `3` |
| `turn` | `DOUBLE` | `YES` | `5.504999999999999` |
| `pct_chg` | `DOUBLE` | `YES` | `382.6` |

## mart.bar_1w

- 类型：`VIEW`
- 用途：由日 K 聚合的周线视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `1990-12-21` |
| `trade_year` | `SMALLINT` | `YES` | `1990` |
| `code` | `VARCHAR` | `YES` | `sh.600601` |
| `open` | `DOUBLE` | `YES` | `185.3` |
| `high` | `DOUBLE` | `YES` | `204.3` |
| `low` | `DOUBLE` | `YES` | `185.3` |
| `close` | `DOUBLE` | `YES` | `204.3` |
| `volume` | `HUGEINT` | `YES` | `7900` |
| `amount` | `DOUBLE` | `YES` | `59000.0` |
| `adjustflag` | `SMALLINT` | `YES` | `3` |
| `turn` | `DOUBLE` | `YES` | `3.9499999999999997` |
| `pct_chg` | `DOUBLE` | `YES` | `308.6` |

## mart.bar_1y

- 类型：`VIEW`
- 用途：由日 K 聚合的年线视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `1990-12-31` |
| `trade_year` | `SMALLINT` | `YES` | `1990` |
| `code` | `VARCHAR` | `YES` | `sh.600601` |
| `open` | `DOUBLE` | `YES` | `185.3` |
| `high` | `DOUBLE` | `YES` | `241.3` |
| `low` | `DOUBLE` | `YES` | `185.3` |
| `close` | `DOUBLE` | `YES` | `241.3` |
| `volume` | `HUGEINT` | `YES` | `11010` |
| `amount` | `DOUBLE` | `YES` | `88450.4` |
| `adjustflag` | `SMALLINT` | `YES` | `3` |
| `turn` | `DOUBLE` | `YES` | `5.504999999999999` |
| `pct_chg` | `DOUBLE` | `YES` | `382.6` |

## mart.bar_30m

- 类型：`VIEW`
- 用途：由 5 分钟行情聚合的 30 分钟行情视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2019-01-02` |
| `trade_year` | `SMALLINT` | `YES` | `2019` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `bar_time` | `TIMESTAMP` | `YES` | `2019-01-02 10:00:00` |
| `open` | `DOUBLE` | `YES` | `9.74` |
| `high` | `DOUBLE` | `YES` | `9.79` |
| `low` | `DOUBLE` | `YES` | `9.6` |
| `close` | `DOUBLE` | `YES` | `9.61` |
| `volume` | `HUGEINT` | `YES` | `6011500` |
| `amount` | `DOUBLE` | `YES` | `58259893.0` |

## mart.bar_5m_hfq

- 类型：`VIEW`
- 用途：由 5 分钟行情和复权因子计算的后复权分钟视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2023-01-03` |
| `trade_year` | `SMALLINT` | `YES` | `2023` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `time_raw` | `VARCHAR` | `YES` | `20230103093500000` |
| `bar_time` | `TIMESTAMP` | `YES` | `2023-01-03 09:35:00` |
| `open` | `DOUBLE` | `YES` | `83.12831337` |
| `high` | `DOUBLE` | `YES` | `83.24265768000001` |
| `low` | `DOUBLE` | `YES` | `82.55659182` |
| `close` | `DOUBLE` | `YES` | `82.67093613` |
| `volume` | `BIGINT` | `YES` | `1786343` |
| `amount` | `DOUBLE` | `YES` | `12945312.0` |
| `adjust_factor_value` | `DOUBLE` | `YES` | `11.434431` |

## mart.bar_5m_qfq

- 类型：`VIEW`
- 用途：由 5 分钟行情和复权因子计算的前复权分钟视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2023-01-03` |
| `trade_year` | `SMALLINT` | `YES` | `2023` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `time_raw` | `VARCHAR` | `YES` | `20230103093500000` |
| `bar_time` | `TIMESTAMP` | `YES` | `2023-01-03 09:35:00` |
| `open` | `DOUBLE` | `YES` | `6.51272045` |
| `high` | `DOUBLE` | `YES` | `6.521678800000001` |
| `low` | `DOUBLE` | `YES` | `6.4679287` |
| `close` | `DOUBLE` | `YES` | `6.476887050000001` |
| `volume` | `BIGINT` | `YES` | `1786343` |
| `amount` | `DOUBLE` | `YES` | `12945312.0` |
| `adjust_factor_value` | `DOUBLE` | `YES` | `0.895835` |

## mart.bar_60m

- 类型：`VIEW`
- 用途：由 5 分钟行情聚合的 60 分钟行情视图。
- 行数：视图

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2019-01-02` |
| `trade_year` | `SMALLINT` | `YES` | `2019` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `bar_time` | `TIMESTAMP` | `YES` | `2019-01-02 10:30:00` |
| `open` | `DOUBLE` | `YES` | `9.74` |
| `high` | `DOUBLE` | `YES` | `9.79` |
| `low` | `DOUBLE` | `YES` | `9.58` |
| `close` | `DOUBLE` | `YES` | `9.65` |
| `volume` | `HUGEINT` | `YES` | `10068925` |
| `amount` | `DOUBLE` | `YES` | `97243474.0` |

## mart.universe_daily

- 类型：`BASE TABLE`
- 用途：每日可交易股票池计算结果表。
- 行数：20467200

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2003-07-29` |
| `code` | `VARCHAR` | `YES` | `sz.000012` |
| `code_name` | `VARCHAR` | `YES` | `南玻A` |
| `security_type` | `SMALLINT` | `YES` | `1` |
| `list_status` | `SMALLINT` | `YES` | `1` |
| `industry` | `VARCHAR` | `YES` | `` |
| `industry_classification` | `VARCHAR` | `YES` | `` |
| `is_sz50` | `SMALLINT` | `YES` | `0` |
| `is_hs300` | `SMALLINT` | `YES` | `0` |
| `is_zz500` | `SMALLINT` | `YES` | `0` |
