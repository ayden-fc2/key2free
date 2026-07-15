import { apiGet, apiPost, apiPut } from "@/lib/api/client";
import type {
  NasConnection,
  NasOperationLog,
  NasRefreshStart,
  NasRefreshTask,
  NasRemoteConfig,
  NasRemoteConfigUpdate,
  NasServiceStatus,
  NasSyncTask,
  NasWatermarkComparison,
} from "@/types/nasDataAsset";

export function getNasConnection(): Promise<NasConnection> {
  return apiGet<NasConnection>("/api/v1/nas-data-assets/connection");
}

export function updateNasConnection(connection: Omit<NasConnection, "base_url">): Promise<NasConnection> {
  return apiPut<NasConnection>("/api/v1/nas-data-assets/connection", connection);
}

export function getNasStatus(): Promise<NasServiceStatus> {
  return apiGet<NasServiceStatus>("/api/v1/nas-data-assets/status");
}

export function getNasRemoteConfig(): Promise<NasRemoteConfig> {
  return apiGet<NasRemoteConfig>("/api/v1/nas-data-assets/remote-config");
}

export function updateNasRemoteConfig(config: NasRemoteConfigUpdate): Promise<NasRemoteConfig> {
  return apiPut<NasRemoteConfig>("/api/v1/nas-data-assets/remote-config", config);
}

export function listNasWatermarks(): Promise<NasWatermarkComparison[]> {
  return apiGet<NasWatermarkComparison[]>("/api/v1/nas-data-assets/watermarks");
}

export function listNasOperationLogs(limit = 100): Promise<NasOperationLog[]> {
  return apiGet<NasOperationLog[]>(`/api/v1/nas-data-assets/logs?limit=${limit}`);
}

export function startNasRefresh(request: {
  end_date: string;
  skip_stk_mins_5min: boolean;
}): Promise<NasRefreshStart> {
  return apiPost<NasRefreshStart>("/api/v1/nas-data-assets/refresh", request);
}

export function getNasRefreshTask(taskId?: number): Promise<NasRefreshTask> {
  const query = taskId === undefined ? "" : `?task_id=${taskId}`;
  return apiGet<NasRefreshTask>(`/api/v1/nas-data-assets/refresh-task${query}`);
}

export function startNasIncrementalSync(includeStkMins5min: boolean): Promise<NasSyncTask> {
  return apiPost<NasSyncTask>("/api/v1/nas-data-assets/sync", {
    include_stk_mins_5min: includeStkMins5min,
  });
}

export function getNasIncrementalSyncTask(): Promise<NasSyncTask> {
  return apiGet<NasSyncTask>("/api/v1/nas-data-assets/sync-task");
}
