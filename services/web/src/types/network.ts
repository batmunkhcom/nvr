export interface NetworkMetricPoint {
  recorded_at: string | null;
  
    // Bandwidth
  inbound_mbps: number | null;
  outbound_mbps: number | null;
  
    // Latency
  rtt_ms: number | null;
  jitter_ms: number | null;
  rtsp_latency: number | null;
  
    // Packet stats
  packets_sent: number | null;
  packets_recv: number | null;
  packet_loss_pct: number | null;
  
    // Connection quality
  fps_current: number | null;
  bitrate_current: number | null;
  rtsp_reconnect_cnt: number | null;
  
    // FFmpeg process metrics
  ffmpeg_pid: number | null;
  ffmpeg_cpu: number | null;
  ffmpeg_memory_mb: number | null;
  
    // Status
  status: 'online' | 'offline' | 'degraded' | 'unknown';
  error_message: string | null;
}

export interface LatestMetric {
  camera_id: string;
  camera_name: string;
  location: string | null;
  status: string;
  outbound_mbps: number | null;
  rtt_ms: number | null;
  packet_loss_pct: number | null;
  fps_current: number | null;
  bitrate_current: number | null;
  ffmpeg_cpu: number | null;
  ffmpeg_memory_mb: number | null;
  recorded_at: string | null;
}

export interface NetworkDashboardSummary {
  total_cameras: number;
  online_cameras: number;
  degraded_cameras: number;
  offline_cameras: number;
  avg_bandwidth_mbps: number | null;
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
  alert_type: 'bandwidth_low' | 'latency_high' | 'packet_loss_high' | 'camera_offline';
  severity: 'warning' | 'critical';
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
