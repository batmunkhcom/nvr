export interface Recording {
  id: string;
  camera_id: string;
  storage_backend_id: string | null;
  file_path: string;
  file_size_bytes: number;
  duration_seconds: number;
  start_time: string;
  end_time: string;
  recording_type: 'continuous' | 'motion' | 'event';
  has_audio: boolean;
  resolution: string | null;
  codec: string | null;
  bitrate_kbps: number | null;
  event_id: string | null;
  is_corrupt: boolean;
  created_at: string;
}

export interface TimelineSegment {
  camera_id: string;
  start_time: string;
  end_time: string;
  recording_type: string;
  has_motion: boolean;
}

export interface StorageBackend {
  id: string;
  name: string;
  backend_type: string;
  mount_point: string | null;
  config: Record<string, unknown>;
  total_bytes: number;
  available_bytes: number;
  priority: number;
  is_active: boolean;
  health_status: string;
  last_health_check: string | null;
}

export interface StorageUsage {
  total_bytes: number;
  used_bytes: number;
  free_bytes: number;
  backends: StorageBackend[];
}
