export type StockDatasetOverview = {
  dataset_name: string;
  enabled: boolean;
  endpoint: string | null;
  row_count: number | null;
  watermark: string | null;
  actual_max_date: string | null;
  updated_at: string | null;
  status: string;
};

export type StockDataAssetSummary = {
  datasets: StockDatasetOverview[];
};

export type StockDataAssetRefresh = {
  status: string;
  message: string;
};
