import { useEffect, useState } from "react";
import { Save, RotateCw, Bell, Monitor, Camera, Radio, Disc, MessageSquare, Brain } from "lucide-react";
import apiClient from "../../api/client";
import { useToast } from "../ui/Toast";

interface ConfigEntry {
  key: string;
  value: string | number | boolean;
  label: string;
  description?: string;
  type: "text" | "number" | "toggle";
}

const CATEGORIES: { prefix: string; label: string; icon: typeof Monitor }[] = [
  { prefix: "ui.", label: "User Interface", icon: Monitor },
  { prefix: "camera.", label: "Camera Defaults", icon: Camera },
  { prefix: "mediamtx.", label: "MediaMTX", icon: Radio },
  { prefix: "recording.", label: "Recording", icon: Disc },
  { prefix: "notification.", label: "Notifications", icon: MessageSquare },
  { prefix: "ai.", label: "AI Engine", icon: Brain },
];

const LABELS: Record<string, [string, string | undefined, "text" | "number" | "toggle"]> = {
  "ui.refresh_interval_s": ["Refresh Interval (s)", "Camera list auto-refresh period", "number"],
  "ui.theme": ["Theme", "UI color theme (dark/light)", "text"],
  "ui.language": ["Language", "Interface language (mn/en)", "text"],
  "camera.test_timeout_s": ["Test Timeout (s)", "RTSP auth check timeout", "number"],
  "camera.health_check_interval_s": ["Health Check Interval (s)", "Auto health-check loop period", "number"],
  "mediamtx.rtsp_url": ["RTSP URL", "Relay target for FFmpeg", "text"],
  "mediamtx.hls_url": ["HLS URL", "HLS base URL for web players", "text"],
  "recording.retention_days": ["Retention (days)", "Days to keep recordings", "number"],
  "notification.channels_enabled": ["Enabled Channels", 'JSON list, e.g. ["telegram","webhook"]', "text"],
  "notification.telegram_bot_token": ["Telegram Bot Token", "Create via @BotFather", "text"],
  "notification.telegram_chat_id": ["Telegram Chat ID", "Your user/group chat ID", "text"],
  "notification.webhook_url": ["Webhook URL", "HTTP endpoint for POST notifications", "text"],
  "ai.enabled": ["AI Detection", "Enable AI engine (OpenAI-compatible or Ollama)", "toggle"],
  "ai.provider": ["AI Provider", "openai or ollama", "text"],
  "ai.base_url": ["AI Base URL", "API endpoint URL", "text"],
  "ai.api_key": ["AI API Key", "Bearer token (empty for local Ollama)", "text"],
  "ai.model": ["AI Model", "gpt-4o-mini / llama3.2-vision / etc.", "text"],
  "ai.motion_detection_enabled": ["Motion Detection", "OpenCV pixel-change detection", "toggle"],
  "ai.confidence_threshold": ["Confidence Threshold", "Minimum detection confidence (0–1)", "number"],
};

export default function ConfigSection() {
  const { toast } = useToast();
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [loaded, setLoaded] = useState(false);
  const [testing, setTesting] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const load = async () => {
    try {
      const res = await apiClient.get("/system/config");
      setConfigs(res.data?.data || {});
      setEditing({});
    } catch {
      toast("error", "Failed to load configuration");
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
    const [label, desc, type] = LABELS[key];
    return { key, value: "", label, description: desc, type };
  });

  if (!loaded) {
    return (
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-40 bg-gray-800 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  const toggleCategory = (prefix: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(prefix) ? next.delete(prefix) : next.add(prefix);
      return next;
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-white">Configuration</h2>
          <p className="text-xs text-gray-500 mt-0.5">System-wide settings organized by category</p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
        >
          <RotateCw size={12} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CATEGORIES.map(({ prefix, label, icon: Icon }) => {
          const groupEntries = entries.filter((e) => e.key.startsWith(prefix));
          if (!groupEntries.length) return null;
          const isOpen = !collapsed.has(prefix);

          return (
            <div
              key={prefix}
              className="bg-gray-800/50 rounded-xl border border-gray-700/50 overflow-hidden transition-colors hover:border-gray-600/50"
            >
              <button
                onClick={() => toggleCategory(prefix)}
                className="w-full flex items-center gap-2.5 px-4 py-3 bg-gray-800/80 border-b border-gray-700/30 text-left"
              >
                <Icon size={15} className="text-blue-400 flex-shrink-0" />
                <span className="text-sm font-semibold text-gray-200">{label}</span>
                <span className="text-[10px] text-gray-600 ml-auto">
                  {groupEntries.length} setting{groupEntries.length > 1 ? "s" : ""}
                </span>
                <span className={`text-gray-500 text-xs transition-transform ${isOpen ? "rotate-0" : "-rotate-90"}`}>
                  ▼
                </span>
              </button>

              {isOpen && (
                <div className="p-4 space-y-2.5">
                  {groupEntries.map((entry) => {
                    const val = displayValue(entry.key);
                    const isChanged = changed(entry.key);
                    const isSaving = saving[entry.key];

                    return (
                      <div key={entry.key} className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="text-[13px] text-gray-200">{entry.label}</div>
                          {entry.description && (
                            <div className="text-[11px] text-gray-500 mt-0.5">{entry.description}</div>
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
                          ) : (
                            <div className="flex items-center gap-1.5">
                              <input
                                type={entry.type === "number" ? "number" : "text"}
                                value={val}
                                onChange={(e) => setEditing((prev) => ({ ...prev, [entry.key]: e.target.value }))}
                                min={entry.type === "number" ? 0 : undefined}
                                className="w-36 px-2 py-1 bg-gray-700/70 border border-gray-600 rounded text-[13px] text-white outline-none focus:border-blue-500"
                              />
                              {isChanged && (
                                <button
                                  onClick={() => save(entry.key)}
                                  disabled={isSaving}
                                  className="p-1 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
                                >
                                  {isSaving ? <RotateCw size={13} className="animate-spin" /> : <Save size={13} />}
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {prefix === "notification." && (
                    <button
                      onClick={testNotification}
                      disabled={testing}
                      className="mt-2 flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded text-xs text-gray-200"
                    >
                      <Bell size={11} /> {testing ? "Testing..." : "Test Notification"}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
