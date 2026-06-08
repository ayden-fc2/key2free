export type DailySignalItem = {
  code: string;
  code_name: string | null;
  trade_date: string;
  universe: Record<string, unknown>;
  signal?: SignalDecision | null;
};

export type SignalDecision = {
  triggered: boolean;
  min_stop_loss: number | null;
  reference_take_profit: number | null;
  signal_atr30: number | null;
  ideal_buy_price: number | null;
  max_watch_days: number | null;
};

export type Bar1dQfq = {
  trade_date: string;
  trade_year: number;
  code: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  preclose: number | null;
  volume: number | null;
  amount: number | null;
  turn: number | null;
  tradestatus: number | null;
  pct_chg: number | null;
  pe_ttm: number | null;
  pb_mrq: number | null;
  ps_ttm: number | null;
  pcf_ncf_ttm: number | null;
  is_st: number | null;
  adjust_factor_value: number | null;
};

export type StockDataContext = {
  code: string;
  trade_date: string;
  universe: Record<string, unknown>;
  bars_1d_qfq: Bar1dQfq[];
};

export type DailySignalResult = {
  trade_date: string;
  strategy_name: string;
  universe_count: number;
  signal_count: number;
  signals: DailySignalItem[];
};

export type DailySignalRequest = {
  trade_date: string;
  strategy_name: string;
};

export type StockDataContextRequest = {
  codes: string[];
};

export type StockDataContextResult = {
  contexts: StockDataContext[];
};
