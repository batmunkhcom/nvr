import { useState, useMemo, useCallback, useRef, useEffect, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useCameras, useCameraMutations } from "../../hooks/useCameras";
import { useUiPreference } from "../../hooks/useUiPreference";
import { useEvents } from "../../hooks/useEvents";
import { Camera } from "../../types/camera";
import { LayoutGrid, Play, MoreVertical, Wifi, Pencil, Trash2, MonitorPlay, GripVertical, X, Loader2, RefreshCw, Volume2, VolumeX, ZoomIn, ZoomOut, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useStreamPlayer, type StreamType } from "../../hooks/useStreamPlayer";
import { useVideoAudio } from "../../hooks/useVideoAudio";
import { useVideoZoom } from "../../hooks/useVideoZoom";
import apiClient from "../../api/client";
import LazyMiniPreview from "./LazyMiniPreview";
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

const LOCATION_COLORS = [
  "bg-blue-900/50 text-blue-400",
  "bg-green-900/50 text-green-400",
  "bg-yellow-900/50 text-yellow-400",
  "bg-purple-900/50 text-purple-400",
  "bg-pink-900/50 text-pink-400",
  "bg-teal-900/50 text-teal-400",
  "bg-orange-900/50 text-orange-400",
  "bg-cyan-900/50 text-cyan-400",
  "bg-red-900/50 text-red-400",
  "bg-indigo-900/50 text-indigo-400",
];

function locationColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return LOCATION_COLORS[Math.abs(hash) % LOCATION_COLORS.length];
}

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
  insertSide,
  onExpand,
}: {
  camera: Camera;
  index: number;
  hasMotion: boolean;
  onDragStart: (idx: number) => void;
  onDragOver: (e: DragEvent, idx: number) => void;
  onDrop: (e: DragEvent, idx: number) => void;
  isDragging: boolean;
  insertSide: "left" | "right" | null;
  onExpand: (camera: Camera) => void;
}) {
  const navigate = useNavigate();
  const { deleteCamera, testCamera } = useCameraMutations();
  const [menuOpen, setMenuOpen] = useState(false);
  const [testing, setTesting] = useState(false);
  const clickRef = useRef(0);
  const dot = statusColors[camera.status] || statusColors.unknown;
  const border = hasMotion ? "border-red-500" : (statusBorder[camera.status] || statusBorder.unknown);
  const hasStream = !!(camera.stream_main_uri || camera.stream_sub_uri);

  const handleClick = () => {
    clickRef.current += 1;
    const clicks = clickRef.current;
    setTimeout(() => {
      if (clickRef.current === clicks) {
        if (clicks === 1) {
          onExpand(camera);
        } else if (clicks >= 2) {
          navigate(`/live/${camera.id}`);
        }
        clickRef.current = 0;
      }
    }, 280);
  };

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
      onClick={handleClick}
      className={`aspect-video bg-gray-800 rounded border-2 ${border} ${hasMotion ? "animate-motion-flash" : ""} relative group overflow-hidden transition-all duration-200 ${isDragging ? "opacity-30 scale-95" : ""} ${insertSide === "left" ? "border-l-[3px] border-l-blue-400/70 shadow-[inset_6px_0_12px_-4px_rgba(96,165,250,0.25)]" : ""} ${insertSide === "right" ? "border-r-[3px] border-r-blue-400/70 shadow-[inset_-6px_0_12px_-4px_rgba(96,165,250,0.25)]" : ""}`}
      onDragOver={(e) => onDragOver(e, index)}
      onDrop={(e) => onDrop(e, index)}
    >
      <div
        draggable
        onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; onDragStart(index); }}
        className="absolute left-0 top-0 bottom-0 w-8 z-30 cursor-grab active:cursor-grabbing"
      />
      {hasStream && <LazyMiniPreview cameraId={camera.id} />}
      {!hasStream && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
          <span className="text-gray-500 text-4xl font-light">{camera.name.charAt(0).toUpperCase()}</span>
          <span className="text-gray-600 text-xs">{camera.name}</span>
        </div>
      )}

      <div className="absolute top-0.5 left-0.5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <GripVertical size={10} className="text-gray-600" />
      </div>

      <div className="absolute top-2 left-2 flex items-center gap-1.5 max-w-[75%]">
        <span
          title={camera.connection_error || `Status: ${camera.status}`}
          className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${dot} ${camera.status === "online" ? "animate-pulse" : ""}`}
        />
        <span className="text-xs text-gray-200 truncate">{camera.name}</span>
        <span className="text-[10px] text-gray-500 flex-shrink-0">(cam{index + 1})</span>
        {camera.location_name && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded truncate max-w-[80px] ${locationColor(camera.location_name)}`}>
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

      {hasStream && !menuOpen && (
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
  const qc = useQueryClient();
  const [columns, setColumns] = useUiPreference<number>("dashboard_columns", 2);
  const cols = gridColsClass[columns] ? columns : 2;
  type InsertAt = { index: number; side: "left" | "right" };
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [insertAt, setInsertAt] = useState<InsertAt | null>(null);
  const dragIndexRef = useRef<number | null>(null);
  const insertAtRef = useRef<InsertAt | null>(null);
  const [expandedCamera, setExpandedCamera] = useState<Camera | null>(null);

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
    e.dataTransfer.dropEffect = "move";
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const side: "left" | "right" = e.clientX < rect.left + rect.width / 2 ? "left" : "right";
    const pos = { index: idx, side };
    setInsertAt(pos);
    insertAtRef.current = pos;
  }, []);

  const handleDrop = useCallback((e: DragEvent, _targetIdx: number) => {
    e.preventDefault();
    const src = dragIndexRef.current;
    if (src === null) {
      setDragIndex(null);
      setInsertAt(null);
      dragIndexRef.current = null;
      insertAtRef.current = null;
      return;
    }

    const ins = insertAtRef.current;
    let target = ins ? ins.index : _targetIdx;
    if (ins && ins.side === "right") target = ins.index + 1;
    if (src < target) target--;

    if (src === target) {
      setDragIndex(null);
      setInsertAt(null);
      dragIndexRef.current = null;
      insertAtRef.current = null;
      return;
    }

    const items = qc.getQueryData<Camera[]>(["cameras"]);
    if (!items) {
      setDragIndex(null);
      setInsertAt(null);
      dragIndexRef.current = null;
      insertAtRef.current = null;
      return;
    }

    const reordered = [...items];
    const [moved] = reordered.splice(src, 1);
    reordered.splice(target, 0, moved);
    const payload = reordered.map((c, i) => ({ id: c.id, display_order: i }));

    qc.setQueryData(["cameras"], reordered);

    reorderCameras.mutate(payload, {
      onError: () => {
        qc.setQueryData(["cameras"], items);
      },
    });

    setDragIndex(null);
    setInsertAt(null);
    dragIndexRef.current = null;
    insertAtRef.current = null;
  }, [reorderCameras, qc]);

  const handleDragEnd = useCallback(() => {
    setDragIndex(null);
    setInsertAt(null);
    insertAtRef.current = null;
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
          <div key={camera.id} className="transition-transform duration-200 ease-out">
            <CameraTile
              key={camera.id}
              camera={camera}
              index={i}
              hasMotion={motionCameraIds.has(camera.id)}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              isDragging={dragIndex === i}
              insertSide={insertAt?.index === i ? insertAt.side : null}
              onExpand={setExpandedCamera}
            />
          </div>
        ))}
      </div>

      {expandedCamera && (
        <ExpandedView camera={expandedCamera} onClose={() => setExpandedCamera(null)} />
      )}
    </div>
  );
}

function ExpandedView({ camera, onClose }: { camera: Camera; onClose: () => void }) {
  const [streamType, setStreamType] = useState<StreamType>("main");
  const { state, retrySec, attachVideo, startStream } = useStreamPlayer({ cameraId: camera.id, streamType });
  const { muted, toggleMute, attachVideo: attachWithAudio } = useVideoAudio(attachVideo);
  const { scale, zoomIn, zoomOut, reset, transformStyle, onWheel, onMouseDown, onMouseMove, onMouseUp, onDoubleClick } = useVideoZoom();

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const doPtz = async (direction: string) => {
    try { await apiClient.post(`/cameras/${camera.id}/ptz`, null, { params: { action: "move", direction, speed: 0.5 } }); } catch {}
  };

  const doPtzZoom = async (zoom: "in" | "out") => {
    try { await apiClient.post(`/cameras/${camera.id}/ptz`, null, { params: { action: "zoom", zoom } }); } catch {}
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={onClose}>
      <div className="relative w-full max-w-5xl mx-4" onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} className="absolute -top-10 right-0 text-gray-400 hover:text-white">
          <X size={24} />
        </button>
        <div className="bg-gray-900 rounded overflow-hidden">
          <div
            className="relative aspect-video bg-black overflow-hidden"
            onWheel={onWheel}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onDoubleClick={onDoubleClick}
          >
            <video ref={attachWithAudio} muted autoPlay playsInline
              className={`absolute inset-0 w-full h-full object-contain ${state === "playing" ? "" : "hidden"}`}
              style={transformStyle} />
            {state === "connecting" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <Loader2 size={32} className="text-gray-400 animate-spin" />
                <span className="text-sm text-gray-400">Starting {streamType} stream...</span>
              </div>
            )}
            {state === "loading" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <Loader2 size={32} className="text-blue-400 animate-spin" />
                <span className="text-sm text-gray-400">Buffering...</span>
              </div>
            )}
            {state === "retrying" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <span className="text-sm text-gray-400">Retrying in {retrySec}s...</span>
                <button onClick={(e) => { e.stopPropagation(); startStream(); }}
                  className="flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300">
                  <RefreshCw size={14} /> Retry Now
                </button>
              </div>
            )}
            {state === "error" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <span className="text-sm text-gray-400">Stream unavailable</span>
                <button onClick={(e) => { e.stopPropagation(); startStream(); }}
                  className="flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300">
                  <RefreshCw size={14} /> Retry Now
                </button>
              </div>
            )}
          </div>
          <div className="px-4 py-2 flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-200">{camera.name}</span>
              <button onClick={toggleMute}
                className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white"
                title={muted ? "Unmute" : "Mute"}>
                {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </button>
              <button onClick={(e) => { e.stopPropagation(); setStreamType((p) => (p === "main" ? "sub" : "main")); }}
                className="text-[10px] px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-300">
                {streamType === "main" ? "MAIN" : "SUB"}
              </button>
            </div>
            <div className="flex items-center gap-1">
              {scale > 1 && (
                <button onClick={reset}
                  className="text-[10px] px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-500">
                  {scale.toFixed(1)}x
                </button>
              )}
              <button onClick={zoomOut} disabled={scale <= 1}
                className="p-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-gray-400 hover:text-white"
                title="Zoom out">
                <ZoomOut size={14} />
              </button>
              <button onClick={zoomIn} disabled={scale >= 16}
                className="p-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-gray-400 hover:text-white"
                title="Zoom in">
                <ZoomIn size={14} />
              </button>
              {camera.has_ptz && (
                <>
                  <span className="w-px h-5 bg-gray-700 mx-1" />
                  <button onClick={() => doPtz("up")} className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white" title="Pan Up">
                    <ChevronUp size={14} /></button>
                  <button onClick={() => doPtz("down")} className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white" title="Pan Down">
                    <ChevronDown size={14} /></button>
                  <button onClick={() => doPtz("left")} className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white" title="Pan Left">
                    <ChevronLeft size={14} /></button>
                  <button onClick={() => doPtz("right")} className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white" title="Pan Right">
                    <ChevronRight size={14} /></button>
                  <button onClick={() => doPtzZoom("in")} className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white" title="PTZ Zoom In">
                    <ZoomIn size={14} /></button>
                  <button onClick={() => doPtzZoom("out")} className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white" title="PTZ Zoom Out">
                    <ZoomOut size={14} /></button>
                </>
              )}
            </div>
            <span className="text-xs text-gray-500">{camera.ip_address}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
