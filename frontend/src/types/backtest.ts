export type BacktestRequest = {
  start_date: string;
  end_date: string;
  initial_cash: number;
  strategy_name: string;
  simulation_runs?: number;
};

export type BacktestTask = {
  id: number | null;
  status: "running" | "error" | "success" | string;
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  simulation_runs: number;
  completed_runs: number;
  trading_day_count: number | null;
  signal_count: number | null;
  final_asset_avg: number | null;
  final_asset_min: number | null;
  final_asset_max: number | null;
  final_return_avg: number | null;
  final_return_min: number | null;
  final_return_max: number | null;
  annualized_return_avg: number | null;
  trades_per_year_avg: number | null;
  win_rate_avg: number | null;
  sharpe_ratio_avg: number | null;
  profit_loss_ratio_avg: number | null;
  excess_return_avg: number | null;
  max_drawdown_avg: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  logs: string;
};

export type BacktestStart = {
  task: BacktestTask;
  message: string;
};

export type BacktestTaskList = BacktestTask[];

export type BacktestSellOp = {
  trade_date: string;
  sell_price: number;
  quantity: number;
  amount: number;
  fee: number;
  pnl: number | null;
  reason: string | null;
  level: number | null;
};

export type BacktestTrade = {
  code: string;
  code_name: string | null;
  buy_date: string;
  buy_price: number;
  quantity: number;
  buy_amount: number;
  buy_fee: number;
  sells: BacktestSellOp[];
  sell_count: number;
  total_pnl: number | null;
  last_sell_date: string | null;
  holding_days: number | null;
  closed: boolean;
  signal: {
    signal_close?: number | null;
    stop_losses?: number[];
    take_profits?: number[];
  } & Record<string, unknown>;
};

export type BacktestEquityCurves = {
  dates: string[];
  runs: { run_no: number; returns: number[] }[];
};

export type BacktestDetail = {
  task_id: number;
  run_no: number;
  available_runs: number[];
  equity_curves: BacktestEquityCurves | null;
  trades: BacktestTrade[];
};
