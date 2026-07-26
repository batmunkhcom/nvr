import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";

export interface CounterSummary {
  person: number;
  vehicle: number;
  animal: number;
  livestock: number;
}

export interface CounterHourly {
  hour: number;
  person: number;
  vehicle: number;
  animal: number;
  livestock: number;
}

export function useCounterSummary(cameraId?: string, days = 1) {
  return useQuery({
    queryKey: ["counters", "summary", cameraId, days],
    queryFn: async () => {
      const params: Record<string, string | number> = { days };
      if (cameraId) params.camera_id = cameraId;
      const res = await apiClient.get("/counters/summary", { params });
      return (res.data?.data || {}) as CounterSummary;
    },
    refetchInterval: 60_000,
  });
}

export function useCounterHourly(cameraId: string, date: string) {
  return useQuery({
    queryKey: ["counters", "hourly", cameraId, date],
    queryFn: async () => {
      const res = await apiClient.get("/counters/hourly", {
        params: { camera_id: cameraId, target_date: date },
      });
      return (res.data?.data || []) as CounterHourly[];
    },
    enabled: !!cameraId && !!date,
  });
}
