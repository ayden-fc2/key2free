import { apiGet, apiPost } from "@/lib/api/client";
import type {
  DailySignalRequest,
  DailySignalResult,
  DailySignalTask,
  DailySignalTaskQuery,
  DailySignalTaskStart,
  StockDataContextRequest,
  StockDataContextResult,
} from "@/types/signal";

export function getSignalStrategies(): Promise<{ strategies: string[] }> {
  return apiGet<{ strategies: string[] }>("/api/v1/signals/strategies");
}

export function getDailySignals(
  request: DailySignalRequest,
): Promise<DailySignalResult> {
  return apiPost<DailySignalResult>("/api/v1/signals/daily", request);
}

export function startDailySignalTask(
  request: DailySignalRequest,
): Promise<DailySignalTaskStart> {
  return apiPost<DailySignalTaskStart>("/api/v1/signals/daily-task", request);
}

export function getDailySignalTask(
  request: DailySignalTaskQuery,
): Promise<DailySignalTask> {
  return apiPost<DailySignalTask>("/api/v1/signals/daily-task/query", request);
}

export function getDailySignalTaskResult(taskId: number): Promise<DailySignalResult> {
  return apiGet<DailySignalResult>(`/api/v1/signals/daily-task/${taskId}/result`);
}

export function getStockDataContexts(
  request: StockDataContextRequest,
): Promise<StockDataContextResult> {
  return apiPost<StockDataContextResult>("/api/v1/signals/stock-contexts", request);
}
