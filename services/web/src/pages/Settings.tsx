import { useState } from "react";
import { Settings as SettingsIcon, MapPin, Info, UserCog, Clock } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import LocationsSection from "../components/layout/LocationsSection";
import ConfigSection from "../components/config/ConfigSection";
import RecordingSchedulesSection from "../components/config/RecordingSchedulesSection";
import apiClient from "../api/client";
import { useQuery } from "@tanstack/react-query";

function SystemInfo() {
  const { data: health } = useQuery({
    queryKey: ["system", "health"],
    queryFn: () => apiClient.get("/system/health").then((r) => r.data?.data),
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gray-800 rounded p-3">
          <p className="text-xs text-gray-500">Version</p>
          <p className="text-sm font-mono text-white">{health?.version || "—"}</p>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <p className="text-xs text-gray-500">Uptime</p>
          <p className="text-sm font-mono text-white">{Math.round((health?.uptime_seconds || 0) / 3600)} hours</p>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <p className="text-xs text-gray-500">Database</p>
          <p className="text-sm font-mono text-green-400">{health?.checks?.database || "ok"}</p>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <p className="text-xs text-gray-500">Redis</p>
          <p className="text-sm font-mono text-green-400">{health?.checks?.redis || "ok"}</p>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <p className="text-xs text-gray-500">Cameras Online</p>
          <p className="text-sm font-mono text-white">{health?.cameras?.online || 0} / {health?.cameras?.total || 0}</p>
        </div>
        <div className="bg-gray-800 rounded p-3">
          <p className="text-xs text-gray-500">Compatible AI</p>
          <p className="text-sm font-mono text-blue-400">OpenAI / Ollama</p>
        </div>
      </div>
    </div>
  );
}

const TABS = [
  { key: "config", label: "Configuration", icon: SettingsIcon },
  { key: "locations", label: "Locations", icon: MapPin },
  { key: "schedules", label: "Schedules", icon: Clock },
  { key: "users", label: "Users", icon: UserCog },
  { key: "info", label: "System Info", icon: Info },
];

export default function Settings() {
  const [tab, setTab] = useState("config");
  const navigate = useNavigate();
  const location = useLocation();

  const handleTab = (key: string) => {
    if (key === "users") {
      navigate("/settings/users");
      return;
    }
    setTab(key);
  };

  if (location.pathname.includes("/settings/users")) {
    return null;
  }

  return (
    <div className="page-enter">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <div className="flex gap-1 mb-6 border-b border-gray-800 pb-0">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => handleTab(key)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-t text-sm font-medium transition-colors ${
              tab === key
                ? "bg-gray-900 text-white border-t border-l border-r border-gray-800"
                : "text-gray-500 hover:text-gray-300 hover:bg-gray-900/50"
            }`}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      <div className="bg-gray-900 rounded-b rounded-r border border-gray-800 p-6">
        {tab === "config" && <ConfigSection />}
        {tab === "locations" && <LocationsSection />}
        {tab === "schedules" && <RecordingSchedulesSection />}
        {tab === "info" && <SystemInfo />}
      </div>
    </div>
  );
}
