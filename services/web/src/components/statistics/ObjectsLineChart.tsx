import { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { CounterDaily } from "../../hooks/useCounters";
import ChartCard, {
  ChartEmpty,
  CHART_COLORS,
  chartTick,
  chartTooltipStyle,
  chartGrid,
  formatDate,
} from "./ChartCard";

const SERIES = [
  { key: "person", label: "Person", color: CHART_COLORS.person },
  { key: "vehicle", label: "Vehicle", color: CHART_COLORS.vehicle },
  { key: "animal", label: "Animal", color: CHART_COLORS.animal },
  { key: "livestock", label: "Livestock", color: CHART_COLORS.livestock },
] as const;

export default function ObjectsLineChart({ data, days }: { data: CounterDaily[]; days: number }) {
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const toggle = (key: string) => setHidden((h) => ({ ...h, [key]: !h[key] }));

  if (!data.length) return <ChartEmpty />;

  const visibleCount = SERIES.filter((s) => !hidden[s.key]).length;

  return (
    <ChartCard
      title="Objects over time"
      subtitle={`Daily detections per object type · last ${days} day${days === 1 ? "" : "s"}`}
      right={
        <div className="flex flex-wrap gap-1.5 justify-end">
          {SERIES.map((s) => {
            const off = !!hidden[s.key];
            return (
              <button
                key={s.key}
                onClick={() => toggle(s.key)}
                title={`${off ? "Show" : "Hide"} ${s.label}`}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border transition-colors ${
                  off
                    ? "bg-gray-800 border-gray-700 text-gray-500 line-through"
                    : "bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-500"
                }`}
              >
                <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
                {s.label}
              </button>
            );
          })}
        </div>
      }
    >
      {visibleCount === 0 ? (
        <ChartEmpty message="All object types are hidden. Click a label to show it." />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
            <XAxis
              dataKey="date"
              tick={chartTick}
              tickFormatter={formatDate}
              stroke={chartGrid}
            />
            <YAxis tick={chartTick} allowDecimals={false} stroke={chartGrid} />
            <Tooltip
              contentStyle={chartTooltipStyle}
              labelFormatter={(l) => `Date: ${l}`}
              formatter={(value, name) => [
                `${value} (${name})`,
              ]}
            />
            {SERIES.map((s) =>
              hidden[s.key] ? null : (
                <Line
                  key={s.key}
                  type="linear"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              )
            )}
          </LineChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
