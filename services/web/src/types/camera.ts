export interface Camera {
  id: string;
  name: string;
  ip_address: string;
  mac_address: string | null;
  manufacturer: string | null;
  model: string | null;
  stream_main_uri: string | null;
  stream_sub_uri: string | null;
  auth_type: string;
  username: string;
  has_audio: boolean;
  has_talkback: boolean;
  has_ptz: boolean;
  has_onvif: boolean;
  max_resolution: string | null;
  recording_mode: string;
  status: string;
  tags: string[] | null;
  location: string | null;
  created_at: string;
}
