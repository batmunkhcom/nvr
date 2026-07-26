import { useState } from "react";
import { useCameras } from "../hooks/useCameras";
import { useCounterSummary, useCounterHourly, useCounterPerCamera } from "../hooks/useCounters";
import CounterCards from "../components/statistics/CounterCards";
import type { CounterHourly, CounterPerCamera } from "../hooks/useCounters";
import { PersonStanding, Car, PawPrint, Tractor, BarChart3, Camera } from "lucide-react";

function HourlyTable({ data }: { data: CounterHourly[] }) {
  if (!data.length) return <p className="text-sm text-gray-500">No data for this date.</p>;
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

function PerCameraGrid({ data }: { data: CounterPerCamera[] }) {
  if (!data.length) return <p className="text-sm text-gray-500">No cameras with counter data yet.</p>;
  const cats = [
    { key: "person" as const, icon: PersonStanding, color: "text-green-400", label: "Persons" },
    { key: "vehicle" as const, icon: Car, color: "text-blue-400", label: "Vehicles" },
    { key: "animal" as const, icon: PawPrint, color: "text-yellow-400", label: "Animals" },
    { key: "livestock" as const, icon: Tractor, color: "text-purple-400", label: "Livestock" },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {data.map((cam) => {
        const total = (cam.person ?? 0) + (cam.vehicle ?? 0) + (cam.animal ?? 0) + (cam.livestock ?? 0);
        return (
          <div key={cam.camera_id} className="bg-gray-900 rounded border border-gray-800 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Camera size={14} className="text-gray-400" />
              <span className="text-sm font-medium text-gray-200">{cam.camera_name}</span>
              <span className="text-[11px] text-gray-600 ml-auto">{total} total</span>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {cats.map((cat) => {
                const Icon = cat.icon;
                const val = cam[cat.key] ?? 0;
                return (
                  <div key={cat.key} className="text-center">
                    <Icon size={12} className={`mx-auto mb-0.5 ${cat.color}`} />
                    <div className="text-xs font-bold">{val}</div>
                    <div className="text-[9px] text-gray-500">{cat.label}</div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
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
  const { data: perCamera } = useCounterPerCamera(days);

  const hasHourly = cameraFilter && hourly && hourly.length > 0;
  const isAllCameras = !cameraFilter;

  const totalObjects = summary
    ? (summary.person ?? 0) + (summary.vehicle ?? 0) + (summary.animal ?? 0) + (summary.livestock ?? 0)
    : 0;

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
        {summary && (
          <span className="text-xs text-gray-500 ml-auto">
            {totalObjects.toLocaleString()} objects &middot; {days === 1 ? "today" : `last ${days} days`}
          </span>
        )}
      </div>

      {summary && (
        <>
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 size={16} className="text-blue-400" />
            <span className="text-sm font-medium text-gray-300">
              {isAllCameras ? "All Cameras" : (cameras || []).find(c => c.id === cameraFilter)?.name || "Camera"}
            </span>
            <span className="text-xs text-gray-500">
              {days === 1 ? "today" : `${days}-day summary`}
            </span>
          </div>
          <CounterCards data={summary} />
        </>
      )}

      {isAllCameras && perCamera && perCamera.length > 0 && (
        <div className="mt-6">
          <div className="flex items-center gap-2 mb-3">
            <Camera size={16} className="text-gray-400" />
            <span className="text-sm font-medium text-gray-300">Per Camera Breakdown</span>
            <span className="text-xs text-gray-500">({perCamera.length} cameras)</span>
          </div>
          <PerCameraGrid data={perCamera} />
        </div>
      )}

      {hasHourly && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-gray-400 mb-3">Hourly Breakdown — {todayISO}</h2>
          <HourlyTable data={hourly} />
        </div>
      )}
    </div>
  );
}
