export type StockDatasetOverview = {
  dataset_name: string;
  enabled: boolean;
  endpoint: string | null;
  row_count: number | null;
  watermark: string | null;
  actual_max_date: string | null;
  updated_at: string | null;
  status: string;
  latest_validation_at: string | null;
  validation_failed_count: number;
  latest_chunk_status: string | null;
  chunk_failed_count: number;
  open_repair_count: number;
};

export type StockDataAssetSummary = {
  datasets: StockDatasetOverview[];
};

export type MartDatasetOverview = {
  dataset_name: string;
  table_name: string;
  table_type: string;
  enabled: boolean;
  row_count: number | null;
  watermark: string | null;
  actual_max_date: string | null;
  updated_at: string | null;
  status: string;
  latest_validation_at: string | null;
  validation_failed_count: number;
};

export type MartDataAssetSummary = {
  datasets: MartDatasetOverview[];
};

export type MartDataAssetRefresh = {
  status: string;
  message: string;
  refreshed_count: number;
};

export type StockDataAssetRefresh = {
  status: string;
  message: string;
  task_id: number | null;
};

export type DataAssetTask = {
  id: number | null;
  type: string;
  logs: string;
  status: "running" | "error" | "success" | string;
};
