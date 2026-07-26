import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";

export interface LPRPattern {
  code: string;
  name: string;
  patterns: string[] | null;
}

export interface LPRReading {
  id: string;
  camera_id: string;
  camera_name: string;
  plate_number: string;
  country_code: string;
  pattern_name: string;
  confidence: number;
  detected_at: string;
  plate_image_path: string | null;
  snapshot_path: string | null;
}

export function useLPRPatterns() {
  return useQuery({
    queryKey: ["lpr", "patterns"],
    queryFn: async () => {
      const res = await apiClient.get("/lpr/patterns");
      return (res.data?.data || {}) as Record<string, LPRPattern>;
    },
    staleTime: 5 * 60_000,
  });
}

export function useLPRReadings(params?: {
  camera_id?: string;
  plate_number?: string;
  days?: number;
  page?: number;
  per_page?: number;
}) {
  return useQuery({
    queryKey: ["lpr", "readings", params],
    queryFn: async () => {
      const res = await apiClient.get("/lpr/readings", { params });
      return {
        data: (res.data?.data || []) as LPRReading[],
        metadata: res.data?.metadata || { page: 1, per_page: 50, total: 0 },
      };
    },
    refetchInterval: 30_000,
  });
}
