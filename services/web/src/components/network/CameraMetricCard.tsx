import { useMemo } from "react";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

interface CameraMetricCardProps {
  camera_id: string;
  camera_name: string;
  location: string | null;
  status: string;
  outbound_mbps: number | null;
  rtt_ms: number | null;
  packet_loss_pct: number | null;
  fps_current: number | null;
  bitrate_current: number | null;
  recorded_at: string | null;
  sparklineData?: Array<{ time: string; value: number | null }>;
}

const statusColors: Record<string, string> = {
  online: "text-green-400",
  offline: "text-red-400",
  degraded: "text-yellow-400",
  unknown: "text-gray-400",
};

export default function CameraMetricCard({
  camera_name,
  location,
  status,
  outbound_mbps,
  rtt_ms,
  packet_loss_pct,
  fps_current,
  recorded_at,
  sparklineData,
}: CameraMetricCardProps) {
  const formattedTime = useMemo(() => {
    if (!recorded_at) return "—";
    const d = new Date(recorded_at);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }, [recorded_at]);

  const sparklineHeight = 40;
  const sparklineWidth = 120;

  const sparklinePaths = useMemo(() => {
    if (!sparklineData || sparklineData.length < 2) return "";
    const values = sparklineData.map((d) => d.value).filter((v) => v != null) as number[];
    if (values.length < 2) return "";
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = sparklineData.map((d, i) => {
      if (d.value == null) return "";
      const x = (i / (sparklineData.length - 1)) * sparklineWidth;
      const y = sparklineHeight - ((d.value - min) / range) * (sparklineHeight - 4) - 2;
      return `${x},${y}`;
    }).filter(Boolean);
    return points.join(" ");
  }, [sparklineData, sparklineWidth, sparklineHeight]);

  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-3 hover:border-gray-700 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${status === "online" ? "bg-green-400 animate-pulse" : status === "degraded" ? "bg-yellow-400" : "bg-red-400"}`} />
          <div>
            <div className="text-sm font-medium text-gray-200">{camera_name}</div>
            {location && <div className="text-[10px] text-gray-500">{location}</div>}
          </div>
        </div>
        <span className={`text-[10px] ${statusColors[status] || statusColors.unknown}`}>{status}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs mb-2">
        <div>
          <div className="text-gray-500 text-[10px]">BW</div>
          <div className="text-gray-200">{outbound_mbps != null ? `${outbound_mbps.toFixed(1)} Mbps` : "—"}</div>
        </div>
        <div>
          <div className="text-gray-500 text-[10px]">Latency</div>
          <div className="text-gray-200">{rtt_ms != null ? `${rtt_ms.toFixed(0)} ms` : "—"}</div>
        </div>
        <div>
          <div className="text-gray-500 text-[10px]">Loss</div>
          <div className={`text-gray-200 ${packet_loss_pct != null && packet_loss_pct > 5 ? "text-red-400" : ""}`}>
            {packet_loss_pct != null ? `${packet_loss_pct.toFixed(1)}%` : "—"}
          </div>
        </div>
      </div>

      {sparklinePaths && (
        <ResponsiveContainer width="100%" height={sparklineHeight}>
          <LineChart>
            <YAxis hide domain={["dataMin", "dataMax"]} />
            <Line type="monotone" data={sparklineData} stroke="#3B82F6" strokeWidth={1.5} dot={false} dataKey="value" />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div className="text-[10px] text-gray-600 mt-1">Updated: {formattedTime}</div>
    </div>
  );
}
