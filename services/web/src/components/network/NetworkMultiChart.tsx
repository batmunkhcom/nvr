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
import type { OverlaySeries } from "../../types/network";
const CAM_COLORS = [
  "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#84cc16", "#6366f1",
  "#14b8a6", "#e11d48", "#a855f7", "#64748b", "#0ea5e9",
  "#d946ef", "#10b981", "#f43f5e", "#8b82f6", "#eab308",
];

interface Props {
  series: OverlaySeries[];
  selectedId: string | null;
  height?: number;
}

function fmtTime(ts: string | null): string {
  if (!ts) return "";
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function NetworkMultiChart({ series, selectedId, height = 260 }: Props) {
  const merged = useMemo(() => {
    const timeMap: Record<string, Record<string, number | null>> = {};
    const allCams = new Set<string>();

    for (const s of series) {
      allCams.add(s.camera_name);
      for (const p of s.points) {
        const t = p.recorded_at || "";
        if (!timeMap[t]) timeMap[t] = {};
        timeMap[t][s.camera_name] = p.inbound_mbps;
      }
    }

    return Object.entries(timeMap)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([time, vals]) => ({ time: fmtTime(time), ...vals }));
  }, [series]);

  const camMeta = useMemo(() => {
    return series.map((s, i) => ({
      key: s.camera_id,
      name: s.camera_name,
      color: CAM_COLORS[i % CAM_COLORS.length],
      location: s.location,
      legendName: s.location ? `${s.camera_name} · ${s.location}` : s.camera_name,
    }));
  }, [series]);

  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-4">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={merged}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="time"
            stroke="#6B7280"
            fontSize={10}
            tickMargin={5}
            interval="preserveStartEnd"
          />
          <YAxis
            stroke="#6B7280"
            fontSize={10}
            tickFormatter={(v: number) => `${v.toFixed(0)}`}
            label={{ value: "Mbps", angle: -90, position: "insideLeft", style: { fill: "#6B7280", fontSize: 10 } }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1F2937",
              border: "1px solid #374151",
              borderRadius: "4px",
              fontSize: "12px",
            }}
            labelStyle={{ color: "#D1D5DB" }}
          />
          <Legend wrapperStyle={{ fontSize: "10px" }} />
          {camMeta.map((meta) => {
            const isDimmed = selectedId != null && meta.key !== selectedId;
            return (
              <Line
                key={meta.key}
                type="monotone"
                dataKey={meta.name}
                stroke={meta.color}
                strokeWidth={isDimmed ? 0.5 : 2}
                dot={false}
                name={meta.legendName}
                opacity={isDimmed ? 0.15 : 1}
                activeDot={{ r: 3 }}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
