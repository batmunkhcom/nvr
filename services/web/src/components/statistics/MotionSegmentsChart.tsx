import {
  ResponsiveContainer,
  BarChart,
  Bar,
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
} from "./ChartCard";

export default function MotionSegmentsChart({
  data,
  days,
}: {
  data: RecordingDaily[];
  days: number;
}) {
  if (!data.length) return <ChartEmpty />;

  const total = data.reduce((acc, r) => acc + r.segments, 0);

  return (
    <ChartCard
      title="Motion recording segments"
      subtitle={`${total.toLocaleString()} motion segments · last ${days} day${days === 1 ? "" : "s"}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
          <XAxis dataKey="date" tick={chartTick} tickFormatter={formatDate} stroke={chartGrid} />
          <YAxis tick={chartTick} allowDecimals={false} stroke={chartGrid} />
          <Tooltip
            contentStyle={chartTooltipStyle}
            labelFormatter={(l) => `Date: ${l}`}
            formatter={(value: any, name: any) => [value, name === "segments" ? "Segments" : name]}
          />
          <Bar dataKey="segments" name="segments" fill={CHART_COLORS.motion} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
