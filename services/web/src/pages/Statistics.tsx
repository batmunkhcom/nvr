import { useState } from "react";
import { useCameras } from "../hooks/useCameras";
import { useCounterSummary, useCounterHourly } from "../hooks/useCounters";
import CounterCards from "../components/statistics/CounterCards";
import type { CounterHourly } from "../hooks/useCounters";

function HourlyTable({ data }: { data: CounterHourly[] }) {
  if (!data.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="text-left py-2 px-3 text-gray-500 font-medium">Hour</th>
            <th className="text-left py-2 px-3 text-gray-500 font-medium">Persons</th>
            <th className="text-left py-2 px-3 text-gray-500 font-medium">Vehicles</th>
            <th className="text-left py-2 px-3 text-gray-500 font-medium">Animals</th>
            <th className="text-left py-2 px-3 text-gray-500 font-medium">Livestock</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.hour} className="border-b border-gray-800/50 hover:bg-gray-800/50">
              <td className="py-2 px-3 font-mono">{String(row.hour).padStart(2, "0")}:00</td>
              <td className="py-2 px-3">{row.person ?? 0}</td>
              <td className="py-2 px-3">{row.vehicle ?? 0}</td>
              <td className="py-2 px-3">{row.animal ?? 0}</td>
              <td className="py-2 px-3">{row.livestock ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function StatisticsPage() {
  const [cameraFilter, setCameraFilter] = useState("");
  const [days, setDays] = useState(7);
  const todayISO = new Date().toISOString().slice(0, 10);

  const { data: cameras } = useCameras();
  const { data: summary } = useCounterSummary(cameraFilter || undefined, days);
  const { data: hourly } = useCounterHourly(cameraFilter || "none", todayISO);

  const hasHourly = cameraFilter && hourly && hourly.length > 0;

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Object Statistics</h1>
      </div>

      <div className="flex items-center gap-3 mb-6">
        <select
          value={cameraFilter}
          onChange={(e) => setCameraFilter(e.target.value)}
          className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300"
        >
          <option value="">All Cameras</option>
          {(cameras || []).map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300"
        >
          <option value={1}>Today</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
        </select>
      </div>

      {summary && <CounterCards data={summary} />}

      {hasHourly && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-gray-400 mb-3">Hourly Breakdown — {todayISO}</h2>
          <HourlyTable data={hourly} />
        </div>
      )}
    </div>
  );
}
