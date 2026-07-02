# 急涨回踩龙头战术 v2

注册名：`sharp_rise_pullback_leader_v2`

在 v1（`sharp_rise_pullback_leader`）基础上增加趋势强度、RSI 与缩量回踩筛选，买入/卖出/观察池规则与 v1 完全一致。

## 相对 v1 的变更

| 阶段 | 新增条件 | 目的 |
| --- | --- | --- |
| 代码范围 | 仅保留沪深主板 `sh.6` / `sz.0`；排除创业板 `sz.3*`、科创板 `sh.688`、北交所 `bj.*` | 收窄至主板流动性与涨跌停规则更一致的标的 |
| 基础筛选 | `avg_amount_20 >= 50000`（千元，约 5000 万日均成交额） | 过滤流动性不足标的 |
| 基础筛选 | `ma_slope_30 > MIN_MA_SLOPE_30`（默认 `0.005`） | 确认 MA30 仍在上升，回踩发生在上升趋势内 |
| 基础筛选 | `45 <= rsi_14 <= 80` | 排除超卖异常与过热追高 |
| 基础筛选 | `0.25 <= volume_ratio_10 <= 3.0` | 回踩量能适中，避免极致无量或放量下跌 |

v1 的代码范围仍包含创业板 `sz.3*`；v2 在此基础上收窄至主板。其余基础筛选（ST、价格、换手率）、形态确认、买入、卖出与观察池规则与 v1 相同，见 `../sharp_rise_pullback_leader/README.md`。

## 可配置参数（v2 新增）

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `MIN_AVG_AMOUNT_20` | 50000 | 20 日平均成交额下限（千元） |
| `MIN_MA_SLOPE_30` | 0.005 | MA30 斜率下限 |
| `MIN_RSI_14` | 45.0 | RSI14 下限 |
| `MAX_RSI_14` | 80.0 | RSI14 上限 |
| `MIN_VOLUME_RATIO_10` | 0.25 | 10 日量比下限 |
| `MAX_VOLUME_RATIO_10` | 3.0 | 10 日量比上限 |

其余参数与 v1 相同，见 `../sharp_rise_pullback_leader/README.md`。

## 接入状态

- `signal_history_window = 200`
- 信号字段：v1 字段 + `ma_slope_30`, `rsi_14`, `volume_ratio_10`, `avg_amount_20`
- 买卖/观察阶段额外字段：无（与 v1 相同）
