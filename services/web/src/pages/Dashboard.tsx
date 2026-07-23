import CameraGrid from "../components/camera/CameraGrid";
import { useCameras } from "../hooks/useCameras";
import { useStorageUsage } from "../hooks/useRecordings";
import { useEvents } from "../hooks/useEvents";
import { useNvrWebSocket } from "../hooks/useWebSocket";
import apiClient from "../api/client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Video, HardDrive, Bell, Film, AlertTriangle } from "lucide-react";
import { useCallback } from "react";

function fmtBytes(bytes: number) {
  if (!bytes || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
  return `${val.toFixed(1)} ${units[i]}`;
}

export default function Dashboard() {
  const { data: cameras } = useCameras();
  const usage = useStorageUsage();
  const { data: events } = useEvents();
  const qc = useQueryClient();

  const onCameraStatus = useCallback(
    () => { qc.invalidateQueries({ queryKey: ["cameras"] }); },
    [qc],
  );
  const onEvent = useCallback(
    () => { qc.invalidateQueries({ queryKey: ["events"] }); },
    [qc],
  );
  useNvrWebSocket(onCameraStatus, onEvent);

  const stats = useQuery({
    queryKey: ["recordings", "stats"],
    queryFn: () => apiClient.get("/recordings/stats").then((r) => r.data?.data),
    refetchInterval: 60_000,
  });

  const cameraList = cameras || [];
  const online = cameraList.filter((c) => c.status === "online").length;
  const offline = cameraList.filter((c) => c.status === "offline").length;
  const degraded = cameraList.filter((c) => c.status === "degraded").length;
  const total = cameraList.length;

  const eventList = events || [];
  const recentEvents = eventList.filter((e: { event_type: string }) =>
    e.event_type === "motion_detected"
  ).length;

  const storagePct = usage.data?.total_bytes
    ? Math.round((usage.data.used_bytes / usage.data.total_bytes) * 100)
    : 0;

  const statsData = stats.data as Record<string, number> | undefined;

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <div className="bg-gray-900 rounded border border-gray-800 p-3">
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
            <Video size={14} className="text-green-400" /> Cameras
          </div>
          <div className="text-lg font-bold">
            <span className="text-green-400">{online}</span>
            <span className="text-gray-500">/{total}</span>
          </div>
          {degraded > 0 && (
            <div className="text-[10px] text-yellow-500 mt-0.5">{degraded} degraded</div>
          )}
          {offline > 0 && (
            <div className="text-[10px] text-red-500">{offline} offline</div>
          )}
        </div>

        <div className="bg-gray-900 rounded border border-gray-800 p-3">
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
            <HardDrive size={14} className="text-blue-400" /> Storage
          </div>
          <div className="text-lg font-bold">
            {usage.data ? `${storagePct}%` : "—"}
          </div>
          <div className="text-[10px] text-gray-500 mt-0.5">
            {usage.data ? fmtBytes(usage.data.free_bytes) : "—"} free
          </div>
        </div>

        <div className="bg-gray-900 rounded border border-gray-800 p-3">
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
            <Film size={14} className="text-purple-400" /> Recordings
          </div>
          <div className="text-lg font-bold">{statsData?.recordings_24h ?? "—"}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">last 24h</div>
        </div>

        <div className="bg-gray-900 rounded border border-gray-800 p-3">
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
            <Bell size={14} className="text-yellow-400" /> Events
          </div>
          <div className="text-lg font-bold">{recentEvents}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">motion detected</div>
        </div>

        <div className="bg-gray-900 rounded border border-gray-800 p-3">
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
            <AlertTriangle size={14} className="text-orange-400" /> Storage Rate
          </div>
          <div className="text-lg font-bold">
            {statsData ? fmtBytes(statsData.storage_bytes_24h ?? 0) : "—"}
          </div>
          <div className="text-[10px] text-gray-500 mt-0.5">24h write volume</div>
        </div>
      </div>

      <h2 className="text-sm font-semibold text-gray-400 mb-3">Camera Grid</h2>
      <CameraGrid />
    </div>
  );
}
