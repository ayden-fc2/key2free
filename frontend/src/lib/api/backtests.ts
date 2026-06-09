import { apiGet, apiPost } from "@/lib/api/client";
import type { DataAssetTask } from "@/types/dataAsset";
import type { BacktestRequest, BacktestStart, BacktestTaskList } from "@/types/backtest";

export function runBacktest(request: BacktestRequest): Promise<BacktestStart> {
  return apiPost<BacktestStart>("/api/v1/backtests/run", request);
}

export function getBacktestTask(taskId?: number): Promise<DataAssetTask> {
  const query = taskId === undefined ? "" : `?task_id=${encodeURIComponent(taskId)}`;
  return apiGet<DataAssetTask>(`/api/v1/backtests/task${query}`);
}

export function listBacktestTasks(limit = 100): Promise<BacktestTaskList> {
  return apiGet<BacktestTaskList>(
    `/api/v1/backtests/tasks?limit=${encodeURIComponent(limit)}`,
  );
}
