# volume_breakout_macd

Registered name: `volume_breakout_macd`

This strategy looks for a low-volatility body range followed by a volume
breakout while MACD DEA and MA20 are both turning upward.

## No Future Data

- Signal selection runs after T close and only reads daily wide-table rows whose
  `trade_date <= T`.
- The consolidation body range high `H`, low `L`, buy trigger `H * 1.02`, and
  close-stop line `(H + L) / 2` are frozen into the signal payload on T.
- Buy decisions run from T+1 to T+3 and use only current-day observable OHLC
  from `today_bars`.
- Sell decisions use current-day observable OHLC plus frozen signal values and
  holding state. No T+1 or later wide-table indicators are read.

## Signal Rules

On signal day T:

1. `macd_dea_12_26_9(T) - macd_dea_12_26_9(T-1) >= 0`.
2. `ma_20(T) - ma_20(T-1) >= 0`.
3. From T-15 through T-2, define each candle body high as
   `max(qfq_open, qfq_close)` and body low as `min(qfq_open, qfq_close)`.
   Let `H` be the highest body high and `L` be the lowest body low. Require
   `(H - L) / L <= 7%`.
4. T volume must be at least `1.5 * avg(vol[T-5..T-1])`.
5. T turnover rate must be at least `1.5 * avg(turnover_rate[T-5..T-1])`.
6. T-day `rsi_5` must be at least `60`, keeping only symbols with enough
   short-term strength.
7. T close must be between `H * 1.01` and `H * 1.04`, keeping the
   breakout near the consolidation range instead of chasing an already extended
   move.

## Buy Rules

The signal is observed for at most three trading days after T.

1. If the observation-day open is already at or above `H * 1.02`, buy at open.
2. Otherwise, if the observation-day intraday high reaches `H * 1.02`, buy at
   `H * 1.02`.

Each buy targets 25% of current total assets and rounds down to full lots.

## Sell Rules

1. If the highest price since buy is at least `buy_price * 1.06` and the
   current-day intraday low touches `highest_since_buy * 0.96`, sell at
   `highest_since_buy * 0.96`.
2. At each close, if the close is below `(H + L) / 2`, sell at close.

## Framework Registration

- Signal history window: 30 trading bars.
- Signal calculation implements `select_signals_for_dates()` so backtests can
  evaluate each loaded date batch by grouping stock history once instead of
  rebuilding per-day full-market signal views.
- Signal fields include: `name`, `qfq_open`, `qfq_high`, `qfq_low`,
  `qfq_close`, `vol`, `turnover_rate`, `ma_20`, `macd_dea_12_26_9`,
  `rsi_5`, `is_st`.
- Buy/sell lifecycle uses only `today_bars`, current holdings, watch pool, and
  frozen signal payload values.
