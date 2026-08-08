import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import type { EventDaily } from "../../hooks/useEvents";
import ChartCard, {
  ChartEmpty,
  CHART_COLORS,
  chartTick,
  chartTooltipStyle,
  chartGrid,
  formatDate,
} from "./ChartCard";

export default function MotionDetectionsChart({
  data,
  days,
}: {
  data: EventDaily[];
  days: number;
}) {
  if (!data.length) return <ChartEmpty />;

  const total = data.reduce((acc, r) => acc + r.detections, 0);

  return (
    <ChartCard
      title="Motion detections (AI)"
      subtitle={`${total.toLocaleString()} detections · last ${days} day${days === 1 ? "" : "s"}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <defs>
            <linearGradient id="detGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_COLORS.detections} stopOpacity={0.35} />
              <stop offset="100%" stopColor={CHART_COLORS.detections} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={chartGrid} />
          <XAxis dataKey="date" tick={chartTick} tickFormatter={formatDate} stroke={chartGrid} />
          <YAxis tick={chartTick} allowDecimals={false} stroke={chartGrid} />
          <Tooltip
            contentStyle={chartTooltipStyle}
            labelFormatter={(l) => `Date: ${l}`}
            formatter={(value: any, name: any) => [value, name === "detections" ? "Detections" : name]}
          />
          <Area
            type="linear"
            dataKey="detections"
            name="detections"
            stroke={CHART_COLORS.detections}
            strokeWidth={2}
            fill="url(#detGrad)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
