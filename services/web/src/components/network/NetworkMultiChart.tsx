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

  const camNames = useMemo(() => series.map((s) => s.camera_name), [series]);

  const colorMap = useMemo(() => {
    const m: Record<string, string> = {};
    for (const s of series) {
      m[s.camera_name] = s.color;
    }
    return m;
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
          <Legend
            wrapperStyle={{ fontSize: "10px" }}
            onClick={(e: any) => {
              /* allow toggling legend items */
            }}
          />
          {camNames.map((name) => {
            const isDimmed = selectedId != null && !series.some((s) => s.camera_name === name && s.camera_id === selectedId);
            return (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={colorMap[name] || "#3b82f6"}
                strokeWidth={isDimmed ? 0.5 : 2}
                dot={false}
                name={name}
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
