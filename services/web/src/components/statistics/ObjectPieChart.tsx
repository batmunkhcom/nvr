import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";
import type { CounterDaily } from "../../hooks/useCounters";
import ChartCard, {
  ChartEmpty,
  CHART_COLORS,
  chartTooltipStyle,
} from "./ChartCard";

const CATS = [
  { key: "person", label: "Person", color: CHART_COLORS.person },
  { key: "vehicle", label: "Vehicle", color: CHART_COLORS.vehicle },
  { key: "animal", label: "Animal", color: CHART_COLORS.animal },
  { key: "livestock", label: "Livestock", color: CHART_COLORS.livestock },
] as const;

export default function ObjectPieChart({
  data,
  days,
}: {
  data: CounterDaily[];
  days: number;
}) {
  if (!data.length) return <ChartEmpty />;

  const slices = CATS.map((c) => {
    const value = data.reduce((acc, r) => acc + (r[c.key] as number || 0), 0);
    return { name: c.label, value, color: c.color };
  }).filter((s) => s.value > 0);

  if (!slices.length) return <ChartEmpty />;
  const total = slices.reduce((acc, s) => acc + s.value, 0);

  return (
    <ChartCard
      title="Object distribution"
      subtitle={`Share of total objects · last ${days} day${days === 1 ? "" : "s"}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={slices}
            dataKey="value"
            nameKey="name"
            innerRadius="45%"
            outerRadius="75%"
            paddingAngle={2}
            stroke="#111827"
            isAnimationActive={false}
          >
            {slices.map((s) => (
              <Cell key={s.name} fill={s.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={chartTooltipStyle}
            formatter={(value: any, name: any) => [
              `${value.toLocaleString()} (${((value / total) * 100).toFixed(0)}%)`,
              name,
            ]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap justify-center gap-3 mt-2">
        {slices.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1 text-[11px] text-gray-400">
            <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
            {s.name} · {((s.value / total) * 100).toFixed(0)}%
          </span>
        ))}
      </div>
    </ChartCard>
  );
}
