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
