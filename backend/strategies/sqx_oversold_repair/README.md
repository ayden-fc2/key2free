# sqx_oversold_repair

Registered name: `sqx_oversold_repair`

`sqx_oversold_repair` is an individual-stock oversold repair strategy. It looks
for stocks that recently broke into a short-term bearish MA structure after a
tight prior range, then waits one trading day for an intraday repair
confirmation.

## No Future Data

- Signal selection runs after T close and only reads daily wide-table rows whose
  `trade_date <= T`.
- Structure prices `L`, `D`, stop price, target price, and reward/risk are
  frozen into `signal.extras` on T. Buy and sell functions reuse those values.
- T+1 buy confirmation reads only T+1 observable daily open plus the first 30
  minutes of 5min bars. The 30-minute floor is the signal-day low `L`, frozen on
  T. Missing 5min data means no buy.
- Sell rules use current-day observable OHLC only. The target is intraday by
  current-day high; the stop is a close-only stop by current-day close.

## Rules

### 1. Basic Filter

- Exclude STAR Market (`sh.688`), BSE (`bj.*`), and rows whose name contains
  `ST`.
- Exclude rows with `is_st != 0`.
- Require latest quarterly `eps > 0`.
- Require at least 250 visible trading bars.
- Require unadjusted close `> 10`.
- Require market value `> 300000` (Tushare unit: 10k CNY, equivalent to RMB
  3bn). The strategy prefers `total_mv` and falls back to `circ_mv` only when
  `total_mv` is unavailable.

### 2. Long Structure Filter

For signal day T:

- Require `MA10 < MA20 < MA30`.
- Walk backward at most 100 bars to find B, the first day of the current
  continuous bearish MA stack.
- Require `B -> T >= 5` trading days.
- In `B..T`, define `L` as the latest lowest `qfq_low`.
- Require `L` to occur within `T-3..T`, and require `T close <= L * 1.05`.
- Let `A = B - 2 * (T - B)`.
- In `A..B-1`, define `U` as max `qfq_high` and `D` as min `qfq_low`.
- The prior range is treated as a 10% price box, but allows outliers: at least
  80% of the daily candles in `A..B-1` must have both `qfq_low` and `qfq_high`
  inside some price band `[box_low, box_low * 1.10]`. At least two candles may
  be exempt even in short windows.

### 3. Short Signal Filter

- T volume must be at least `1.5 * avg(T-5..T-1 volume)`.
- T lower shadow must satisfy:
  `lower_shadow >= (real_body + upper_shadow) * 0.8`.
- Stop price is `L * 0.95`.
- Target price is `D * 0.99`.
- Require reward/risk at T close:
  `(T close - L*0.95) * 1.7 <= (D*0.99 - T close)`.

### 4. Buy

- The signal is observed for T+1 only.
- T+1 open must be higher than T close.
- During the first 30 minutes, 5min lows must not break signal-day low `L`.
- Buy price is the 5min close at the 30-minute confirmation point.

### 5. Sell

- If close breaks `L * 0.95`, sell at that close.
- If intraday high reaches `D * 0.99`, sell at `D * 0.99`.
- At T+4 close, if the highest price since buy has not reached `buy_price *
  1.08`, sell at that close.

## Framework Registration

- Signal fields include: `name`, `list_date`, `close`, `qfq_open`, `qfq_high`,
  `qfq_low`, `qfq_close`, `ma_10`, `ma_20`, `ma_30`, `vol`, `eps`, `total_mv`,
  `circ_mv`, `is_st`.
- Signal history window: 260 trading bars.
- Backtest lifecycle: `select_signals`, `update_watch_pool`, `decide_buys`,
  `decide_sells`.
