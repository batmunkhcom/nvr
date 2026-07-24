import { useState, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useLatestMetrics,
  useCameraHistory,
  useOverlayHistory,
  useNetworkSummary,
  useActiveAlerts,
  useToggleMonitoring,
  useMonitorStatus,
} from "../hooks/useNetwork";
import NetworkMultiChart from "../components/network/NetworkMultiChart";
import NetworkAlertPanel from "../components/network/NetworkAlertPanel";
import NetworkSummaryBar from "../components/network/NetworkSummaryBar";
import { useNvrWebSocket } from "../hooks/useWebSocket";
import { Activity, Play, Pause } from "lucide-react";

const RANGE_OPTIONS = ["1h", "6h", "12h", "24h", "7d"] as const;

export default function NetworkDashboard() {
  const qc = useQueryClient();
  const [selectedCam, setSelectedCam] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<string>("24h");
  const [selectedLoc, setSelectedLoc] = useState<string | null>(null);

  const { data: summary } = useNetworkSummary();
  const { data: metrics } = useLatestMetrics();
  const { data: overlay } = useOverlayHistory(timeRange);
  const { data: singleHistory } = useCameraHistory(selectedCam, timeRange);
  const { data: alerts } = useActiveAlerts();
  const { data: monStatus } = useMonitorStatus();
  const toggle = useToggleMonitoring();

  useNvrWebSocket(
    () => {},
    () => {},
    () => {
      qc.invalidateQueries({ queryKey: ["network", "metrics"] });
      qc.invalidateQueries({ queryKey: ["network", "summary"] });
    },
  );

  const locations = useMemo(() => {
    if (!summary?.cameras_by_location) return [];
    return Object.keys(summary.cameras_by_location).filter(
      (l) => l !== "Unknown",
    );
  }, [summary]);

  const filtered = useMemo(() => {
    if (!metrics) return [];
    return selectedLoc
      ? metrics.filter((m) => m.location === selectedLoc)
      : metrics;
  }, [metrics, selectedLoc]);

  const running = monStatus?.running ?? false;

  return (
    <div className="page-enter">
      {/* header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Network Monitoring</h1>
        <button
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium ${
            running
              ? "bg-yellow-600/20 text-yellow-400 border border-yellow-600/40 hover:bg-yellow-600/30"
              : "bg-green-600 hover:bg-green-700 text-white"
          } disabled:opacity-50`}
          title={running ? "Pause" : "Start"}
        >
          {running ? <Pause size={14} /> : <Play size={14} />}
          {running ? "Pause" : "Start"}
        </button>
      </div>

      {/* summary */}
      {summary && <NetworkSummaryBar summary={summary} />}

      {/* alerts */}
      {alerts && alerts.length > 0 && <NetworkAlertPanel />}

      {/* location filter */}
      {locations.length >= 2 && (
        <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-2">
          <button
            onClick={() => setSelectedLoc(null)}
            className={`px-3 py-1 rounded text-xs font-medium ${
              !selectedLoc
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            All
          </button>
          {locations.map((loc) => {
            const lsum = summary?.cameras_by_location[loc];
            return (
              <button
                key={loc}
                onClick={() =>
                  setSelectedLoc(loc === selectedLoc ? null : loc)
                }
                className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1.5 ${
                  selectedLoc === loc
                    ? "bg-blue-600 text-white"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                }`}
              >
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: lsum?.color || "#3b82f6" }}
                />
                {loc}
                {lsum && (
                  <span className="text-[10px] opacity-60">
                    {lsum.online}/{lsum.total}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* overlay chart */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
            <Activity size={16} className="text-purple-400" />
            {selectedCam
              ? `Camera Detail — ${singleHistory?.camera_name ?? selectedCam}`
              : "All Cameras — Bandwidth"}
            {selectedCam && (
              <button
                onClick={() => setSelectedCam(null)}
                className="text-[10px] text-blue-400 hover:text-blue-300 ml-1"
              >
                ← Show all
              </button>
            )}
          </h3>
          <div className="flex items-center gap-1">
            {RANGE_OPTIONS.map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-2 py-0.5 rounded text-xs font-medium ${
                  timeRange === r
                    ? "bg-blue-600 text-white"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
        {overlay && overlay.length > 0 ? (
          <NetworkMultiChart
            series={
              selectedCam
                ? overlay.filter((s) => s.camera_id === selectedCam)
                : overlay
            }
            selectedId={selectedCam}
            height={260}
          />
        ) : (
          <div className="bg-gray-900 rounded border border-gray-800 p-6 text-center text-xs text-gray-500">
            {running
              ? "Collecting data... chart appears within 2 minutes"
              : "Monitor is paused. Press Start to begin."}
          </div>
        )}
      </div>

      {/* camera list */}
      {!filtered.length ? (
        <div className="bg-gray-900 rounded border border-gray-800 p-6 text-center text-xs text-gray-500">
          {running ? "Waiting for camera metrics..." : "Monitor is paused"}
        </div>
      ) : (
        <div className="space-y-1">
          <div className="flex items-center gap-3 px-3 py-1 text-[11px] text-gray-500 font-medium">
            <span className="w-3" />
            <span className="flex-1">Camera</span>
            <span className="w-14 text-right">In</span>
            <span className="w-14 text-right">Out</span>
            <span className="w-12 text-right">RTT</span>
            <span className="w-10 text-right">Loss</span>
          </div>
          {filtered.map((m) => {
            const isSelected = selectedCam === m.camera_id;
            const locColor = m.location_color || "#3b82f6";
            return (
              <button
                key={m.camera_id}
                onClick={() =>
                  setSelectedCam(
                    selectedCam === m.camera_id ? null : m.camera_id,
                  )
                }
                className={`w-full flex items-center gap-3 px-3 py-2 rounded text-left transition-all ${
                  isSelected
                    ? "bg-blue-900/20 border border-blue-700/50 ring-1 ring-blue-500/20"
                    : selectedCam
                      ? "bg-gray-900/60 border border-gray-800 hover:bg-gray-800/40 opacity-60"
                      : "bg-gray-900/60 border border-gray-800 hover:bg-gray-800/60"
                }`}
              >
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <span
                    className={`w-2.5 h-2.5 rounded-full ${
                      m.status === "online"
                        ? "bg-green-400 shadow-[0_0_6px_#4ade80]"
                        : m.status === "degraded"
                          ? "bg-yellow-400"
                          : m.status === "unknown"
                            ? "bg-gray-500"
                            : "bg-red-400"
                    }`}
                  />
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: locColor }}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <span
                    className={`text-sm ${isSelected ? "text-blue-200" : "text-gray-200"}`}
                  >
                    {m.camera_name}
                  </span>
                  {m.location && (
                    <span className="text-[10px] text-gray-500 ml-1.5">
                      {m.location}
                    </span>
                  )}
                </div>
                <span className="w-14 text-right text-xs tabular-nums text-blue-300">
                  {m.inbound_mbps != null
                    ? fmtMbps(m.inbound_mbps)
                    : "—"}
                </span>
                <span className="w-14 text-right text-xs tabular-nums text-purple-300">
                  {m.outbound_mbps != null
                    ? fmtMbps(m.outbound_mbps)
                    : "—"}
                </span>
                <span className="w-12 text-right text-xs tabular-nums text-gray-400">
                  {m.rtt_ms != null ? `${m.rtt_ms.toFixed(0)} ms` : "—"}
                </span>
                <span
                  className={`w-10 text-right text-xs tabular-nums ${
                    m.packet_loss_pct != null && m.packet_loss_pct > 5
                      ? "text-red-400"
                      : "text-gray-500"
                  }`}
                >
                  {m.packet_loss_pct != null
                    ? `${m.packet_loss_pct.toFixed(1)}%`
                    : "—"}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function fmtMbps(v: number): string {
  if (v >= 1) return `${v.toFixed(1)} Mbps`;
  if (v > 0) return `${Math.round(v * 1000)} Kbps`;
  return "0";
}
