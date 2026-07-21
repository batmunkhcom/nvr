import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";
import { Recording, TimelineSegment, StorageUsage } from "../types/recording";

export function useRecordings(filters?: Record<string, string>) {
  return useQuery({
    queryKey: ["recordings", filters],
    queryFn: async () => {
      const res = await apiClient.get("/recordings", { params: { per_page: 50, ...filters } });
      return {
        data: (res.data?.data || []) as Recording[],
        metadata: res.data?.metadata || { page: 1, per_page: 50, total: 0 },
      };
    },
    refetchInterval: 30_000,
  });
}

export function useTimeline(cameraId: string, date: string) {
  return useQuery({
    queryKey: ["timeline", cameraId, date],
    queryFn: async () => {
      const res = await apiClient.get("/recordings/timeline", {
        params: { camera_id: cameraId, date },
      });
      return (res.data?.data || []) as TimelineSegment[];
    },
    enabled: !!cameraId && !!date,
  });
}

export function useRecordingStreamUrl(recordingId: string) {
  return `/api/v1/recordings/${recordingId}/stream`;
}

export function useStorageUsage() {
  return useQuery({
    queryKey: ["storage", "usage"],
    queryFn: async () => {
      const res = await apiClient.get("/storage/usage");
      return res.data?.data as StorageUsage;
    },
    refetchInterval: 60_000,
  });
}
