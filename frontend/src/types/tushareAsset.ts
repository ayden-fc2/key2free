export type TushareAssetWatermark = {
  asset_table_name: string;
  earliest_trusted_watermark: string | null;
  trusted_watermark: string | null;
  issue_count: number;
  last_issue_at: string | null;
  last_issue_scope: string | null;
  last_issue_message: string | null;
  issue_log: string;
};

export type TushareRefreshStart = {
  ok: boolean;
  task_id: number | null;
  message: string;
};

export type TushareRefreshRequest = {
  end_date: string;
  skip_stk_mins_5min?: boolean;
};

export type TushareRefreshTask = {
  id: number;
  status: "running" | "success" | "error" | string;
  started_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
  current_asset_table_name: string | null;
  current_watermark: string | null;
  logs: string;
};
