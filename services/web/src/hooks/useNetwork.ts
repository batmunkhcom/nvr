import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { networkApi } from "../api/network";
import type {
  NetworkDashboardSummary,
  LatestMetric,
  OverlaySeries,
} from "../types/network";

export function useNetworkSummary() {
  return useQuery({
    queryKey: ["network", "summary"],
    queryFn: () => networkApi.getSummary().then((r) => r.data.data),
    refetchInterval: 30_000,
  });
}

export function useLatestMetrics() {
  return useQuery({
    queryKey: ["network", "metrics"],
    queryFn: () => networkApi.getLatestMetrics().then((r) => r.data.data),
    refetchInterval: 30_000,
  });
}

export function useOverlayHistory(range = "24h") {
  return useQuery({
    queryKey: ["network", "overlay", range],
    queryFn: () =>
      networkApi.getOverlayHistory(range).then((r) => r.data.data),
    refetchInterval: 30_000,
  });
}

export function useCameraHistory(
  cameraId: string | null | undefined,
  range = "24h",
) {
  return useQuery({
    queryKey: ["network", "history", cameraId, range],
    queryFn: () =>
      networkApi.getCameraHistory(cameraId!, range).then((r) => r.data.data),
    enabled: !!cameraId,
    refetchInterval: 30_000,
  });
}

export function useAggregateHistory(range = "24h") {
  return useQuery({
    queryKey: ["network", "history", "all", range],
    queryFn: () =>
      networkApi.getAggregateHistory(range).then((r) => r.data.data),
    refetchInterval: 30_000,
  });
}

export function useMonitorStatus() {
  return useQuery({
    queryKey: ["network", "monitor", "status"],
    queryFn: () => networkApi.getMonitorStatus().then((r) => r.data.data),
    refetchInterval: 15_000,
  });
}

export function useToggleMonitoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => networkApi.toggleMonitoring(),
    onSuccess: (r) => {
      qc.setQueryData(["network", "monitor", "status"], r.data.data);
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
  });
}

export function useActiveAlerts() {
  return useQuery({
    queryKey: ["network", "alerts"],
    queryFn: () => networkApi.getActiveAlerts().then((r) => r.data.data),
    refetchInterval: 15_000,
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => networkApi.acknowledgeAlert(alertId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["network", "alerts"] });
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
  });
}

export function useNetworkWebSocket(
  onMetricUpdate?: (cameraId: string, metrics: Record<string, unknown>) => void,
) {
  const qc = useQueryClient();

  return {
    onCameraStatus: () => {
      qc.invalidateQueries({ queryKey: ["network", "metrics"] });
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
    onEvent: () => {
      qc.invalidateQueries({ queryKey: ["network", "alerts"] });
    },
    onMetric: (cameraId: string, metrics: Record<string, unknown>) => {
      onMetricUpdate?.(cameraId, metrics);
      qc.setQueryData<LatestMetric[] | undefined>(
        ["network", "metrics"],
        (old) =>
          old?.map((m) =>
            m.camera_id === cameraId ? { ...m, ...metrics } : m,
          ),
      );
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
  };
}
