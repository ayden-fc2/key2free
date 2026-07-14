export type DailySignalItem = {
  code: string;
  code_name: string | null;
  trade_date: string;
  universe: Record<string, unknown>;
  signal?: SignalDecision | null;
};

export type SignalDecision = {
  triggered: boolean;
  signal_close: number | null;
  entry_trigger_price?: number | string | null;
  sell_rules?: SignalRule[];
  stop_losses: number[];
  take_profits: number[];
  max_watch_days: number | null;
  display?: SignalDisplay | null;
  extras: Record<string, unknown> | null;
};

export type SignalRule = {
  name?: string;
  rule_type?: "static" | "dynamic" | string;
  timing?: string;
  trigger_price?: number | string | null;
  sell_price?: number | string | null;
  description?: string;
};

export type SignalDisplay = {
  title?: string;
  signal_date?: string;
  entry?: string;
  watch?: string;
  sell?: string[];
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
  macd_dif_12_26_9: number | null;
  macd_dea_12_26_9: number | null;
  macd_hist_12_26_9: number | null;
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
  start_trade_date?: string | null;
  end_trade_date?: string | null;
  lookback_trade_days?: number;
};

export type SignalReplayPoolItem = {
  code: string;
  code_name: string | null;
  pool_type: "watch" | "holding" | string;
  signal_date: string | null;
  added_date: string | null;
  buy_date: string | null;
  buy_price: number | null;
  quantity: number | null;
  signal?: SignalDecision | null;
};

export type SignalReplayResult = {
  trade_date: string;
  strategy_name: string;
  start_trade_date: string;
  end_trade_date: string;
  replay_trade_days: number;
  signal_count: number;
  end_trade_date_signal_count: number;
  watch_count: number;
  holding_count: number;
  watch_pool: SignalReplayPoolItem[];
  holdings: SignalReplayPoolItem[];
};

export type DailySignalRequest = {
  trade_date: string;
  strategy_name: string;
  lookback_trade_days?: number;
};

export type SignalReplayRequest = {
  trade_date: string;
  strategy_name: string;
  replay_trade_days?: number;
};

export type DailySignalTask = {
  id: number | null;
  status: string;
  trade_date: string;
  strategy_name: string;
  lookback_trade_days: number;
  universe_count: number | null;
  processed_count: number;
  signal_count: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  logs: string;
};

export type DailySignalTaskStart = {
  task: DailySignalTask;
  message: string;
};

export type DailySignalTaskQuery = {
  task_id?: number | null;
  trade_date?: string | null;
  strategy_name?: string | null;
};

export type StockDataContextRequest = {
  codes: string[];
};

export type StockDataContextResult = {
  contexts: StockDataContext[];
};
