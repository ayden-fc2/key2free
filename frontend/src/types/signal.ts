export type DailySignalItem = {
  code: string;
  code_name: string | null;
  trade_date: string;
  universe: Record<string, unknown>;
  current_bar_1d_qfq: Record<string, unknown> | null;
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

