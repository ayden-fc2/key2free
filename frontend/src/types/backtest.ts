import type { DataAssetTask } from "@/types/dataAsset";

export type BacktestRequest = {
  start_date: string;
  end_date: string;
  initial_cash: number;
  strategy_name: string;
};

export type BacktestStart = {
  task: DataAssetTask;
  message: string;
};

export type BacktestTaskList = DataAssetTask[];
