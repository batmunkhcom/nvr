import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import { Recording, TimelineSegment, StorageBackend, StorageUsage } from "../types/recording";

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

export interface RecordingDaily {
  date: string;
  segments: number;
  size_bytes: number;
  duration_seconds: number;
}

export function useRecordingDaily(days = 7, cameraId?: string) {
  return useQuery({
    queryKey: ["recordings", "daily", days, cameraId],
    queryFn: async () => {
      const params: Record<string, string | number> = { days };
      if (cameraId) params.camera_id = cameraId;
      const res = await apiClient.get("/recordings/daily", { params });
      return (res.data?.data || []) as RecordingDaily[];
    },
    refetchInterval: 60_000,
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
  if (!recordingId) return "";
  const token = localStorage.getItem("access_token") || "";
  return `/api/v1/recordings/${recordingId}/stream?token=${encodeURIComponent(token)}`;
}

export function recordingThumbnailUrl(recordingId: string) {
  const token = localStorage.getItem("access_token") || "";
  return `/api/v1/recordings/${recordingId}/thumbnail?token=${encodeURIComponent(token)}`;
}

export interface BulkDeletePayload {
  ids?: string[];
  delete_all?: boolean;
  before?: string;
  camera_id?: string;
}

export function useBulkDeleteRecordings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: BulkDeletePayload) => {
      const res = await apiClient.post("/recordings/bulk-delete", payload);
      return res.data?.data as { deleted: number; freed_bytes: number };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      qc.invalidateQueries({ queryKey: ["timeline"] });
      qc.invalidateQueries({ queryKey: ["storage"] });
    },
  });
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

export interface StorageAnalysis {
  computed_at: string;
  total_gb_per_day: number;
  total_stored_gb: number;
  days_fit: number | null;
  disk: { total_gb: number; used_gb: number; free_gb: number; used_percent: number };
  per_camera: {
    camera_id: string;
    camera: string;
    stored_gb: number;
    stored_segments: number;
    gb_per_day: number;
    segments_24h: number;
  }[];
}

export function useStorageAnalysis() {
  return useQuery({
    queryKey: ["storage", "analysis"],
    queryFn: async () => {
      const res = await apiClient.get("/storage/analysis");
      return (res.data?.data || null) as StorageAnalysis | null;
    },
    refetchInterval: 300_000,
  });
}

export function useStorageBackends() {
  return useQuery({
    queryKey: ["storage", "backends"],
    queryFn: async () => {
      const res = await apiClient.get("/storage/backends");
      return (res.data?.data || []) as StorageBackend[];
    },
  });
}

export function useStorageMutations() {
  const qc = useQueryClient();
  const inval = () => {
    qc.invalidateQueries({ queryKey: ["storage"] });
  };

  const create = useMutation({
    mutationFn: (body: {
      name: string;
      backend_type: string;
      mount_point?: string;
      config?: Record<string, unknown>;
      total_bytes?: number;
      available_bytes?: number;
      priority?: number;
    }) => apiClient.post("/storage/backends", body),
    onSuccess: inval,
  });

  const update = useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      name?: string;
      mount_point?: string;
      config?: Record<string, unknown>;
      total_bytes?: number;
      available_bytes?: number;
      priority?: number;
      is_active?: boolean;
    }) => apiClient.patch(`/storage/backends/${id}`, body),
    onSuccess: inval,
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/storage/backends/${id}`),
    onSuccess: inval,
  });

  return { create, update, remove };
}

export function useDeleteRecording() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/recordings/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recordings"] });
      qc.invalidateQueries({ queryKey: ["timeline"] });
    },
  });
}
