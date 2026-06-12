import { apiGet, apiPost } from "@/lib/api/client";
import type {
  TushareAssetWatermark,
  TushareRefreshRequest,
  TushareRefreshStart,
  TushareRefreshTask,
} from "@/types/tushareAsset";

export function listTushareWatermarks(): Promise<TushareAssetWatermark[]> {
  return apiGet<TushareAssetWatermark[]>("/api/v1/tushare-assets/watermarks");
}

export function startTushareRefresh(request: TushareRefreshRequest): Promise<TushareRefreshStart> {
  return apiPost<TushareRefreshStart>("/api/v1/tushare-assets/refresh", request);
}

export function getTushareRefreshTask(taskId?: number): Promise<TushareRefreshTask> {
  const query = taskId === undefined ? "" : `?task_id=${encodeURIComponent(taskId)}`;
  return apiGet<TushareRefreshTask>(`/api/v1/tushare-assets/refresh-task${query}`);
}
