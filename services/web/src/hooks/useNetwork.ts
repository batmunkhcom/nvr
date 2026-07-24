import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { networkApi } from "../api/network";
import type { NetworkDashboardSummary, LatestMetric, NetworkAlert } from "../types/network";

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

export function useCameraHistory(cameraId: string | null | undefined, range = "24h") {
  return useQuery({
    queryKey: ["network", "history", cameraId, range],
    queryFn: () =>
      networkApi.getCameraHistory(cameraId!, range).then((r) => r.data.data),
    enabled: !!cameraId,
    refetchInterval: 30_000,
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

export function useStartMonitoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => networkApi.startMonitoring(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
  });
}

export function useStopMonitoring() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => networkApi.stopMonitoring(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
  });
}

export function useNetworkWebSocket(onMetricUpdate?: (cameraId: string, metrics: Record<string, unknown>) => void) {
  const qc = useQueryClient();

  const onCameraStatus = () => {
    qc.invalidateQueries({ queryKey: ["network", "metrics"] });
    qc.invalidateQueries({ queryKey: ["network", "summary"] });
  };

  const onEvent = () => {
    qc.invalidateQueries({ queryKey: ["network", "alerts"] });
  };

  const onMetric = (cameraId: string, metrics: Record<string, unknown>) => {
    if (onMetricUpdate) {
      onMetricUpdate(cameraId, metrics);
    }
    qc.setQueryData(["network", "metrics"], (old: LatestMetric[] | undefined) => {
      if (!old) return old;
      return old.map((m) =>
        m.camera_id === cameraId ? { ...m, ...metrics } : m
      );
    });
    qc.invalidateQueries({ queryKey: ["network", "summary"] });
  };

  return { connect: onCameraStatus, disconnect: onEvent };
}
