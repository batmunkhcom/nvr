import { NetworkDashboardSummary } from "../../types/network";
import { Wifi, Activity, AlertTriangle, Server, ArrowDown, ArrowUp } from "lucide-react";

interface NetworkSummaryBarProps {
  summary: NetworkDashboardSummary;
}

export default function NetworkSummaryBar({ summary }: NetworkSummaryBarProps) {
  const {
    total_cameras, online_cameras, degraded_cameras, offline_cameras,
    total_inbound_mbps, total_outbound_mbps, avg_latency_ms,
    active_alerts, alerts_by_severity,
  } = summary;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Server size={14} className="text-blue-400" /> Cameras
        </div>
        <div className="text-lg font-bold">
          <span className="text-green-400">{online_cameras}</span>
          <span className="text-gray-500">/{total_cameras}</span>
        </div>
        {(degraded_cameras > 0 || offline_cameras > 0) && (
          <div className="text-[10px] text-gray-500 mt-0.5">
            {degraded_cameras > 0 && <span className="text-yellow-500">{degraded_cameras} degraded </span>}
            {offline_cameras > 0 && <span className="text-red-400">{offline_cameras} offline</span>}
          </div>
        )}
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <ArrowDown size={14} className="text-blue-400" /> Inbound
        </div>
        <div className="text-lg font-bold text-blue-300">
          {fmtBW(total_inbound_mbps)}
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">total cam→server</div>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <ArrowUp size={14} className="text-purple-400" /> Outbound
        </div>
        <div className="text-lg font-bold text-purple-300">
          {fmtBW(total_outbound_mbps)}
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">total server→client</div>
      </div>
    </div>
  );
}

function fmtBW(v: number): string {
  if (v >= 1) return `${v.toFixed(1)} Mbps`;
  if (v > 0) return `${Math.round(v * 1000)} Kbps`;
  return "—";
}
