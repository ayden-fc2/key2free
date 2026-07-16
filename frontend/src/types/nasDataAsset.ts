import type { TushareRefreshTask } from "@/types/tushareAsset";

export type NasConnection = {
  scheme: "http" | "https";
  host: string;
  port: number;
  base_url: string;
};

export type NasDatabaseStatus = {
  ready: boolean;
  path: string;
  size_bytes: number;
  table_count?: number;
  trade_cal_count?: number;
  reason: string | null;
};

export type NasSchedulerStatus = {
  enabled: boolean;
  hour: number;
  minute: number;
  timezone: string;
  next_run_at: string | null;
  thread_alive: boolean;
};

export type NasRemoteConfig = {
  tushare_token_masked: string;
  tushare_token_configured: boolean;
  tushare_http_url: string;
  tushare_mcp_url: string | null;
  tushare_timeout_seconds: number;
  schedule_enabled: boolean;
  schedule_hour: number;
  schedule_minute: number;
  advertised_host: string;
  advertised_port: number;
};

export type NasServiceStatus = {
  service: string;
  status: string;
  version: string;
  sync_implemented: boolean;
  database: NasDatabaseStatus;
  scheduler: NasSchedulerStatus;
  config: NasRemoteConfig;
  timestamp: string;
};

export type NasWatermarkComparison = {
  asset_table_name: string;
  local_earliest_trusted_watermark: string | null;
  local_trusted_watermark: string | null;
  nas_earliest_trusted_watermark: string | null;
  nas_trusted_watermark: string | null;
  pending: boolean;
  metadata_pending: boolean;
  local_issue_count: number;
  local_last_issue_at: string | null;
  local_last_issue_scope: string | null;
  local_last_issue_message: string | null;
  local_issue_log: string;
  nas_issue_count: number;
  nas_last_issue_at: string | null;
  nas_last_issue_scope: string | null;
  nas_last_issue_message: string | null;
  nas_issue_log: string;
};

export type NasOperationLog = {
  id: string;
  timestamp: string;
  operation: string;
  status: string;
  source: string;
  message: string;
  details: Record<string, unknown>;
};

export type NasSyncTask = {
  id: string;
  status: string;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  current_asset_table_name: string | null;
  completed_asset_count: number;
  total_asset_count: number;
  downloaded_bytes: number;
  imported_rows: number;
  logs: string;
};

export type NasRemoteConfigUpdate = Partial<{
  tushare_token: string;
  tushare_http_url: string;
  tushare_mcp_url: string | null;
  tushare_timeout_seconds: number;
  schedule_enabled: boolean;
  schedule_hour: number;
  schedule_minute: number;
  advertised_host: string;
  advertised_port: number;
}>;

export type NasRefreshStart = {
  ok: boolean;
  task_id: number | null;
  message: string;
};

export type NasRefreshTask = TushareRefreshTask;
