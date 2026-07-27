import { useEffect, useState } from "react";
import { Save, RotateCw, Bell, Monitor, Camera, Radio, Disc, HardDrive, MessageSquare, Brain, Video } from "lucide-react";
import apiClient from "../../api/client";
import { useToast } from "../ui/Toast";

interface ConfigEntry {
  key: string;
  value: string | number | boolean;
  label: string;
  description?: string;
  help?: string;
  type: "text" | "number" | "toggle" | "select";
  options?: string[];
}

const CATEGORIES: { key: string; label: string; icon: typeof Monitor }[] = [
  { key: "ui.", label: "UI", icon: Monitor },
  { key: "camera.", label: "Camera", icon: Camera },
  { key: "stream.", label: "Streaming", icon: Video },
  { key: "mediamtx.", label: "MediaMTX", icon: Radio },
  { key: "recording.", label: "Recording", icon: Disc },
  { key: "storage.", label: "Storage", icon: HardDrive },
  { key: "notification.", label: "Notifications", icon: MessageSquare },
  { key: "ai.", label: "AI", icon: Brain },
];

// [label, fallback help text, type, options?]
const LABELS: Record<string, [string, string | undefined, "text" | "number" | "toggle" | "select", string[]?]> = {
  "ui.refresh_interval_s": ["Refresh Interval (s)", "How often the camera list reloads. Lower = more up-to-date, higher = less server load. Recommended: 30.", "number"],
  "ui.theme": ["Theme", "UI color theme. Currently only 'dark' is supported.", "text"],
  "ui.language": ["Language", "Interface language: 'mn' (Монгол) or 'en' (English).", "select", ["mn", "en"]],
  "camera.test_timeout_s": ["Test Timeout (s)", "How long to wait for a camera RTSP auth check before marking it failed. Increase to 10+ for slow networks.", "number"],
  "camera.health_check_interval_s": ["Health Check Interval (s)", "How often the background loop pings every camera and updates its status. 60–120s recommended; minimum 30.", "number"],
  "mediamtx.rtsp_url": ["MediaMTX RTSP URL", "Internal relay target for FFmpeg transcoded streams. Only change if MediaMTX runs on a different host.", "text"],
  "mediamtx.hls_url": ["MediaMTX HLS URL", "Base URL used by browsers to play HLS streams. Must be reachable from client machines.", "text"],
  "recording.retention_days": ["Retention (days)", "Maximum days to keep recordings. Circular cleanup deletes earlier when the disk watermark is hit, whichever comes first.", "number"],
  "recording.segment_seconds": ["Segment Length (s)", "Length of one recording file. 300s is a good balance: shorter = finer deletion granularity, longer = fewer files.", "number"],
  "recording.stream": ["Recording Stream (System Default)", "Fallback when a camera has no override. 'sub' = low bitrate sub-stream (~10x less disk, good for evidence). 'main' = full quality. Per-camera override available in camera settings.", "select", ["sub", "main"]],
  "storage.max_usage_percent": ["Disk Max Usage (%)", "When the recordings disk exceeds this, the oldest recordings are deleted automatically. Keeps the system from ever filling the disk.", "number"],
  "storage.min_free_gb": ["Disk Min Free (GB)", "Always keep at least this much free space. If free space drops below, oldest recordings are deleted until it recovers.", "number"],
  "notification.channels_enabled": ["Enabled Channels", 'JSON list of notification channels, e.g. ["telegram","webhook"]', "text"],
  "notification.telegram_bot_token": ["Telegram Bot Token", "Create a bot via @BotFather in Telegram and paste its token here.", "text"],
  "notification.telegram_chat_id": ["Telegram Chat ID", "Your user or group chat ID that receives alerts.", "text"],
  "notification.webhook_url": ["Webhook URL", "HTTP endpoint that receives POST notifications (camera offline, AI detections).", "text"],
  "ai.enabled": ["AI Detection", "Enable the AI engine (object detection on camera streams). Disable to save CPU.", "toggle"],
  "ai.provider": ["AI Provider", "Summarization backend: 'openai' or 'ollama' (local).", "text"],
  "ai.base_url": ["AI Base URL", "API endpoint of the summarization provider.", "text"],
  "ai.api_key": ["AI API Key", "Bearer token (leave empty for local Ollama).", "text"],
  "ai.model": ["AI Model", "Model name, e.g. gpt-4o-mini / llama3.2-vision.", "text"],
  "ai.motion_detection_enabled": ["Motion Detection", "Run the OpenCV motion gate before AI inference — saves ~80% CPU. Keep enabled.", "toggle"],
  "ai.confidence_threshold": ["Confidence Threshold", "Minimum AI detection confidence, 0–1. Higher = fewer false alarms, lower = catches more. Recommended: 0.5.", "number"],
  "stream.sub_bitrate_kbps": ["Sub-stream Bitrate (kbps)", "Video bitrate for sub-stream (dashboard tiles). Lower = less CPU & bandwidth. 300–1000 recommended.", "number"],
  "stream.main_bitrate_kbps": ["Main-stream Bitrate (kbps)", "Video bitrate for main stream (live view). 1500–4000 recommended.", "number"],
  "stream.threads": ["FFmpeg Threads", "CPU threads per FFmpeg transcode. 1 = lowest CPU per stream (good for many cameras). 0 = auto-detect. Restart streams to apply.", "number"],
};

export default function ConfigSection() {
  const { toast } = useToast();
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [dbDescriptions, setDbDescriptions] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [loaded, setLoaded] = useState(false);
  const [testing, setTesting] = useState(false);
  const [activeTab, setActiveTab] = useState("ui.");

  const load = async () => {
    try {
      const res = await apiClient.get("/system/config");
      setConfigs(res.data?.data || {});
      setEditing({});
    } catch {
      toast("error", "Failed to load configuration");
    }
    try {
      const entriesRes = await apiClient.get("/system/config/entries");
      const descs: Record<string, string> = {};
      for (const e of entriesRes.data?.data || []) {
        if (e.description) descs[e.key] = e.description;
      }
      setDbDescriptions(descs);
    } catch {
      // descriptions are optional — fall back to built-in help text
    }
    setLoaded(true);
  };

  useEffect(() => { load(); }, []);

  const save = async (key: string) => {
    const value = editing[key] ?? configs[key];
    setSaving((prev) => ({ ...prev, [key]: true }));
    try {
      await apiClient.patch("/system/config", null, { params: { key, value: String(value) } });
      setConfigs((prev) => ({ ...prev, [key]: String(value) }));
      setEditing((prev) => { const n = { ...prev }; delete n[key]; return n; });
      toast("success", "Saved");
    } catch {
      toast("error", "Failed to save");
    }
    setSaving((prev) => ({ ...prev, [key]: false }));
  };

  const testNotification = async () => {
    setTesting(true);
    try {
      const res = await apiClient.post("/system/notification/test");
      const results = res.data?.data?.results || [];
      const sent = results.filter((r: { status: string }) => r.status === "sent").length;
      toast(sent > 0 ? "success" : "warning", `Notification test: ${sent}/${results.length} sent`);
    } catch {
      toast("error", "Notification test failed");
    }
    setTesting(false);
  };

  const displayValue = (key: string) => key in editing ? editing[key] : (configs[key] ?? "");
  const changed = (key: string) => key in editing && editing[key] !== (configs[key] ?? "");

  const entries: ConfigEntry[] = Object.keys(LABELS).map((key) => {
    const [label, help, type, options] = LABELS[key];
    return { key, value: "", label, help, description: dbDescriptions[key], type, options };
  });

  if (!loaded) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 bg-gray-800 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  const activeEntries = entries.filter((e) => e.key.startsWith(activeTab));

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-bold text-white">Configuration</h2>
          <p className="text-xs text-gray-500 mt-0.5">System-wide settings by category</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
        >
          <RotateCw size={12} /> Refresh
        </button>
      </div>

      <div className="flex gap-1 mb-4 border-b border-gray-800 pb-0">
        {CATEGORIES.map(({ key, label, icon: Icon }) => {
          const count = entries.filter((e) => e.key.startsWith(key)).length;
          if (!count) return null;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-t text-sm font-medium transition-colors ${
                activeTab === key
                  ? "bg-gray-800 text-white border-t border-l border-r border-gray-700"
                  : "text-gray-500 hover:text-gray-300 hover:bg-gray-800/50"
              }`}
            >
              <Icon size={14} className="flex-shrink-0" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          );
        })}
      </div>

      <div className="bg-gray-800/50 rounded-b rounded-r border border-gray-700/50 p-4">
        {activeEntries.map((entry) => {
          const val = displayValue(entry.key);
          const isChanged = changed(entry.key);
          const isSaving = saving[entry.key];

          return (
            <div
              key={entry.key}
              className="flex items-start justify-between gap-4 py-2.5 border-b border-gray-700/30 last:border-0"
            >
              <div className="min-w-0 flex-1">
                <div className="text-[13px] text-gray-200">{entry.label}</div>
                <div className="text-[11px] text-gray-500 mt-0.5">
                  {entry.description || entry.help}
                </div>
                {entry.description && entry.help && (
                  <div className="text-[11px] text-gray-600 mt-0.5">{entry.help}</div>
                )}
                <div className="text-[10px] text-gray-700 font-mono mt-0.5">{entry.key}</div>
              </div>
              <div className="flex-shrink-0">
                {entry.type === "toggle" ? (
                  <button
                    onClick={() => {
                      const v = String(val) === "true" ? "false" : "true";
                      apiClient.patch("/system/config", null, { params: { key: entry.key, value: v } }).then(() => {
                        setConfigs((prev) => ({ ...prev, [entry.key]: v }));
                      });
                    }}
                    className={`relative w-9 h-5 rounded-full transition-colors ${
                      String(val) === "true" ? "bg-blue-600" : "bg-gray-600"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                        String(val) === "true" ? "left-4" : "left-0.5"
                      }`}
                    />
                  </button>
                ) : entry.type === "select" ? (
                  <div className="flex items-center gap-1.5">
                    <select
                      value={val}
                      onChange={(e) => setEditing((prev) => ({ ...prev, [entry.key]: e.target.value }))}
                      className="w-44 px-2 py-1 bg-gray-700/70 border border-gray-600 rounded text-[13px] text-white outline-none focus:border-blue-500"
                    >
                      {entry.options?.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                    <button
                      onClick={() => save(entry.key)}
                      disabled={isSaving || !isChanged}
                      className="p-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-30 disabled:hover:bg-blue-600 transition-opacity"
                      title="Save"
                    >
                      {isSaving ? <RotateCw size={13} className="animate-spin" /> : <Save size={13} />}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <input
                      type={entry.type === "number" ? "number" : "text"}
                      value={val}
                      onChange={(e) => setEditing((prev) => ({ ...prev, [entry.key]: e.target.value }))}
                      min={entry.type === "number" ? 0 : undefined}
                      className="w-44 px-2 py-1 bg-gray-700/70 border border-gray-600 rounded text-[13px] text-white outline-none focus:border-blue-500"
                    />
                    <button
                      onClick={() => save(entry.key)}
                      disabled={isSaving || !isChanged}
                      className="p-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-30 disabled:hover:bg-blue-600 transition-opacity"
                      title="Save"
                    >
                      {isSaving ? <RotateCw size={13} className="animate-spin" /> : <Save size={13} />}
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {activeEntries.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-6">No settings in this category</p>
        )}

        {activeTab === "notification." && (
          <div className="mt-3 pt-3 border-t border-gray-700/30">
            <button
              onClick={testNotification}
              disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-xs text-gray-200"
            >
              <Bell size={11} /> {testing ? "Testing..." : "Test Notification"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
