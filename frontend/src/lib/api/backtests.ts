import { apiGet, apiPost } from "@/lib/api/client";
import type { BacktestRequest, BacktestStart, BacktestTask, BacktestTaskList } from "@/types/backtest";

export function runBacktest(request: BacktestRequest): Promise<BacktestStart> {
  return apiPost<BacktestStart>("/api/v1/backtests/run", request);
}

export function getBacktestTask(taskId?: number): Promise<BacktestTask> {
  const query = taskId === undefined ? "" : `?task_id=${encodeURIComponent(taskId)}`;
  return apiGet<BacktestTask>(`/api/v1/backtests/task${query}`);
}

export function listBacktestTasks(limit = 100): Promise<BacktestTaskList> {
  return apiGet<BacktestTaskList>(
    `/api/v1/backtests/tasks?limit=${encodeURIComponent(limit)}`,
  );
}
