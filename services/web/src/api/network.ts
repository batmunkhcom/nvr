import apiClient from "./client";
import type {
  LatestMetric,
  NetworkDashboardSummary,
  NetworkAlert,
  NetworkConfigUpdate,
  CameraHistory,
  OverlaySeries,
} from "../types/network";

export const networkApi = {
  getLatestMetrics: () =>
    apiClient.get<{ data: LatestMetric[] }>("/network/metrics"),

  getCameraHistory: (cameraId: string, range = "24h", page = 1, perPage = 100) =>
    apiClient.get<{ data: CameraHistory }>(
      `/network/metrics/${cameraId}/history`,
      { params: { range, page, per_page: perPage } },
    ),

  getAggregateHistory: (range = "24h") =>
    apiClient.get<{ data: CameraHistory }>("/network/metrics/all/history", {
      params: { range },
    }),

  getOverlayHistory: (range = "24h") =>
    apiClient.get<{ data: OverlaySeries[] }>("/network/metrics/overlay", {
      params: { range },
    }),

  getSummary: () =>
    apiClient.get<{ data: NetworkDashboardSummary }>("/network/summary"),

  getMonitorStatus: () =>
    apiClient.get<{ data: { running: boolean } }>("/network/monitor/status"),

  toggleMonitoring: () =>
    apiClient.post<{ data: { running: boolean; status: string } }>(
      "/network/monitor/toggle",
    ),

  getActiveAlerts: () =>
    apiClient.get<{ data: NetworkAlert[] }>("/network/alerts"),

  getAllAlerts: (
    page = 1,
    perPage = 25,
    cameraId?: string,
    severity?: string,
    alertType?: string,
  ) =>
    apiClient.get<{
      data: NetworkAlert[];
      total_count: number;
      page: number;
      per_page: number;
    }>("/network/alerts/all", {
      params: {
        page,
        per_page: perPage,
        camera_id: cameraId,
        severity,
        alert_type: alertType,
      },
    }),

  acknowledgeAlert: (alertId: string) =>
    apiClient.post<{ data: any }>(`/network/alerts/${alertId}/acknowledge`),

  getCameraConfig: (cameraId: string) =>
    apiClient.get<{ data: NetworkConfigUpdate | null }>(
      `/network/config/${cameraId}`,
    ),

  updateCameraConfig: (cameraId: string, config: NetworkConfigUpdate) =>
    apiClient.patch<{ data: any }>(`/network/config/${cameraId}`, config),
};
