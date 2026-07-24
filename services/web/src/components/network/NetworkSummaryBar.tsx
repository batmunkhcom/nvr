import { NetworkDashboardSummary } from "../../types/network";
import { Wifi, Activity, AlertTriangle, Server } from "lucide-react";

interface NetworkSummaryBarProps {
  summary: NetworkDashboardSummary;
}

export default function NetworkSummaryBar({ summary }: NetworkSummaryBarProps) {
  const { total_cameras, online_cameras, degraded_cameras, offline_cameras, avg_bandwidth_mbps, avg_latency_ms, active_alerts, alerts_by_severity } = summary;

  return (
    <div className="grid grid-cols-2 md:grid-cols-7 gap-3 mb-6">
      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Server size={14} className="text-blue-400" /> Cameras
        </div>
        <div className="text-lg font-bold">
          <span className="text-green-400">{online_cameras}</span>
          <span className="text-gray-500">/{total_cameras}</span>
        </div>
        {degraded_cameras > 0 && (
          <div className="text-[10px] text-yellow-500 mt-0.5">{degraded_cameras} degraded</div>
        )}
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Wifi size={14} className="text-green-400" /> Bandwidth
        </div>
        <div className="text-lg font-bold">
          {avg_bandwidth_mbps != null ? `${avg_bandwidth_mbps.toFixed(1)} Mbps` : "—"}
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">average</div>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Activity size={14} className="text-purple-400" /> Latency
        </div>
        <div className="text-lg font-bold">
          {avg_latency_ms != null ? `${avg_latency_ms.toFixed(0)} ms` : "—"}
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">average</div>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <AlertTriangle size={14} className="text-orange-400" /> Alerts
        </div>
        <div className="text-lg font-bold">
          {active_alerts > 0 ? (
            <>
              <span className="text-red-400">{alerts_by_severity.critical}</span>
              <span className="text-yellow-500">/{alerts_by_severity.warning}</span>
            </>
          ) : (
            <span className="text-green-400">0</span>
          )}
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">active</div>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Wifi size={14} className="text-green-400" /> Online
        </div>
        <div className="text-lg font-bold text-green-400">{online_cameras}</div>
        <div className="text-[10px] text-gray-500 mt-0.5">connected</div>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Activity size={14} className="text-yellow-400" /> Degraded
        </div>
        <div className="text-lg font-bold text-yellow-400">{degraded_cameras}</div>
        <div className="text-[10px] text-gray-500 mt-0.5">issues</div>
      </div>

      <div className="bg-gray-900 rounded border border-gray-800 p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <AlertTriangle size={14} className="text-red-400" /> Offline
        </div>
        <div className="text-lg font-bold text-red-400">{offline_cameras}</div>
        <div className="text-[10px] text-gray-500 mt-0.5">disconnected</div>
      </div>
    </div>
  );
}
