import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface NetworkChartProps {
  points: Array<{
    recorded_at: string | null;
    inbound_mbps?: number | null;
    outbound_mbps?: number | null;
    rtt_ms?: number | null;
    packet_loss_pct?: number | null;
  }>;
  title: string;
  height?: number;
}

function formatTime(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function NetworkChart({ points, title, height = 200 }: NetworkChartProps) {
  const chartData = useMemo(() => {
    return [...points].reverse().map((d) => ({
      time: formatTime(d.recorded_at),
      inbound: d.inbound_mbps ?? null,
      outbound: d.outbound_mbps ?? null,
      rtt: d.rtt_ms ?? null,
      loss: d.packet_loss_pct ?? null,
    }));
  }, [points]);

  const hasBandwidth = points.some((d) => d.inbound_mbps != null || d.outbound_mbps != null);
  const hasLatency = points.some((d) => d.rtt_ms != null);
  const hasLoss = points.some((d) => d.packet_loss_pct != null);

  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-3">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="time" stroke="#6B7280" fontSize={10} tickMargin={5} />
          <YAxis stroke="#6B7280" fontSize={10} />
          <Tooltip
            contentStyle={{ backgroundColor: "#1F2937", border: "1px solid #374151", borderRadius: "4px", fontSize: "12px" }}
            labelStyle={{ color: "#D1D5DB" }}
          />
          <Legend wrapperStyle={{ fontSize: "11px" }} />
          {hasBandwidth && (
            <>
              <Line type="monotone" dataKey="inbound" stroke="#3B82F6" strokeWidth={1.5} dot={false} name="In (Mbps)" />
              <Line type="monotone" dataKey="outbound" stroke="#10B981" strokeWidth={1.5} dot={false} name="Out (Mbps)" />
            </>
          )}
          {hasLatency && (
            <Line type="monotone" dataKey="rtt" stroke="#F59E0B" strokeWidth={1.5} dot={false} name="RTT (ms)" />
          )}
          {hasLoss && (
            <Line type="monotone" dataKey="loss" stroke="#EF4444" strokeWidth={1.5} dot={false} name="Loss (%)" />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
