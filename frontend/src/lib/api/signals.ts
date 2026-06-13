import { apiGet, apiPost } from "@/lib/api/client";
import type {
  DailySignalRequest,
  DailySignalResult,
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

export function getStockDataContexts(
  request: StockDataContextRequest,
): Promise<StockDataContextResult> {
  return apiPost<StockDataContextResult>("/api/v1/signals/stock-contexts", request);
}
