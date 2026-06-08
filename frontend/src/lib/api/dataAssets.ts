import { apiGet, apiPost } from "@/lib/api/client";
import type {
  DataAssetTask,
  MartDataAssetRefresh,
  MartDataAssetSummary,
  StockDataAssetRefresh,
  StockDataAssetSummary,
} from "@/types/dataAsset";

export function getStockDataAssetSummary(): Promise<StockDataAssetSummary> {
  return apiGet<StockDataAssetSummary>("/api/v1/data-assets/stocks/summary");
}

export function getMartDataAssetSummary(): Promise<MartDataAssetSummary> {
  return apiGet<MartDataAssetSummary>("/api/v1/data-assets/mart/summary");
}

export function refreshMartDataAssets(): Promise<MartDataAssetRefresh> {
  return apiPost<MartDataAssetRefresh>("/api/v1/data-assets/mart/refresh");
}

export function requestStockDataAssetRefresh(
  datasetNames?: string[],
  targetDate?: string,
): Promise<StockDataAssetRefresh> {
  const params = new URLSearchParams();
  if (datasetNames && datasetNames.length > 0) {
    params.set("dataset_names", datasetNames.join(","));
  }
  if (targetDate) {
    params.set("target_date", targetDate);
  }
  const query = params.size === 0 ? "" : `?${params.toString()}`;
  return apiPost<StockDataAssetRefresh>(`/api/v1/data-assets/stocks/refresh${query}`);
}

export function getSourceUpdateTask(taskId?: number): Promise<DataAssetTask> {
  const query = taskId === undefined ? "" : `?task_id=${taskId}`;
  return apiGet<DataAssetTask>(`/api/v1/data-assets/source-update-task${query}`);
}

export function stopSourceUpdateTask(taskId?: number): Promise<DataAssetTask> {
  const params = new URLSearchParams();
  if (taskId !== undefined) {
    params.set("task_id", String(taskId));
  }
  const query = params.size === 0 ? "" : `?${params.toString()}`;
  return apiPost<DataAssetTask>(`/api/v1/data-assets/source-update-task/stop${query}`);
}
