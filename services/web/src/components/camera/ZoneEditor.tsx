import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, Trash2, Check, X, Loader2 } from "lucide-react";
import apiClient from "../../api/client";

export interface AiZone {
  name: string;
  points: [number, number][]; // normalized 0-1 coordinates
}

interface Props {
  cameraId: string;
  zones: AiZone[];
  onChange: (zones: AiZone[]) => void;
}

const CLOSE_DISTANCE = 0.03; // normalized distance to first point = close polygon

export default function ZoneEditor({ cameraId, zones, onChange }: Props) {
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [loadingSnap, setLoadingSnap] = useState(false);
  const [snapError, setSnapError] = useState("");
  const [drawing, setDrawing] = useState<[number, number][] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadSnapshot = useCallback(async () => {
    setLoadingSnap(true);
    setSnapError("");
    try {
      const res = await apiClient.post(`/cameras/${cameraId}/snapshot`);
      setSnapshot(res.data?.data?.snapshot_url || null);
    } catch {
      setSnapError("Snapshot unavailable (camera offline?) — draw zones on a blank canvas");
      setSnapshot(null);
    }
    setLoadingSnap(false);
  }, [cameraId]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  const toNormalized = (e: React.MouseEvent): [number, number] => {
    const rect = containerRef.current!.getBoundingClientRect();
    const x = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    const y = Math.min(Math.max((e.clientY - rect.top) / rect.height, 0), 1);
    return [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000];
  };

  const handleClick = (e: React.MouseEvent) => {
    if (drawing === null) return;
    const [x, y] = toNormalized(e);
    // click near the first point closes the polygon
    if (drawing.length >= 3) {
      const [fx, fy] = drawing[0];
      if (Math.hypot(x - fx, y - fy) < CLOSE_DISTANCE) {
        closePolygon();
        return;
      }
    }
    setDrawing([...drawing, [x, y]]);
  };

  const closePolygon = () => {
    if (drawing && drawing.length >= 3) {
      onChange([...zones, { name: `Zone ${zones.length + 1}`, points: drawing }]);
    }
    setDrawing(null);
  };

  const removeZone = (idx: number) => {
    onChange(zones.filter((_, i) => i !== idx));
  };

  const renameZone = (idx: number, name: string) => {
    onChange(zones.map((z, i) => (i === idx ? { ...z, name } : z)));
  };

  const pts = (points: [number, number][]) =>
    points.map(([x, y]) => `${x * 100},${y * 100}`).join(" ");

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs text-gray-400">Detection Zones</label>
        {drawing === null ? (
          <button
            type="button"
            onClick={() => setDrawing([])}
            className="flex items-center gap-1 px-2 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs text-white"
          >
            <Plus size={12} /> Add Zone
          </button>
        ) : (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={closePolygon}
              disabled={drawing.length < 3}
              className="flex items-center gap-1 px-2 py-1 bg-green-600 hover:bg-green-700 disabled:opacity-40 rounded text-xs text-white"
            >
              <Check size={12} /> Done ({drawing.length} pts)
            </button>
            <button
              type="button"
              onClick={() => setDrawing(null)}
              className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-200"
            >
              <X size={12} /> Cancel
            </button>
          </div>
        )}
      </div>

      <div
        ref={containerRef}
        onClick={handleClick}
        className={`relative w-full aspect-video bg-gray-950 rounded overflow-hidden border ${
          drawing !== null ? "border-blue-500 cursor-crosshair" : "border-gray-700"
        }`}
      >
        {loadingSnap && (
          <div className="absolute inset-0 flex items-center justify-center text-gray-500">
            <Loader2 size={20} className="animate-spin" />
          </div>
        )}
        {!loadingSnap && snapshot && (
          <img
            src={snapshot}
            alt="camera"
            className="absolute inset-0 w-full h-full object-contain pointer-events-none"
            draggable={false}
          />
        )}
        {!loadingSnap && snapError && (
          <p className="absolute inset-x-0 top-1 text-center text-[11px] text-yellow-500/80 px-2">
            {snapError}
          </p>
        )}

        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 w-full h-full pointer-events-none"
        >
          {zones.map((z, i) => (
            <polygon
              key={i}
              points={pts(z.points)}
              fill="rgba(59,130,246,0.22)"
              stroke="#3b82f6"
              strokeWidth="0.5"
            />
          ))}
          {drawing !== null && drawing.length > 0 && (
            <>
              <polyline
                points={pts(drawing)}
                fill="none"
                stroke="#22c55e"
                strokeWidth="0.5"
              />
              {drawing.map(([x, y], i) => (
                <circle
                  key={i}
                  cx={x * 100}
                  cy={y * 100}
                  r={i === 0 ? 1.6 : 1.1}
                  fill={i === 0 ? "#f59e0b" : "#22c55e"}
                />
              ))}
            </>
          )}
        </svg>
      </div>

      {drawing !== null && (
        <p className="text-[11px] text-green-400 mt-1">
          Click to add points ({drawing.length}/3+). Click the orange first point or Done to close the zone.
        </p>
      )}

      {zones.length > 0 && (
        <div className="mt-2 space-y-1">
          {zones.map((z, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-sm bg-blue-500/60 border border-blue-400 flex-shrink-0" />
              <input
                type="text"
                value={z.name}
                onChange={(e) => renameZone(i, e.target.value)}
                className="flex-1 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-xs text-gray-200 outline-none focus:border-blue-500"
              />
              <span className="text-[10px] text-gray-500">{z.points.length} pts</span>
              <button
                type="button"
                onClick={() => removeZone(i)}
                className="p-1 text-gray-500 hover:text-red-400"
                title="Delete zone"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] text-gray-500 mt-1.5 leading-snug">
        Only objects inside a zone trigger AI events. No zones = the whole frame is watched.
        Draw around gates, driveways, or areas you care about to cut false alarms.
      </p>
    </div>
  );
}
