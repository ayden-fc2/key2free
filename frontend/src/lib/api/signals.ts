import { apiPost } from "@/lib/api/client";
import type {
  DailySignalRequest,
  DailySignalResult,
  StockDataContextRequest,
  StockDataContextResult,
} from "@/types/signal";

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
