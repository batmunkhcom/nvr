import { useMemo, useState } from "react";
import { useLPRReadings } from "../hooks/useLPR";
import { useCameras } from "../hooks/useCameras";
import type { LPRReading } from "../hooks/useLPR";
import EmptyState from "../components/ui/EmptyState";
import { Car } from "lucide-react";

export default function LPRReadings() {
  const [cameraFilter, setCameraFilter] = useState("");
  const [searchPlate, setSearchPlate] = useState("");

  const params: Record<string, string | number> = {};
  if (cameraFilter) params.camera_id = cameraFilter;
  if (searchPlate) params.plate_number = searchPlate;

  const { data } = useLPRReadings(Object.keys(params).length > 0 ? params : undefined);
  const { data: cameras } = useCameras();

  const readings = data?.data || [];
  const total = data?.metadata?.total || readings.length;

  return (
    <div className="page-enter">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">License Plate Detection</h1>
        <span className="text-sm text-gray-400">{total} readings</span>
      </div>

      <div className="flex items-center gap-3 mb-4">
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
        <input
          type="text"
          placeholder="Search plate number..."
          value={searchPlate}
          onChange={(e) => setSearchPlate(e.target.value)}
          className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300 flex-1 max-w-xs"
        />
      </div>

      {!readings.length ? (
        <EmptyState
          icon={<Car size={28} />}
          title="No license plates detected"
          description="Enable LPR per-camera in camera settings to start detecting plates."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left py-2 px-3 text-gray-500 font-medium">Plate</th>
                <th className="text-left py-2 px-3 text-gray-500 font-medium">Camera</th>
                <th className="text-left py-2 px-3 text-gray-500 font-medium">Country</th>
                <th className="text-left py-2 px-3 text-gray-500 font-medium">Confidence</th>
                <th className="text-left py-2 px-3 text-gray-500 font-medium">Time</th>
              </tr>
            </thead>
            <tbody>
              {readings.map((r) => (
                <tr key={r.id} className="border-b border-gray-800/50 hover:bg-gray-800/50">
                  <td className="py-2 px-3 font-mono font-bold">{r.plate_number}</td>
                  <td className="py-2 px-3 text-gray-400">{r.camera_name}</td>
                  <td className="py-2 px-3">{r.country_code}</td>
                  <td className="py-2 px-3">
                    <span
                      className={
                        r.confidence >= 0.85
                          ? "text-green-400"
                          : r.confidence >= 0.7
                          ? "text-yellow-400"
                          : "text-red-400"
                      }
                    >
                      {Math.round(r.confidence * 100)}%
                    </span>
                  </td>
                  <td className="py-2 px-3 text-gray-500 text-xs">
                    {r.detected_at ? new Date(r.detected_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
