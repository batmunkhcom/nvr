import { useState } from "react";
import { Download, Upload, Database } from "lucide-react";
import apiClient from "../../api/client";
import { useToast } from "../ui/Toast";

export default function BackupSection() {
  const { toast } = useToast();
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const [cameras, config, locations, schedules, users] = await Promise.all([
        apiClient.get("/cameras?per_page=100"),
        apiClient.get("/system/config"),
        apiClient.get("/locations"),
        apiClient.get("/recording-schedules"),
        apiClient.get("/users?per_page=100"),
      ]);
      const backup = {
        version: "1.0",
        exported_at: new Date().toISOString(),
        data: {
          cameras: cameras.data?.data || [],
          config: config.data?.data || {},
          locations: locations.data?.data || [],
          schedules: schedules.data?.data || [],
          users: users.data?.data || [],
        },
      };
      const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `nvr-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast("success", "Backup downloaded");
    } catch {
      toast("error", "Failed to export data");
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setImporting(true);
      try {
        const text = await file.text();
        const backup = JSON.parse(text);
        const data = backup.data || backup;
        let restored = 0;

        if (data.config) {
          const entries = typeof data.config === "object" ? Object.entries(data.config) : [];
          for (const [key, value] of entries) {
            try {
              await apiClient.patch("/system/config", null, { params: { key, value: String(value) } });
              restored++;
            } catch {}
          }
        }
        if (data.cameras?.length) {
          for (const cam of data.cameras) {
            try {
              await apiClient.post("/cameras", {
                name: cam.name,
                ip_address: cam.ip_address,
                username: cam.username || "admin",
                stream_main_uri: cam.stream_main_uri,
                stream_sub_uri: cam.stream_sub_uri,
                recording_mode: cam.recording_mode || "continuous",
                location_id: cam.location_id,
              });
              restored++;
            } catch {}
          }
        }
        toast("success", `Restored ${restored} items`);
      } catch {
        toast("error", "Invalid backup file");
      } finally {
        setImporting(false);
      }
    };
    input.click();
  };

  return (
    <div>
      <h2 className="text-lg font-bold text-white mb-4">Backup & Restore</h2>
      <p className="text-sm text-gray-400 mb-6">
        Export all system configuration and camera data as a JSON file. Use import to restore from a previous backup.
      </p>
      <div className="grid grid-cols-2 gap-4">
        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex flex-col items-center gap-3 p-6 bg-gray-800 rounded-xl border border-gray-700 hover:border-blue-600 disabled:opacity-50 transition-colors text-left"
        >
          <Download size={24} className="text-blue-400" />
          <div>
            <p className="text-sm font-medium text-white">{exporting ? "Exporting..." : "Export Backup"}</p>
            <p className="text-xs text-gray-500 mt-1">Download cameras, config, locations & schedules</p>
          </div>
        </button>
        <button
          onClick={handleImport}
          disabled={importing}
          className="flex flex-col items-center gap-3 p-6 bg-gray-800 rounded-xl border border-gray-700 hover:border-blue-600 disabled:opacity-50 transition-colors text-left"
        >
          <Upload size={24} className="text-green-400" />
          <div>
            <p className="text-sm font-medium text-white">{importing ? "Importing..." : "Import Backup"}</p>
            <p className="text-xs text-gray-500 mt-1">Restore from a previously exported .json file</p>
          </div>
        </button>
      </div>
    </div>
  );
}
