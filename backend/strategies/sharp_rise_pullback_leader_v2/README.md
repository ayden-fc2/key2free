# 急涨回踩龙头战术 v2

注册名：`sharp_rise_pullback_leader_v2`

在 v1（`sharp_rise_pullback_leader`）基础上增加趋势强度、RSI、缩量回踩与买入放量确认，其余形态/买卖/观察池规则保持一致。

## 相对 v1 的变更

| 阶段 | 新增条件 | 目的 |
| --- | --- | --- |
| 基础筛选 | `avg_amount_20 >= 50000`（千元，约 5000 万日均成交额） | 过滤流动性不足标的 |
| 基础筛选 | `ma_slope_30 > 0` | 确认 MA30 仍在上升，回踩发生在上升趋势内 |
| 基础筛选 | `45 <= rsi_14 <= 80` | 排除超卖异常与过热追高 |
| 基础筛选 | `0.25 <= volume_ratio_10 <= 3.0` | 回踩量能适中，避免极致无量或放量下跌 |
| 买入 | 触发日 `vol >= T日 avg_volume_10 × 1.15` | 价格突破需伴随放量，减少假突破 |

v2 仍只交易沪深主板（`sh.6` / `sz.0`），代码范围与 v1 相同。详见 v1 README 中「基础筛选 #1」说明。

## 可配置参数（v2 新增）

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `MIN_AVG_AMOUNT_20` | 50000 | 20 日平均成交额下限（千元） |
| `MIN_MA_SLOPE_30` | 0.005 | MA30 斜率下限 |
| `MIN_RSI_14` | 45.0 | RSI14 下限 |
| `MAX_RSI_14` | 80.0 | RSI14 上限 |
| `MIN_VOLUME_RATIO_10` | 0.25 | 10 日量比下限 |
| `MAX_VOLUME_RATIO_10` | 3.0 | 10 日量比上限 |
| `ENTRY_VOLUME_MULTIPLE` | 1.0 | 买入日成交量相对 T 日 10 日均量的倍数 |

其余参数与 v1 相同，见 `../sharp_rise_pullback_leader/README.md`。

## 接入状态

- `signal_history_window = 200`
- 信号字段：v1 字段 + `ma_slope_30`, `rsi_14`, `vol`, `avg_volume_10`, `volume_ratio_10`, `avg_amount_20`
- 买入阶段使用 `today_bars` 中的当日 `vol`（第 5 个字段）与信号日已知的 `signal_avg_volume_10` 比较，不引入未来数据
