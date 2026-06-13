import { apiGet, apiPost } from "@/lib/api/client";
import type {
  BacktestDetail,
  BacktestRequest,
  BacktestStart,
  BacktestTask,
  BacktestTaskList,
} from "@/types/backtest";

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

export function getBacktestDetail(
  taskId: number,
  runNo = 1,
  includeCurves = true,
): Promise<BacktestDetail> {
  const params = new URLSearchParams({
    task_id: String(taskId),
    run_no: String(runNo),
    include_curves: includeCurves ? "true" : "false",
  });
  return apiGet<BacktestDetail>(`/api/v1/backtests/detail?${params.toString()}`);
}
