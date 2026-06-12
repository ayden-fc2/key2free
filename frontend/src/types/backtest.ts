export type BacktestRequest = {
  start_date: string;
  end_date: string;
  initial_cash: number;
  strategy_name: string;
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
