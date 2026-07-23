import { useEffect, useState } from "react";
import { Save, RotateCw } from "lucide-react";
import apiClient from "../../api/client";
import { useToast } from "../ui/Toast";

interface ConfigEntry {
  key: string;
  value: string | number | boolean;
  label: string;
  description?: string;
  type: "text" | "number" | "toggle";
}

const CATEGORIES: Record<string, string> = {
  "ui.": "User Interface",
  "camera.": "Camera",
  "mediamtx.": "MediaMTX",
  "recording.": "Recording",
  "ai.": "AI Engine",
};

const LABELS: Record<string, [string, string | undefined, "text" | "number" | "toggle"]> = {
  "ui.refresh_interval_s": ["Refresh Interval (s)", "Camera list auto-refresh period", "number"],
  "ui.theme": ["Theme", "UI color theme (dark/light)", "text"],
  "ui.language": ["Language", "Interface language (mn/en)", "text"],
  "camera.test_timeout_s": ["Test Timeout (s)", "RTSP auth check timeout", "number"],
  "camera.health_check_interval_s": ["Health Check Interval (s)", "Auto health-check loop period", "number"],
  "mediamtx.rtsp_url": ["MediaMTX RTSP URL", "Relay target for FFmpeg", "text"],
  "mediamtx.hls_url": ["MediaMTX HLS URL", "HLS base URL for web players", "text"],
  "recording.retention_days": ["Retention (days)", "Days to keep recordings", "number"],
  "ai.enabled": ["AI Detection", "Enable AI object detection engine", "toggle"],
  "ai.confidence_threshold": ["Confidence Threshold", "Minimum detection confidence (0–1)", "number"],
};

export default function ConfigSection() {
  const { toast } = useToast();
  const [configs, setConfigs] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [loaded, setLoaded] = useState(false);

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

  useEffect(() => {
    load();
  }, []);

  const save = async (key: string) => {
    const value = editing[key] ?? configs[key];
    setSaving((prev) => ({ ...prev, [key]: true }));
    try {
      await apiClient.patch("/system/config", null, { params: { key, value: String(value) } });
      setConfigs((prev) => ({ ...prev, [key]: String(value) }));
      setEditing((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      toast("success", "Saved");
    } catch {
      toast("error", "Failed to save");
    }
    setSaving((prev) => ({ ...prev, [key]: false }));
  };

  const displayValue = (key: string) =>
    key in editing ? editing[key] : (configs[key] ?? "");

  const changed = (key: string) =>
    key in editing && editing[key] !== (configs[key] ?? "");

  const entries: ConfigEntry[] = Object.keys(LABELS)
    .map((key) => {
      const [label, desc, type] = LABELS[key];
      return { key, value: "", label, description: desc, type };
    })
    .filter(() => true);

  const grouped = entries.reduce(
    (acc, entry) => {
      const cat = Object.keys(CATEGORIES).find((p) => entry.key.startsWith(p)) || "other";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(entry);
      return acc;
    },
    {} as Record<string, ConfigEntry[]>,
  );

  if (!loaded) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 bg-gray-800 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  const renderField = (entry: ConfigEntry) => {
    const val = displayValue(entry.key);
    const isChanged = changed(entry.key);
    const isSaving = saving[entry.key];

    if (entry.type === "toggle") {
      const isOn = String(val) === "true" || String(val).toLowerCase() === "true";
      return (
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              const newVal = isOn ? "false" : "true";
              setEditing((prev) => ({ ...prev, [entry.key]: newVal }));
              setConfigs((prev) => ({ ...prev, [entry.key]: String(val) }));
              // save immediately for toggle
              apiClient.patch("/system/config", null, { params: { key: entry.key, value: newVal } }).then(() => {
                setConfigs((prev) => ({ ...prev, [entry.key]: newVal }));
                setEditing((prev) => {
                  const next = { ...prev };
                  delete next[entry.key];
                  return next;
                });
              });
            }}
            className={`relative w-10 h-5 rounded-full transition-colors ${
              isOn ? "bg-blue-600" : "bg-gray-600"
            }`}
          >
            <span
              className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                isOn ? "left-5" : "left-0.5"
              }`}
            />
          </button>
          <span className="text-xs text-gray-400">{isOn ? "On" : "Off"}</span>
        </div>
      );
    }

    return (
      <div className="flex items-center gap-2">
        <input
          type={entry.type === "number" ? "number" : "text"}
          value={val}
          onChange={(e) =>
            setEditing((prev) => ({ ...prev, [entry.key]: e.target.value }))
          }
          min={entry.type === "number" ? 0 : undefined}
          className="px-2 py-1 bg-gray-700 border border-gray-600 rounded text-sm text-white w-48"
        />
        {isChanged && (
          <button
            onClick={() => save(entry.key)}
            disabled={isSaving}
            className="p-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
            title="Save"
          >
            {isSaving ? (
              <RotateCw size={14} className="animate-spin" />
            ) : (
              <Save size={14} />
            )}
          </button>
        )}
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold">System Configuration</h2>
        <button
          onClick={load}
          className="flex items-center gap-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
        >
          <RotateCw size={12} /> Refresh
        </button>
      </div>

      <div className="space-y-6">
        {Object.entries(grouped).map(([cat, groupEntries]) => (
          <div key={cat}>
            <h3 className="text-sm font-semibold text-gray-300 mb-2 border-b border-gray-700 pb-1">
              {CATEGORIES[cat] || cat}
            </h3>
            <div className="space-y-2">
              {groupEntries.map((entry) => (
                <div
                  key={entry.key}
                  className="flex items-center justify-between gap-4 py-1.5"
                >
                  <div className="min-w-0">
                    <div className="text-sm text-white">{entry.label}</div>
                    {entry.description && (
                      <div className="text-xs text-gray-500">{entry.description}</div>
                    )}
                    <div className="text-[10px] text-gray-600 font-mono">{entry.key}</div>
                  </div>
                  {renderField(entry)}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
