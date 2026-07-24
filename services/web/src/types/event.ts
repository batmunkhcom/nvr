export interface NvrEvent {
  id: string;
  snapshot_path: string | null;
  camera_id: string;
  event_type: string;
  severity: string;
  start_time: string;
  end_time: string | null;
  metadata: Record<string, unknown>;
  is_acknowledged: boolean;
  created_at: string;
}
