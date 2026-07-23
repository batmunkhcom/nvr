import { useState } from "react";
import { Settings as SettingsIcon, Info, Download, Server } from "lucide-react";
import ConfigSection from "../components/config/ConfigSection";
import SystemInfoPanel from "../components/config/SystemInfoPanel";
import BackupSection from "../components/config/BackupSection";

const SECTIONS = [
  { key: "config", label: "Configuration", icon: SettingsIcon, desc: "UI, Camera, AI, Recording & Notification preferences" },
  { key: "info", label: "System Info", icon: Info, desc: "Version, uptime, and health status" },
  { key: "backup", label: "Backup & Restore", icon: Download, desc: "Export/import all configuration and data" },
];

export default function Settings() {
  const [active, setActive] = useState("config");

  return (
    <div className="page-enter flex h-full gap-6">
      <aside className="w-60 flex-shrink-0">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3 px-1">
          Settings
        </h2>
        <nav className="space-y-0.5">
          {SECTIONS.map(({ key, label, icon: Icon, desc }) => (
            <button
              key={key}
              onClick={() => setActive(key)}
              className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors ${
                active === key
                  ? "bg-blue-600/20 border border-blue-700/50 text-blue-300"
                  : "hover:bg-gray-800 text-gray-400 border border-transparent"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Icon size={16} className="flex-shrink-0" />
                <span className="text-sm font-medium">{label}</span>
              </div>
              {active === key && (
                <p className="text-xs text-blue-400/60 mt-0.5 ml-7">{desc}</p>
              )}
            </button>
          ))}
        </nav>
      </aside>

      <div className="flex-1 min-w-0 bg-gray-900 rounded-xl border border-gray-800 p-6">
        {active === "config" && <ConfigSection />}
        {active === "info" && <SystemInfoPanel />}
        {active === "backup" && <BackupSection />}
      </div>
    </div>
  );
}
