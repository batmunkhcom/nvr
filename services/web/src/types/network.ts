export interface NetworkMetricPoint {
  recorded_at: string | null;
  inbound_mbps: number | null;
  outbound_mbps: number | null;
  rtt_ms: number | null;
  packet_loss_pct: number | null;
  status: "online" | "offline" | "degraded" | "unknown";
}

export interface LatestMetric {
  camera_id: string;
  camera_name: string;
  location: string | null;
  location_color: string | null;
  status: string;
  inbound_mbps: number | null;
  outbound_mbps: number | null;
  rtt_ms: number | null;
  packet_loss_pct: number | null;
  recorded_at: string | null;
}

export interface OverlaySeries {
  camera_id: string;
  camera_name: string;
  location: string | null;
  color: string;
  points: NetworkMetricPoint[];
}

export interface LocationSummary {
  total: number;
  online: number;
  degraded: number;
  offline: number;
  avg_bw: number | null;
  color: string;
}

export interface NetworkDashboardSummary {
  total_cameras: number;
  online_cameras: number;
  degraded_cameras: number;
  offline_cameras: number;
  total_inbound_mbps: number;
  total_outbound_mbps: number;
  avg_latency_ms: number | null;
  active_alerts: number;
  alerts_by_severity: { warning: number; critical: number };
  cameras_by_location: Record<string, LocationSummary>;
}

export interface LocationSummary {
  total: number;
  online: number;
  degraded: number;
  offline: number;
  avg_bw: number | null;
}

export interface NetworkAlert {
  id: string;
  camera_id: string;
  camera_name: string;
  location: string | null;
  alert_type: "bandwidth_low" | "latency_high" | "packet_loss_high" | "camera_offline";
  severity: "warning" | "critical";
  message: string;
  triggered_at: string;
  acknowledged_at: string | null;
  metadata: Record<string, any> | null;
}

export interface NetworkConfigUpdate {
  poll_interval?: number;
  ping_enabled?: boolean;
  ping_count?: number;
  ping_timeout?: number;
  rtsp_check_enabled?: boolean;
  bandwidth_warn_mbps?: number;
  bandwidth_crit_mbps?: number;
  latency_warn_ms?: number;
  latency_crit_ms?: number;
  packet_loss_warn_pct?: number;
  packet_loss_crit_pct?: number;
  retention_days?: number;
}

export interface CameraHistory {
  camera_id: string;
  camera_name: string;
  location: string | null;
  time_range: { start: string; end: string };
  metrics: NetworkMetricPoint[];
  total_count: number;
  page: number;
  per_page: number;
}
