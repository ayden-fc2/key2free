import { apiGet } from "@/lib/api/client";
import type { HealthState } from "@/types/health";

export function getHealth(): Promise<HealthState> {
  return apiGet<HealthState>("/api/v1/health");
}
