import { ReactNode } from "react";

export default function ChartCard({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="bg-gray-900 rounded border border-gray-800 p-4 flex flex-col">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-300">{title}</h3>
          {subtitle && <p className="text-[11px] text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        {right}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}

export function ChartEmpty({ message }: { message?: string }) {
  return (
    <div className="h-64 flex items-center justify-center text-sm text-gray-500">
      {message || "No data for this period."}
    </div>
  );
}

export const CHART_COLORS = {
  person: "#22c55e",
  vehicle: "#3b82f6",
  animal: "#eab308",
  livestock: "#a855f7",
  recording: "#f97316",
  segments: "#38bdf8",
  detections: "#f43f5e",
  motion: "#34d399",
};

export const chartTick = { fill: "#9ca3af", fontSize: 12 };

export const chartTooltipStyle = {
  backgroundColor: "#111827",
  border: "1px solid #374151",
  borderRadius: 8,
  fontSize: 12,
  color: "#e5e7eb",
};

export const chartGrid = "#1f2937";

export function formatDate(d: string): string {
  return d.slice(5); // YYYY-MM-DD -> MM-DD
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${bytes} B`;
}
