import { useMutation, useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";

export interface DiscoveredCamera {
  id: string;
  ip_address: string;
  port: number;
  manufacturer: string | null;
  model: string | null;
  name: string | null;
  rtsp_uri: string | null;
  confidence: number;
  source: string;
}

export interface DiscoverResults {
  scan_id: string;
  cameras: DiscoveredCamera[];
  total_found: number;
}

export function useStartDiscovery() {
  return useMutation({
    mutationFn: async (opts: { network?: string; scan_targets?: string[] }) => {
      const res = await apiClient.post("/cameras/discover", opts);
      return res.data?.data as { scan_id: string };
    },
  });
}

export function useDiscoveryStatus(scanId: string | null) {
  return useQuery({
    queryKey: ["discovery", "status", scanId],
    queryFn: async () => {
      const res = await apiClient.get(`/cameras/discover/${scanId}/status`);
      return res.data?.data as { status: string; phase: string; cameras_found: number; progress_pct: number };
    },
    enabled: !!scanId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === "completed" || data.status === "failed") return false;
      return 2000;
    },
  });
}

export function useDiscoveryResults(scanId: string | null) {
  return useQuery({
    queryKey: ["discovery", "results", scanId],
    queryFn: async () => {
      const res = await apiClient.get(`/cameras/discover/${scanId}/results`);
      return res.data?.data as DiscoverResults;
    },
    enabled: false,
  });
}

export function useAddCamera() {
  return useMutation({
    mutationFn: async (camera: { name: string; ip_address: string; username?: string; password?: string; rtsp_uri?: string }) => {
      const res = await apiClient.post("/cameras", camera);
      return res.data?.data;
    },
  });
}
