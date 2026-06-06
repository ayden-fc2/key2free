---
title: Source 数据资产
tags:
  - data-asset/source
---

# Source 数据资产

外部接口同步后的原始业务数据。同步脚本直接维护 source 表。

> [!info]
> 本文档由 `data/data.duckdb` 的真实结构生成。字段、类型和示例以当前 DuckDB 为准。

## 对象索引

- [[source#source.adjust_factor|source.adjust_factor]] `BASE TABLE`
- [[source#source.all_stock_snapshot|source.all_stock_snapshot]] `BASE TABLE`
- [[source#source.balance|source.balance]] `BASE TABLE`
- [[source#source.bar_1d_raw|source.bar_1d_raw]] `BASE TABLE`
- [[source#source.bar_5m_raw|source.bar_5m_raw]] `BASE TABLE`
- [[source#source.cash_flow|source.cash_flow]] `BASE TABLE`
- [[source#source.deposit_rate|source.deposit_rate]] `BASE TABLE`
- [[source#source.dividend|source.dividend]] `BASE TABLE`
- [[source#source.dupont|source.dupont]] `BASE TABLE`
- [[source#source.forecast|source.forecast]] `BASE TABLE`
- [[source#source.growth|source.growth]] `BASE TABLE`
- [[source#source.index_member_snapshot|source.index_member_snapshot]] `BASE TABLE`
- [[source#source.industry_snapshot|source.industry_snapshot]] `BASE TABLE`
- [[source#source.loan_rate|source.loan_rate]] `BASE TABLE`
- [[source#source.money_supply_month|source.money_supply_month]] `BASE TABLE`
- [[source#source.money_supply_year|source.money_supply_year]] `BASE TABLE`
- [[source#source.operation|source.operation]] `BASE TABLE`
- [[source#source.performance_express|source.performance_express]] `BASE TABLE`
- [[source#source.profit|source.profit]] `BASE TABLE`
- [[source#source.reserve_ratio|source.reserve_ratio]] `BASE TABLE`
- [[source#source.security_master|source.security_master]] `BASE TABLE`
- [[source#source.trade_calendar|source.trade_calendar]] `BASE TABLE`

## source.adjust_factor

- 类型：`BASE TABLE`
- 用途：复权因子源表，用于生成前复权、后复权行情。
- 行数：61261
- 维护：endpoint=`query_adjust_factor`；asset_scope=`equity_index_etf`；enabled=`1`；priority=`80`；chunk_strategy=`code_full`；replace_strategy=`code_date_window`。
- 水位：watermark_value=`2026-05-11`；updated_at=`2026-05-14 17:26:56.405267`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `divid_operate_date` | `DATE` | `YES` | `2002-08-22` |
| `fore_adjust_factor` | `DOUBLE` | `YES` | `0.119615` |
| `back_adjust_factor` | `DOUBLE` | `YES` | `1.526763` |
| `adjust_factor` | `DOUBLE` | `YES` | `1.526763` |
| `ingest_run_id` | `BIGINT` | `YES` | `28` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-28 04:06:28.360287` |

## source.all_stock_snapshot

- 类型：`BASE TABLE`
- 用途：全市场股票快照源表，用于构建每日股票池。
- 行数：20467200
- 维护：endpoint=`query_all_stock`；asset_scope=`all`；enabled=`1`；priority=`30`；chunk_strategy=`trade_day`；replace_strategy=`single_date`。
- 水位：watermark_value=`2026-05-12`；updated_at=`2026-05-14 16:25:42.817585`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `1990-12-19` |
| `code` | `VARCHAR` | `YES` | `sh.000001` |
| `code_name` | `VARCHAR` | `YES` | `上证综合指数` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-03-25 10:21:00.999506` |

## source.balance

- 类型：`BASE TABLE`
- 用途：季频偿债能力源表。
- 行数：36858
- 维护：endpoint=`query_balance_data`；asset_scope=`equity`；enabled=`1`；priority=`140`；chunk_strategy=`dataset_code_year_quarter`；replace_strategy=`code_year_quarter`。
- 水位：watermark_value=`2025-03-31`；updated_at=`2026-04-01 12:37:01.979111`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `pub_date` | `DATE` | `YES` | `2024-04-30` |
| `stat_date` | `DATE` | `YES` | `2024-03-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2024` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `1` |
| `current_ratio` | `DOUBLE` | `YES` | `` |
| `quick_ratio` | `DOUBLE` | `YES` | `` |
| `cash_ratio` | `DOUBLE` | `YES` | `` |
| `yoy_liability` | `DOUBLE` | `YES` | `0.019831` |
| `liability_to_asset` | `DOUBLE` | `YES` | `0.917011` |
| `asset_to_equity` | `DOUBLE` | `YES` | `12.04973` |
| `ingest_run_id` | `BIGINT` | `YES` | `43` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-31 09:19:26.187850` |

## source.bar_1d_raw

- 类型：`BASE TABLE`
- 用途：日 K 原始行情源表。
- 行数：20320968
- 维护：endpoint=`query_history_k_data_plus`；asset_scope=`equity_index_etf`；enabled=`1`；priority=`40`；chunk_strategy=`code_full_then_fallback_year`；replace_strategy=`code_or_code_year`。
- 水位：watermark_value=`2026-05-14`；updated_at=`2026-05-14 17:17:40.777863`。

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
| `adjustflag` | `SMALLINT` | `YES` | `3` |
| `turn` | `DOUBLE` | `YES` | `0.007269` |
| `tradestatus` | `SMALLINT` | `YES` | `1` |
| `pct_chg` | `DOUBLE` | `YES` | `0.0` |
| `pe_ttm` | `DOUBLE` | `YES` | `` |
| `pb_mrq` | `DOUBLE` | `YES` | `` |
| `ps_ttm` | `DOUBLE` | `YES` | `` |
| `pcf_ncf_ttm` | `DOUBLE` | `YES` | `` |
| `is_st` | `SMALLINT` | `YES` | `0` |
| `ingest_run_id` | `BIGINT` | `YES` | `8` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-26 00:07:54.396422` |

## source.bar_5m_raw

- 类型：`BASE TABLE`
- 用途：5 分钟 K 原始行情源表。
- 行数：385114579
- 维护：endpoint=`query_history_k_data_plus`；asset_scope=`equity_etf`；enabled=`1`；priority=`70`；chunk_strategy=`code_year_then_fallback_quarter`；replace_strategy=`code_year_or_quarter`。
- 水位：watermark_value=`2026-05-14`；updated_at=`2026-05-14 17:26:48.375968`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `trade_date` | `DATE` | `YES` | `2023-01-03` |
| `trade_year` | `SMALLINT` | `YES` | `2023` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `time_raw` | `VARCHAR` | `YES` | `20230103093500000` |
| `bar_time` | `TIMESTAMP` | `YES` | `2023-01-03 09:35:00` |
| `open` | `DOUBLE` | `YES` | `7.27` |
| `high` | `DOUBLE` | `YES` | `7.28` |
| `low` | `DOUBLE` | `YES` | `7.22` |
| `close` | `DOUBLE` | `YES` | `7.23` |
| `volume` | `BIGINT` | `YES` | `1786343` |
| `amount` | `DOUBLE` | `YES` | `12945312.0` |
| `adjustflag` | `SMALLINT` | `YES` | `3` |
| `ingest_run_id` | `BIGINT` | `YES` | `14` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-26 16:51:19.984278` |

## source.cash_flow

- 类型：`BASE TABLE`
- 用途：季频现金流量源表。
- 行数：37203
- 维护：endpoint=`query_cash_flow_data`；asset_scope=`equity`；enabled=`1`；priority=`150`；chunk_strategy=`dataset_code_year_quarter`；replace_strategy=`code_year_quarter`。
- 水位：watermark_value=`2024-06-30`；updated_at=`2026-04-01 16:15:22.025104`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `pub_date` | `DATE` | `YES` | `2024-04-30` |
| `stat_date` | `DATE` | `YES` | `2024-03-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2024` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `1` |
| `ca_to_asset` | `DOUBLE` | `YES` | `` |
| `nca_to_asset` | `DOUBLE` | `YES` | `` |
| `tangible_asset_to_asset` | `DOUBLE` | `YES` | `` |
| `ebit_to_interest` | `DOUBLE` | `YES` | `` |
| `cfo_to_or` | `DOUBLE` | `YES` | `-9.98566` |
| `cfo_to_np` | `DOUBLE` | `YES` | `-25.630238` |
| `cfo_to_gr` | `DOUBLE` | `YES` | `-9.98566` |
| `ingest_run_id` | `BIGINT` | `YES` | `49` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-04-01 05:42:33.800679` |

## source.deposit_rate

- 类型：`BASE TABLE`
- 用途：存款利率宏观源表。
- 行数：43
- 维护：endpoint=`query_deposit_rate_data`；asset_scope=`macro`；enabled=`1`；priority=`210`；chunk_strategy=`small_full_table`；replace_strategy=`date_window`。
- 水位：watermark_value=`2015-10-24`；updated_at=`2026-05-14 17:27:02.105960`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `pub_date` | `DATE` | `YES` | `1990-04-15` |
| `demand_deposit_rate` | `DOUBLE` | `YES` | `2.88` |
| `fixed_deposit_rate3_month` | `DOUBLE` | `YES` | `6.3` |
| `fixed_deposit_rate6_month` | `DOUBLE` | `YES` | `7.74` |
| `fixed_deposit_rate1_year` | `DOUBLE` | `YES` | `10.08` |
| `fixed_deposit_rate2_year` | `DOUBLE` | `YES` | `10.98` |
| `fixed_deposit_rate3_year` | `DOUBLE` | `YES` | `11.88` |
| `fixed_deposit_rate5_year` | `DOUBLE` | `YES` | `13.68` |
| `installment_fixed_deposit_rate1_year` | `DOUBLE` | `YES` | `` |
| `installment_fixed_deposit_rate3_year` | `DOUBLE` | `YES` | `` |
| `installment_fixed_deposit_rate5_year` | `DOUBLE` | `YES` | `` |
| `ingest_run_id` | `BIGINT` | `YES` | `94` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-05-14 09:27:00.930644` |

## source.dividend

- 类型：`BASE TABLE`
- 用途：分红除权源表。
- 行数：17159
- 维护：endpoint=`query_dividend_data`；asset_scope=`equity`；enabled=`1`；priority=`90`；chunk_strategy=`code_year_type`；replace_strategy=`code_year_type`。
- 水位：watermark_value=`2024-12-24`；updated_at=`2026-03-31 13:38:21.022775`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600006` |
| `query_year` | `SMALLINT` | `YES` | `2025` |
| `query_year_type` | `VARCHAR` | `YES` | `operate` |
| `divid_pre_notice_date` | `DATE` | `YES` | `` |
| `divid_agm_pum_date` | `DATE` | `YES` | `2025-05-21` |
| `divid_plan_announce_date` | `DATE` | `YES` | `2025-04-26` |
| `divid_plan_date` | `DATE` | `YES` | `2025-07-11` |
| `divid_regist_date` | `DATE` | `YES` | `2025-07-16` |
| `divid_operate_date` | `DATE` | `YES` | `2025-07-17` |
| `divid_pay_date` | `DATE` | `YES` | `2025-07-17` |
| `divid_stock_market_date` | `DATE` | `YES` | `` |
| `divid_cash_ps_before_tax` | `DOUBLE` | `YES` | `0.005` |
| `divid_cash_ps_after_tax` | `DOUBLE` | `YES` | `` |
| `divid_stocks_ps` | `DOUBLE` | `YES` | `0.0` |
| `divid_cash_stock` | `VARCHAR` | `YES` | `10派0.05元（含税，扣税后0.045或0.05元）` |
| `divid_reserve_to_stock_ps` | `DOUBLE` | `YES` | `` |
| `ingest_run_id` | `BIGINT` | `YES` | `36` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-29 03:46:23.482722` |

## source.dupont

- 类型：`BASE TABLE`
- 用途：季频杜邦指数源表。
- 行数：37245
- 维护：endpoint=`query_dupont_data`；asset_scope=`equity`；enabled=`1`；priority=`160`；chunk_strategy=`dataset_code_year_quarter`；replace_strategy=`code_year_quarter`。
- 水位：watermark_value=`2025-09-30`；updated_at=`2026-04-02 19:48:52.410488`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `pub_date` | `DATE` | `YES` | `2024-04-30` |
| `stat_date` | `DATE` | `YES` | `2024-03-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2024` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `1` |
| `dupont_roe` | `DOUBLE` | `YES` | `0.023738` |
| `dupont_asset_sto_equity` | `DOUBLE` | `YES` | `12.305018` |
| `dupont_asset_turn` | `DOUBLE` | `YES` | `0.00502` |
| `dupont_pnitoni` | `DOUBLE` | `YES` | `0.986467` |
| `dupont_nitogr` | `DOUBLE` | `YES` | `0.389605` |
| `dupont_tax_burden` | `DOUBLE` | `YES` | `0.867771` |
| `dupont_intburden` | `DOUBLE` | `YES` | `` |
| `dupont_ebittogr` | `DOUBLE` | `YES` | `` |
| `ingest_run_id` | `BIGINT` | `YES` | `49` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-04-01 09:15:23.879870` |

## source.forecast

- 类型：`BASE TABLE`
- 用途：业绩预告源表。
- 行数：15521
- 维护：endpoint=`query_forecast_report`；asset_scope=`equity`；enabled=`1`；priority=`180`；chunk_strategy=`code_yearly_date_window`；replace_strategy=`code_date_window`。
- 水位：watermark_value=`2026-04-30`；updated_at=`2026-05-14 17:27:00.815106`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600004` |
| `pub_date` | `DATE` | `YES` | `2024-01-13` |
| `stat_date` | `DATE` | `YES` | `2023-12-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2023` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `4` |
| `profit_forcast_type` | `VARCHAR` | `YES` | `扭亏` |
| `profit_forcast_abstract` | `VARCHAR` | `YES` | `预计2023年1-12月归属于上市公司股东的净利润盈利:43,818.51万元至53,555.96万元,同比上年增长150,938.97万元至160,676.42万元。` |
| `profit_forcast_chg_pct_up` | `DOUBLE` | `YES` | `149.996013` |
| `profit_forcast_chg_pct_dwn` | `DOUBLE` | `YES` | `140.905827` |
| `ingest_run_id` | `BIGINT` | `YES` | `51` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-04-02 13:17:28.328294` |

## source.growth

- 类型：`BASE TABLE`
- 用途：季频成长能力源表。
- 行数：36744
- 维护：endpoint=`query_growth_data`；asset_scope=`equity`；enabled=`1`；priority=`130`；chunk_strategy=`dataset_code_year_quarter`；replace_strategy=`code_year_quarter`。
- 水位：watermark_value=`2025-06-30`；updated_at=`2026-03-31 16:32:50.786409`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `pub_date` | `DATE` | `YES` | `2024-04-30` |
| `stat_date` | `DATE` | `YES` | `2024-03-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2024` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `1` |
| `yoy_equity` | `DOUBLE` | `YES` | `0.040816` |
| `yoy_asset` | `DOUBLE` | `YES` | `0.021555` |
| `yoyni` | `DOUBLE` | `YES` | `0.093498` |
| `yoyeps_basic` | `DOUBLE` | `YES` | `0.117647` |
| `yoypni` | `DOUBLE` | `YES` | `0.100436` |
| `ingest_run_id` | `BIGINT` | `YES` | `39` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-30 08:14:08.432895` |

## source.index_member_snapshot

- 类型：`BASE TABLE`
- 用途：指数成分股快照源表。
- 行数：65750
- 维护：endpoint=`query_index_members`；asset_scope=`index_members`；enabled=`1`；priority=`270`；chunk_strategy=`index_code_date`；replace_strategy=`index_code_date`。
- 水位：watermark_value=`2026-05-04`；updated_at=`2026-05-14 17:09:50.728994`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `index_code` | `VARCHAR` | `YES` | `sh.000016` |
| `index_name` | `VARCHAR` | `YES` | `上证50` |
| `update_date` | `DATE` | `YES` | `2026-01-05` |
| `code` | `VARCHAR` | `YES` | `sh.600028` |
| `code_name` | `VARCHAR` | `YES` | `中国石化` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-04-03 04:45:08.390800` |

## source.industry_snapshot

- 类型：`BASE TABLE`
- 用途：行业分类快照源表。
- 行数：357972
- 维护：endpoint=`query_stock_industry`；asset_scope=`equity`；enabled=`1`；priority=`260`；chunk_strategy=`snapshot_date`；replace_strategy=`single_date`。
- 水位：watermark_value=`2026-05-11`；updated_at=`2026-05-14 17:09:42.679638`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `update_date` | `DATE` | `YES` | `2026-01-05` |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `code_name` | `VARCHAR` | `YES` | `浦发银行` |
| `industry` | `VARCHAR` | `YES` | `J66货币金融服务` |
| `industry_classification` | `VARCHAR` | `YES` | `证监会行业分类` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-04-03 04:39:31.819782` |

## source.loan_rate

- 类型：`BASE TABLE`
- 用途：贷款利率宏观源表。
- 行数：43
- 维护：endpoint=`query_loan_rate_data`；asset_scope=`macro`；enabled=`1`；priority=`220`；chunk_strategy=`small_full_table`；replace_strategy=`date_window`。
- 水位：watermark_value=`2015-10-24`；updated_at=`2026-05-14 17:27:02.283902`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `pub_date` | `DATE` | `YES` | `1990-04-15` |
| `loan_rate6_month` | `DOUBLE` | `YES` | `` |
| `loan_rate6_month_to1_year` | `DOUBLE` | `YES` | `` |
| `loan_rate1_year_to3_year` | `DOUBLE` | `YES` | `` |
| `loan_rate3_year_to5_year` | `DOUBLE` | `YES` | `` |
| `loan_rate_above5_year` | `DOUBLE` | `YES` | `` |
| `mortgate_rate_below5_year` | `DOUBLE` | `YES` | `` |
| `mortgate_rate_above5_year` | `DOUBLE` | `YES` | `` |
| `ingest_run_id` | `BIGINT` | `YES` | `94` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-05-14 09:27:02.237842` |

## source.money_supply_month

- 类型：`BASE TABLE`
- 用途：月度货币供应量源表。
- 行数：607
- 维护：endpoint=`query_money_supply_data_month`；asset_scope=`macro`；enabled=`1`；priority=`240`；chunk_strategy=`small_full_table`；replace_strategy=`date_window`。
- 水位：watermark_value=`2026-04-01`；updated_at=`2026-05-14 17:27:04.678420`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `stat_year` | `SMALLINT` | `YES` | `1951` |
| `stat_month` | `SMALLINT` | `YES` | `12` |
| `m0_month` | `DOUBLE` | `YES` | `` |
| `m0_yoy` | `DOUBLE` | `YES` | `` |
| `m0_chain_relative` | `DOUBLE` | `YES` | `` |
| `m1_month` | `DOUBLE` | `YES` | `` |
| `m1_yoy` | `DOUBLE` | `YES` | `` |
| `m1_chain_relative` | `DOUBLE` | `YES` | `` |
| `m2_month` | `DOUBLE` | `YES` | `` |
| `m2_yoy` | `DOUBLE` | `YES` | `` |
| `m2_chain_relative` | `DOUBLE` | `YES` | `` |
| `stat_date` | `DATE` | `YES` | `1951-12-01` |
| `ingest_run_id` | `BIGINT` | `YES` | `94` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-05-14 09:27:03.574420` |

## source.money_supply_year

- 类型：`BASE TABLE`
- 用途：年度货币供应量源表。
- 行数：73
- 维护：endpoint=`query_money_supply_data_year`；asset_scope=`macro`；enabled=`1`；priority=`250`；chunk_strategy=`small_full_table`；replace_strategy=`date_window`。
- 水位：watermark_value=`2024-12-31`；updated_at=`2026-05-14 17:27:04.981257`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `stat_year` | `SMALLINT` | `YES` | `1952` |
| `m0_year` | `DOUBLE` | `YES` | `` |
| `m0_year_yoy` | `DOUBLE` | `YES` | `` |
| `m1_year` | `DOUBLE` | `YES` | `` |
| `m1_year_yoy` | `DOUBLE` | `YES` | `` |
| `m2_year` | `DOUBLE` | `YES` | `101.3` |
| `m2_year_yoy` | `DOUBLE` | `YES` | `` |
| `stat_date` | `DATE` | `YES` | `1952-12-31` |
| `ingest_run_id` | `BIGINT` | `YES` | `94` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-05-14 09:27:04.790397` |

## source.operation

- 类型：`BASE TABLE`
- 用途：季频营运能力源表。
- 行数：36615
- 维护：endpoint=`query_operation_data`；asset_scope=`equity`；enabled=`1`；priority=`120`；chunk_strategy=`dataset_code_year_quarter`；replace_strategy=`code_year_quarter`。
- 水位：watermark_value=`2025-03-31`；updated_at=`2026-03-30 15:07:32.670562`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `pub_date` | `DATE` | `YES` | `2024-08-20` |
| `stat_date` | `DATE` | `YES` | `2024-06-30` |
| `fiscal_year` | `SMALLINT` | `YES` | `2024` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `2` |
| `nr_turn_ratio` | `DOUBLE` | `YES` | `` |
| `nr_turn_days` | `DOUBLE` | `YES` | `` |
| `inv_turn_ratio` | `DOUBLE` | `YES` | `` |
| `inv_turn_days` | `DOUBLE` | `YES` | `` |
| `ca_turn_ratio` | `DOUBLE` | `YES` | `` |
| `asset_turn_ratio` | `DOUBLE` | `YES` | `0.009665` |
| `ingest_run_id` | `BIGINT` | `YES` | `39` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-30 05:08:24.049660` |

## source.performance_express

- 类型：`BASE TABLE`
- 用途：业绩快报源表。
- 行数：3176
- 维护：endpoint=`query_performance_express_report`；asset_scope=`equity`；enabled=`1`；priority=`170`；chunk_strategy=`code_yearly_date_window`；replace_strategy=`code_date_window`。
- 水位：watermark_value=`2026-05-07`；updated_at=`2026-05-14 17:27:00.173668`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600007` |
| `pub_date` | `DATE` | `YES` | `2024-03-16` |
| `stat_date` | `DATE` | `YES` | `2023-12-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2023` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `4` |
| `performance_exp_update_date` | `DATE` | `YES` | `2024-03-16` |
| `performance_express_total_asset` | `DOUBLE` | `YES` | `12881140000.0` |
| `performance_express_net_asset` | `DOUBLE` | `YES` | `9700160000.0` |
| `performance_express_eps_chg_pct` | `DOUBLE` | `YES` | `0.126126` |
| `performance_express_roe_wa` | `DOUBLE` | `YES` | `13.53` |
| `performance_express_eps_diluted` | `DOUBLE` | `YES` | `1.25` |
| `performance_express_gryoy` | `DOUBLE` | `YES` | `0.148588` |
| `performance_express_opyoy` | `DOUBLE` | `YES` | `0.210185` |
| `ingest_run_id` | `BIGINT` | `YES` | `51` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-04-02 12:04:23.022545` |

## source.profit

- 类型：`BASE TABLE`
- 用途：季频盈利能力源表。
- 行数：36615
- 维护：endpoint=`query_profit_data`；asset_scope=`equity`；enabled=`1`；priority=`110`；chunk_strategy=`dataset_code_year_quarter`；replace_strategy=`code_year_quarter`。
- 水位：watermark_value=`2024-06-30`；updated_at=`2026-03-30 12:20:43.319498`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.600000` |
| `pub_date` | `DATE` | `YES` | `2025-03-29` |
| `stat_date` | `DATE` | `YES` | `2024-12-31` |
| `fiscal_year` | `SMALLINT` | `YES` | `2024` |
| `fiscal_quarter` | `SMALLINT` | `YES` | `4` |
| `roe_avg` | `DOUBLE` | `YES` | `0.06195` |
| `np_margin` | `DOUBLE` | `YES` | `0.268437` |
| `gp_margin` | `DOUBLE` | `YES` | `` |
| `net_profit` | `DOUBLE` | `YES` | `45835000000.0` |
| `eps_ttm` | `DOUBLE` | `YES` | `1.541862` |
| `mb_revenue` | `DOUBLE` | `YES` | `317913000000.0` |
| `total_share` | `DOUBLE` | `YES` | `29352178302.0` |
| `liqa_share` | `DOUBLE` | `YES` | `29352178302.0` |
| `ingest_run_id` | `BIGINT` | `YES` | `4` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-03-25 09:30:06.916249` |

## source.reserve_ratio

- 类型：`BASE TABLE`
- 用途：存款准备金率宏观源表。
- 行数：47
- 维护：endpoint=`query_required_reserve_ratio_data`；asset_scope=`macro`；enabled=`1`；priority=`230`；chunk_strategy=`small_full_table`；replace_strategy=`date_window`。
- 水位：watermark_value=`2018-07-05`；updated_at=`2026-05-14 17:27:02.429476`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `pub_date` | `DATE` | `YES` | `1999-11-18` |
| `effective_date` | `DATE` | `YES` | `1999-11-21` |
| `big_institutions_ratio_pre` | `DOUBLE` | `YES` | `8.0` |
| `big_institutions_ratio_after` | `DOUBLE` | `YES` | `6.0` |
| `medium_institutions_ratio_pre` | `DOUBLE` | `YES` | `8.0` |
| `medium_institutions_ratio_after` | `DOUBLE` | `YES` | `6.0` |
| `ingest_run_id` | `BIGINT` | `YES` | `94` |
| `loaded_at` | `TIMESTAMP` | `YES` | `2026-05-14 09:27:02.387564` |

## source.security_master

- 类型：`BASE TABLE`
- 用途：证券基础资料源表。
- 行数：8657
- 维护：endpoint=`query_stock_basic`；asset_scope=`all`；enabled=`1`；priority=`10`；chunk_strategy=`table_once`；replace_strategy=`full_table`。
- 水位：watermark_value=``；updated_at=``。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `code` | `VARCHAR` | `YES` | `sh.000001` |
| `code_name` | `VARCHAR` | `YES` | `上证综合指数` |
| `ipo_date` | `DATE` | `YES` | `1991-07-15` |
| `out_date` | `DATE` | `YES` | `` |
| `security_type` | `SMALLINT` | `YES` | `2` |
| `list_status` | `SMALLINT` | `YES` | `1` |
| `first_seen_date` | `DATE` | `YES` | `2026-03-25` |
| `last_seen_date` | `DATE` | `YES` | `2026-03-25` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-03-25 10:09:45.184392` |

## source.trade_calendar

- 类型：`BASE TABLE`
- 用途：交易日历源表。
- 行数：12931
- 维护：endpoint=`query_trade_dates`；asset_scope=`cn`；enabled=`1`；priority=`20`；chunk_strategy=`year_range`；replace_strategy=`date_window`。
- 水位：watermark_value=`2026-05-14`；updated_at=`2026-05-14 16:25:30.967831`。

| 字段 | 类型 | 可空 | 示例 |
| --- | --- | --- | --- |
| `calendar_date` | `DATE` | `YES` | `1990-12-19` |
| `is_trading_day` | `SMALLINT` | `YES` | `1` |
| `exchange` | `VARCHAR` | `YES` | `CN` |
| `updated_at` | `TIMESTAMP` | `YES` | `2026-03-25 10:10:19.488131` |
