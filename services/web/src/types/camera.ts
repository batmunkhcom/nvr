export interface Camera {
  id: string;
  name: string;
  ip_address: string;
  mac_address: string | null;
  manufacturer: string | null;
  model: string | null;
  firmware_version: string | null;
  serial_number: string | null;
  stream_main_uri: string | null;
  stream_sub_uri: string | null;
  stream_audio_uri: string | null;
  auth_type: string;
  username: string;
  has_audio: boolean;
  has_talkback: boolean;
  has_ptz: boolean;
  has_onvif: boolean;
  has_motion_detection: boolean;
  has_io_ports: boolean;
  motion_source: string | null;
  max_resolution: string | null;
  recording_mode: string;
  stream_transport: string;
  ptz_presets: string[] | null;
  status: string;
  connection_error: string | null;
  last_seen_at: string | null;
  tags: string[] | null;
  location: string | null;
  location_id: string | null;
  location_name: string | null;
  storage_backend_id: string | null;
  storage_backend_name: string | null;
  notes: string | null;
  privacy_mode: string | null;
  ai_enabled: boolean;
  ai_objects: string[] | null;
  ai_zones: { points: [number, number][] }[] | null;
  ai_sensitivity: string;
  ai_min_confidence: number;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface CameraReorderItem {
  id: string;
  display_order: number;
}

export interface Location {
  id: string;
  name: string;
  description: string | null;
  color: string;
  camera_count: number;
  created_at: string;
}

export interface CameraCreatePayload {
  name: string;
  ip_address: string;
  username: string;
  password?: string;
  auth_type: string;
  stream_main_uri?: string;
  stream_sub_uri?: string;
  stream_audio_uri?: string;
  recording_mode: string;
  stream_transport: string;
  tags?: string[];
  location?: string;
  location_id?: string | null;
  storage_backend_id?: string;
  notes?: string;
  ai_enabled?: boolean;
  ai_objects?: string[];
  ai_sensitivity?: string;
  ai_min_confidence?: number;
}

export interface CameraUpdatePayload {
  name?: string;
  ip_address?: string;
  username?: string;
  password?: string;
  auth_type?: string;
  stream_main_uri?: string;
  stream_sub_uri?: string;
  stream_audio_uri?: string;
  recording_mode?: string;
  stream_transport?: string;
  is_active?: boolean;
  tags?: string[];
  location?: string;
  location_id?: string | null;
  storage_backend_id?: string;
  notes?: string;
  privacy_mode?: string;
  ai_enabled?: boolean;
  ai_objects?: string[];
  ai_zones?: { points: [number, number][] }[] | null;
  ai_sensitivity?: string;
  ai_min_confidence?: number;
  motion_source?: string;
}

export interface ProbeResult {
  reachable: boolean;
  ip: string;
  open_ports: number[];
  manufacturer: string | null;
  model: string | null;
  server_header: string | null;
  http_title: string | null;
  stream_main_uri: string | null;
  stream_sub_uri: string | null;
  has_rtsp: boolean;
  has_http: boolean;
  has_audio: boolean;
  has_ptz: boolean;
  has_onvif: boolean;
  has_motion_detection: boolean;
  onvif_url: string | null;
}

export interface DiscoveredDevice {
  ip_address: string;
  manufacturer: string | null;
  model: string | null;
  http_title: string | null;
  stream_main_uri: string | null;
  open_ports: number[];
  has_rtsp: boolean;
  has_http: boolean;
  has_audio: boolean;
  has_ptz: boolean;
  has_onvif: boolean;
  has_motion_detection: boolean;
  confidence: number;
}

export interface DiscoveryStatus {
  scan_id: string;
  status: string;
  phases: Record<string, string>;
  found_count: number;
  progress_pct: number;
  scanned_ips: number;
  total_ips: number;
}

export interface TestResult {
  reachable: boolean;
  rtsp_ok: boolean;
  auth_ok: boolean;
  error_code: string | null;
  error_message: string | null;
  latency_ms: number | null;
  stream_resolution: string | null;
  stream_codec: string | null;
  manufacturer: string | null;
  open_ports: number[];
}
