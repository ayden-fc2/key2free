import { apiGet, apiPost } from "@/lib/api/client";
import type {
  StockDataAssetRefresh,
  StockDataAssetSummary,
} from "@/types/dataAsset";

export function getStockDataAssetSummary(): Promise<StockDataAssetSummary> {
  return apiGet<StockDataAssetSummary>("/api/v1/data-assets/stocks/summary");
}

export function requestStockDataAssetRefresh(): Promise<StockDataAssetRefresh> {
  return apiPost<StockDataAssetRefresh>("/api/v1/data-assets/stocks/refresh");
}
