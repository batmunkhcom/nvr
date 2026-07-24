import { useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLatestMetrics, useCameraHistory, useNetworkSummary, useActiveAlerts, useStartMonitoring, useStopMonitoring } from "../hooks/useNetwork";
import NetworkSummaryBar from "../components/network/NetworkSummaryBar";
import CameraMetricCard from "../components/network/CameraMetricCard";
import NetworkChart from "../components/network/NetworkChart";
import NetworkAlertPanel from "../components/network/NetworkAlertPanel";
import { useNvrWebSocket } from "../hooks/useWebSocket";
import { Wifi, Play, Square, Activity, TrendingUp, AlertTriangle } from "lucide-react";

export default function NetworkDashboard() {
  const qc = useQueryClient();
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState("24h");
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);

  const { data: summary } = useNetworkSummary();
  const { data: metrics } = useLatestMetrics();
  const { data: historyData } = useCameraHistory(selectedCameraId, timeRange);
  const { data: alerts } = useActiveAlerts();
  const startMonitoring = useStartMonitoring();
  const stopMonitoring = useStopMonitoring();

  const onMetricUpdate = useCallback(
    (cameraId: string) => { qc.invalidateQueries({ queryKey: ["network", "metrics"] }); },
    [qc],
   );

  useNvrWebSocket(
    () => {},
    () => {},
    onMetricUpdate,
    );

  const locations = summary?.cameras_by_location ? Object.keys(summary.cameras_by_location) : [];

  const filteredMetrics = selectedLocation
    ? (metrics || []).filter((m: { location: string | null }) => m.location === selectedLocation)
    : metrics;

  const sparklineData = historyData?.metrics
    ?.slice(0, 50)
    .reverse()
    .map((m: any) => ({
      time: new Date(m.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      value: m.outbound_mbps ?? m.rtt_ms ?? m.packet_loss_pct,
     }));

  return (
    <div className="page-enter">
       <div className="flex items-center justify-between mb-4">
         <h1 className="text-2xl font-bold">Network Monitoring</h1>
          <div className="flex items-center gap-2">
            {startMonitoring.isPending ? (
              <button
               disabled
               className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm transition-colors disabled:opacity-50"
              >
               <Play size={14} /> Starting...
              </button>
            ) : (
              <button
               onClick={() => startMonitoring.mutate()}
               className="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm transition-colors disabled:opacity-50"
              >
               <Play size={14} /> Start Monitoring
              </button>
            )}
            {stopMonitoring.isPending ? (
              <button
               disabled
               className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded text-sm transition-colors disabled:opacity-50"
              >
               <Square size={14} /> Stopping...
              </button>
            ) : (
              <button
               onClick={() => stopMonitoring.mutate()}
               className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded text-sm transition-colors disabled:opacity-50"
              >
               <Square size={14} /> Stop Monitoring
              </button>
            )}
          </div>
       </div>

       {summary && <NetworkSummaryBar summary={summary} />}

       {alerts && alerts.length > 0 && <NetworkAlertPanel />}

       {locations.length > 0 && (
         <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-2">
           <button
             onClick={() => setSelectedLocation(null)}
             className={`px-3 py-1 rounded text-xs font-medium transition-colors flex-shrink-0 ${
               selectedLocation === null ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
             }`}
           >
            All Locations
           </button>
           {locations.map((loc) => (
             <button
               key={loc}
               onClick={() => setSelectedLocation(loc)}
               className={`px-3 py-1 rounded text-xs font-medium transition-colors flex-shrink-0 ${
                 selectedLocation === loc ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
               }`}
             >
               {loc}
             </button>
           ))}
         </div>
       )}

       <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
         <NetworkChart
           data={historyData?.metrics || []}
           title={selectedCameraId ? `Network Metrics — ${selectedCameraId}` : "Network Overview"}
           height={250}
         />

         <div className="bg-gray-900 rounded border border-gray-800 p-4">
           <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
             <Activity size={16} className="text-purple-400" />
             Camera Status Overview
           </h3>
           <div className="space-y-2">
             {(filteredMetrics || []).map((m: any) => (
               <button
                 key={m.camera_id}
                 onClick={() => setSelectedCameraId(selectedCameraId === m.camera_id ? null : m.camera_id)}
                 className={`w-full flex items-center justify-between p-2 rounded text-left transition-colors ${
                   selectedCameraId === m.camera_id ? "bg-blue-900/30 border border-blue-700" : "hover:bg-gray-800"
                 }`}
               >
                 <div className="flex items-center gap-2">
                   <span className={`w-2 h-2 rounded-full ${m.status === "online" ? "bg-green-400 animate-pulse" : m.status === "degraded" ? "bg-yellow-400" : "bg-red-400"}`} />
                   <div>
                     <div className="text-xs text-gray-200">{m.camera_name}</div>
                     {m.location && <div className="text-[10px] text-gray-500">{m.location}</div>}
                   </div>
                 </div>
                 <div className="flex items-center gap-3 text-xs text-gray-400">
                   <span>{m.outbound_mbps != null ? `${m.outbound_mbps.toFixed(1)} Mbps` : "—"}</span>
                   <span>{m.rtt_ms != null ? `${m.rtt_ms.toFixed(0)} ms` : "—"}</span>
                   <span className={`${m.packet_loss_pct != null && m.packet_loss_pct > 5 ? "text-red-400" : ""}`}>
                     {m.packet_loss_pct != null ? `${m.packet_loss_pct.toFixed(1)}%` : "—"}
                   </span>
                 </div>
               </button>
             ))}
           </div>
         </div>
       </div>

       {(filteredMetrics || []).length > 0 && (
         <>
           <div className="flex items-center justify-between mb-3">
             <h2 className="text-sm font-semibold text-gray-400 flex items-center gap-2">
               <TrendingUp size={14} /> Camera Metrics
             </h2>
             <div className="flex items-center gap-2">
               {["1h", "6h", "12h", "24h", "7d"].map((range) => (
                 <button
                   key={range}
                   onClick={() => setTimeRange(range)}
                   className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                     timeRange === range ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                   }`}
                 >
                   {range}
                 </button>
               ))}
             </div>
           </div>
           <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
             {(filteredMetrics || []).map((m: any) => (
               <CameraMetricCard
                 key={m.camera_id}
                 camera_id={m.camera_id}
                 camera_name={m.camera_name}
                 location={m.location}
                 status={m.status}
                 outbound_mbps={m.outbound_mbps}
                 rtt_ms={m.rtt_ms}
                 packet_loss_pct={m.packet_loss_pct}
                 fps_current={m.fps_current}
                 bitrate_current={m.bitrate_current}
                 recorded_at={m.recorded_at}
                 sparklineData={sparklineData}
               />
             ))}
           </div>
         </>
       )}

       {selectedCameraId && historyData && (
         <div className="mt-6">
           <NetworkChart
             data={historyData.metrics || []}
             title={`Detailed Metrics — ${historyData.camera_name}`}
             height={300}
           />
         </div>
       )}
     </div>
   );
}
