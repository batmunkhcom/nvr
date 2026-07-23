import { useState, useMemo, useCallback, useRef, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useCameras, useCameraMutations } from "../../hooks/useCameras";
import { useUiPreference } from "../../hooks/useUiPreference";
import { useEvents } from "../../hooks/useEvents";
import { Camera } from "../../types/camera";
import { LayoutGrid, Play, MoreVertical, Wifi, Pencil, Trash2, MonitorPlay, GripVertical } from "lucide-react";
import MiniLivePreview from "./MiniLivePreview";
import EmptyState from "../ui/EmptyState";
import { useConfirm } from "../ui/ConfirmDialog";

const statusColors: Record<string, string> = {
  online: "bg-success",
  offline: "bg-danger",
  degraded: "bg-warning",
  unknown: "bg-gray-500",
};

const statusBorder: Record<string, string> = {
  online: "border-green-800 group-hover:border-green-600",
  offline: "border-red-900 group-hover:border-red-700",
  degraded: "border-yellow-900 group-hover:border-yellow-600",
  unknown: "border-gray-700 group-hover:border-gray-500",
};

const COLUMN_OPTIONS = [1, 2, 3, 4] as const;

const gridColsClass: Record<number, string> = {
  1: "grid-cols-1",
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

function CameraTile({
  camera,
  index,
  hasMotion,
  onDragStart,
  onDragOver,
  onDrop,
  isDragging,
}: {
  camera: Camera;
  index: number;
  hasMotion: boolean;
  onDragStart: (idx: number) => void;
  onDragOver: (e: DragEvent, idx: number) => void;
  onDrop: (e: DragEvent, idx: number) => void;
  isDragging: boolean;
}) {
  const navigate = useNavigate();
  const { deleteCamera, testCamera } = useCameraMutations();
  const [menuOpen, setMenuOpen] = useState(false);
  const [testing, setTesting] = useState(false);
  const dot = statusColors[camera.status] || statusColors.unknown;
  const border = hasMotion ? "border-red-500" : (statusBorder[camera.status] || statusBorder.unknown);
  const isLive = camera.status === "online";

  const handleTest = async () => {
    setMenuOpen(false);
    setTesting(true);
    try { await testCamera.mutateAsync(camera.id); } catch {}
    setTesting(false);
  };

  const { confirm } = useConfirm();

  const handleDelete = async () => {
    setMenuOpen(false);
    const ok = await confirm(`Delete "${camera.name}"?`);
    if (!ok) return;
    deleteCamera.mutate(camera.id);
  };

  return (
    <div
      title={camera.connection_error || undefined}
      draggable
      onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; onDragStart(index); }}
      onDragOver={(e) => onDragOver(e, index)}
      onDrop={(e) => onDrop(e, index)}
      className={`aspect-video bg-gray-800 rounded border-2 ${border} ${hasMotion ? "animate-motion-flash" : ""} relative group overflow-hidden cursor-pointer transition-all duration-200 ${isDragging ? "opacity-30 scale-95" : ""}`}
    >
      <div onClick={() => navigate(`/live/${camera.id}`)} className="absolute inset-0">
        {isLive && <MiniLivePreview cameraId={camera.id} />}
        {!isLive && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
            <span className="text-gray-500 text-4xl font-light">{camera.name.charAt(0).toUpperCase()}</span>
            <span className="text-gray-600 text-xs">{camera.name}</span>
          </div>
        )}
      </div>

      <div className="absolute top-0.5 left-0.5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <GripVertical size={10} className="text-gray-600" />
      </div>

      <div className="absolute top-2 left-2 flex items-center gap-1.5 max-w-[75%]">
        <span
          title={camera.connection_error || `Status: ${camera.status}`}
          className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${dot} ${isLive ? "animate-pulse" : ""}`}
        />
        <span className="text-xs text-gray-200 truncate">{camera.name}</span>
        <span className="text-[10px] text-gray-500 flex-shrink-0">(cam{index + 1})</span>
        {camera.location_name && (
          <span className="text-[10px] bg-blue-900/50 text-blue-400 px-1.5 py-0.5 rounded truncate max-w-[80px]">
            {camera.location_name}
          </span>
        )}
      </div>

      <div className="absolute top-2 right-2 z-20" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="opacity-0 group-hover:opacity-100 hover:bg-gray-700 rounded p-1 transition-all"
        >
          <MoreVertical size={16} className="text-gray-300" />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-7 w-44 bg-gray-800 border border-gray-600 rounded shadow-xl py-1 z-30">
            <button
              onClick={() => { setMenuOpen(false); navigate(`/live/${camera.id}`); }}
              className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-200 hover:bg-gray-700"
            >
              <MonitorPlay size={13} /> Live View
            </button>
            <button
              onClick={() => { setMenuOpen(false); navigate(`/cameras?edit=${camera.id}`); }}
              className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-200 hover:bg-gray-700"
            >
              <Pencil size={13} /> Edit Camera
            </button>
            <button
              onClick={handleTest}
              disabled={testing}
              className="flex items-center gap-2 w-full px-3 py-2 text-xs text-gray-200 hover:bg-gray-700 disabled:opacity-50"
            >
              <Wifi size={13} /> {testing ? "Testing..." : "Test Connection"}
            </button>
            <div className="border-t border-gray-700 my-1" />
            <button
              onClick={handleDelete}
              className="flex items-center gap-2 w-full px-3 py-2 text-xs text-red-400 hover:bg-gray-700"
            >
              <Trash2 size={13} /> Delete
            </button>
          </div>
        )}
      </div>

      {isLive && !menuOpen && (
        <div className="absolute top-2 right-8 opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="flex items-center gap-1 px-2 py-0.5 bg-green-700 rounded text-xs text-white">
            <Play size={10} /> Live
          </span>
        </div>
      )}

      <div className="absolute bottom-2 left-2 right-2 flex justify-between items-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <span className="text-xs text-gray-400 truncate">{camera.ip_address}</span>
        {camera.has_ptz && <span className="text-xs bg-blue-700 px-1.5 py-0.5 rounded text-white">PTZ</span>}
      </div>
    </div>
  );
}

export default function CameraGrid() {
  const { data: cameras, isLoading } = useCameras();
  const { reorderCameras } = useCameraMutations();
  const { data: events = [] } = useEvents();
  const [columns, setColumns] = useUiPreference<number>("dashboard_columns", 2);
  const cols = gridColsClass[columns] ? columns : 2;
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const camerasRef = useRef(cameras);
  camerasRef.current = cameras;

  const motionCameraIds = useMemo(() => {
    const now = Date.now();
    const ids = new Set<string>();
    for (const ev of events) {
      if (ev.event_type === "motion") {
        const age = now - new Date(ev.created_at).getTime();
        if (age < 10_000) ids.add(ev.camera_id);
      }
    }
    return ids;
  }, [events]);

  const handleDragStart = useCallback((idx: number) => {
    setDragIndex(idx);
    dragIndexRef.current = idx;
  }, []);

  const handleDragOver = useCallback((e: DragEvent, idx: number) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback((_e: DragEvent, targetIdx: number) => {
    const src = dragIndexRef.current;
    if (src === null || src === targetIdx) { setDragIndex(null); dragIndexRef.current = null; return; }
    const items = camerasRef.current;
    if (!items) { setDragIndex(null); dragIndexRef.current = null; return; }

    const reordered = [...items];
    const [moved] = reordered.splice(src, 1);
    reordered.splice(targetIdx, 0, moved);

    const payload = reordered.map((c, i) => ({ id: c.id, display_order: i }));
    reorderCameras.mutate(payload);
    setDragIndex(null);
    dragIndexRef.current = null;
  }, [reorderCameras]);

  const handleDragEnd = useCallback(() => {
    setDragIndex(null);
  }, []);

  if (isLoading) {
    return (
      <div className={`grid ${gridColsClass[cols]} gap-4`}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="aspect-video bg-gray-800 rounded border border-gray-700 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!cameras?.length) {
    return (
      <EmptyState
        icon={<MonitorPlay size={28} />}
        title="No cameras configured"
        description="Go to Cameras to add your first IP camera."
      />
    );
  }

  return (
    <div onDragEnd={handleDragEnd}>
      <div className="flex items-center justify-between gap-1 mb-3">
        <span className="text-[10px] text-gray-600">Drag to reorder</span>
        <div className="flex items-center gap-1">
          <LayoutGrid size={14} className="text-gray-500 mr-1" />
          {COLUMN_OPTIONS.map((n) => (
            <button
              key={n}
              onClick={() => setColumns(n)}
              title={`${n} column${n > 1 ? "s" : ""}`}
              className={`w-7 h-7 rounded text-xs font-medium transition-colors ${
                cols === n
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>
      <div className={`grid ${gridColsClass[cols]} gap-4`}>
        {cameras.map((camera, i) => (
          <CameraTile
            key={camera.id}
            camera={camera}
            index={i}
            hasMotion={motionCameraIds.has(camera.id)}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            isDragging={dragIndex === i}
          />
        ))}
      </div>
    </div>
  );
}
