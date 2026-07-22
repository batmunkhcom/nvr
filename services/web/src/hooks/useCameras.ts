import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "../api/client";
import type {
  Camera,
  CameraCreatePayload,
  CameraUpdatePayload,
  DiscoveredDevice,
  DiscoveryStatus,
  ProbeResult,
  TestResult,
} from "../types/camera";

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: async () => {
      const res = await apiClient.get("/cameras?per_page=100");
      return (res.data?.data || []) as Camera[];
    },
    refetchInterval: 30_000,
  });
}

export function useCameraMutations() {
  const qc = useQueryClient();

  const createCamera = useMutation({
    mutationFn: (payload: CameraCreatePayload) =>
      apiClient.post("/cameras", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cameras"] });
    },
  });

  const updateCamera = useMutation({
    mutationFn: ({ id, ...payload }: CameraUpdatePayload & { id: string }) =>
      apiClient.patch(`/cameras/${id}`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cameras"] });
    },
  });

  const deleteCamera = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/cameras/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cameras"] });
    },
  });

  const testCamera = useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/cameras/${id}/test`).then((r) => r.data?.data as TestResult),
  });

  return { createCamera, updateCamera, deleteCamera, testCamera };
}

export function useCameraProbe() {
  return useMutation({
    mutationFn: (ip: string) =>
      apiClient
        .post("/cameras/probe", { ip_address: ip })
        .then((r) => r.data?.data as ProbeResult),
  });
}

export function useDiscovery() {
  return useMutation({
    mutationFn: (payload?: {
      subnets?: string[];
      methods?: string[];
      timeout?: number;
    }) =>
      apiClient.post("/cameras/discover", payload || {}).then((r) => r.data?.data),
  });
}

export function useDiscoveryStatus(scanId: string | null) {
  return useQuery({
    queryKey: ["discovery-status", scanId],
    queryFn: () =>
      apiClient
        .get(`/cameras/discover/${scanId}/status`)
        .then((r) => r.data?.data as DiscoveryStatus),
    enabled: !!scanId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : false,
  });
}

export function useDiscoveryResults(scanId: string) {
  return useQuery({
    queryKey: ["discovery-results", scanId],
    queryFn: () =>
      apiClient
        .get(`/cameras/discover/${scanId}/results`)
        .then((r) => (r.data?.data?.devices || []) as DiscoveredDevice[]),
    enabled: false,
  });
}
