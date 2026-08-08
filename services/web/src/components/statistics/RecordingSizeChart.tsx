import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { RecordingDaily } from "../../hooks/useRecordings";
import ChartCard, {
  ChartEmpty,
  CHART_COLORS,
  chartTick,
  chartTooltipStyle,
  chartGrid,
  formatDate,
  formatBytes,
} from "./ChartCard";

export default function RecordingSizeChart({
  data,
  days,
}: {
  data: RecordingDaily[];
  days: number;
}) {
  if (!data.length) return <ChartEmpty />;

  const total = data.reduce((acc, r) => acc + r.size_bytes, 0);
  const chartData = data.map((r) => ({ ...r, size_gb: +(r.size_bytes / 1024 ** 3).toFixed(2) }));

  return (
    <ChartCard
      title="Recording size"
      subtitle={`${formatBytes(total)} total · last ${days} day${days === 1 ? "" : "s"}`}
      right={
        <div className="flex flex-col items-end gap-1 text-[10px] text-gray-500">
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ background: CHART_COLORS.recording }} /> Size (GB)
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-0.5" style={{ background: CHART_COLORS.segments }} /> Segments
          </span>
        </div>
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
          <XAxis dataKey="date" tick={chartTick} tickFormatter={formatDate} stroke={chartGrid} />
          <YAxis yAxisId="size" tick={chartTick} allowDecimals={false} stroke={chartGrid} />
          <YAxis
            yAxisId="segments"
            orientation="right"
            tick={chartTick}
            allowDecimals={false}
            stroke={chartGrid}
            width={40}
          />
          <Tooltip
            contentStyle={chartTooltipStyle}
            labelFormatter={(l) => `Date: ${l}`}
            formatter={(value: any, name: any) => {
              if (name === "size_gb") return [`${value} GB`, "Size"];
              return [value, "Segments"];
            }}
          />
          <Bar yAxisId="size" dataKey="size_gb" name="size_gb" fill={CHART_COLORS.recording} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          <Line
            yAxisId="segments"
            type="linear"
            dataKey="segments"
            name="segments"
            stroke={CHART_COLORS.segments}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
