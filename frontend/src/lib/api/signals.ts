import { apiPost } from "@/lib/api/client";
import type { DailySignalRequest, DailySignalResult } from "@/types/signal";

export function getDailySignals(
  request: DailySignalRequest,
): Promise<DailySignalResult> {
  return apiPost<DailySignalResult>("/api/v1/signals/daily", request);
}

