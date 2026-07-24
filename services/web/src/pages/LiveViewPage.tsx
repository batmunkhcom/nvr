import { useCallback, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Maximize, Minimize, Square,
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RefreshCw,
} from "lucide-react";
import { useCameras } from "../hooks/useCameras";
import apiClient from "../api/client";
import { useStreamPlayer, type StreamType } from "../hooks/useStreamPlayer";
import type { Camera as CameraType } from "../types/camera";

export default function LiveView() {
  const params = useParams();
  const navigate = useNavigate();
  const { data: cameras } = useCameras();
  const camera = (cameras || []).find((c: CameraType) => c.id === params.cameraId);
  const [fullscreen, setFullscreen] = useState(false);
  const [streamType, setStreamType] = useState<StreamType>("main");
  const cameraId = camera?.id || "";

  const { state, retrySec, attachVideo, startStream } = useStreamPlayer({
    cameraId,
    streamType,
  });

  const stopStream = useCallback(async () => {
    if (!camera) return;
    try { await apiClient.post(`/cameras/${camera.id}/live/stop`); } catch { /* noop */ }
  }, [camera]);

  const doPtz = useCallback(async (direction: string) => {
    if (!camera) return;
    try { await apiClient.post(`/cameras/${camera.id}/ptz`, null, { params: { action: "move", direction, speed: 0.5 } }); } catch { /* non-fatal */ }
  }, [camera]);

  const doZoom = useCallback(async (zoom: "in" | "out") => {
    if (!camera) return;
    try { await apiClient.post(`/cameras/${camera.id}/ptz`, null, { params: { action: "zoom", zoom } }); } catch { /* non-fatal */ }
  }, [camera]);

  if (!camera) {
    return <div className="flex items-center justify-center h-64"><p className="text-gray-500">Camera not found</p></div>;
  }

  const isPlaying = state === "playing";

  return (
    <div className={fullscreen ? "fixed inset-0 z-50 bg-black" : "page-enter"}>
      {!fullscreen && (
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded text-gray-400">
              <ArrowLeft size={18} />
            </button>
            <div>
              <h1 className="text-xl font-bold">{camera.name}</h1>
              <p className="text-xs text-gray-500">{camera.ip_address} &middot; {camera.status}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setStreamType((p) => (p === "main" ? "sub" : "main"))}
              className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300">
              {streamType === "main" ? "MAIN" : "SUB"}
            </button>
            {isPlaying && (
              <button onClick={stopStream} className="flex items-center gap-1.5 px-3 py-1.5 bg-red-700 hover:bg-red-600 rounded text-white text-sm">
                <Square size={14} /> Stop
              </button>
            )}
            <button onClick={() => setFullscreen(!fullscreen)} className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded text-gray-400">
              {fullscreen ? <Minimize size={18} /> : <Maximize size={18} />}
            </button>
          </div>
        </div>
      )}

      <div className={`relative bg-black rounded-lg overflow-hidden ${fullscreen ? "h-full" : "aspect-video"}`}>
        <video ref={attachVideo} autoPlay muted playsInline
          className={`w-full h-full object-contain ${isPlaying ? "" : "hidden"}`} />

        {!isPlaying && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 gap-3">
            {state === "connecting" && (
              <div className="w-10 h-10 border-2 border-gray-600 border-t-blue-500 rounded-full animate-spin" />
            )}
            {state === "loading" && <p className="text-sm">Buffering {streamType} stream...</p>}
            {state === "retrying" && (
              <>
                <p className="text-sm text-yellow-500">Retrying in {retrySec}s</p>
                <button onClick={startStream} className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
                  <RefreshCw size={14} /> Retry Now
                </button>
              </>
            )}
            {state === "error" && (
              <button onClick={startStream} className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
                <RefreshCw size={14} /> Retry
              </button>
            )}
          </div>
        )}

        {fullscreen && (
          <button onClick={() => setFullscreen(false)}
            className="absolute top-4 right-4 text-white bg-black/50 hover:bg-black/70 rounded p-2">
            <Minimize size={20} />
          </button>
        )}
      </div>

      {camera.has_ptz && isPlaying && (
        <div className="flex flex-wrap items-center justify-center gap-1 mt-2">
          <button onClick={() => doPtz("up")} className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronUp size={18} /></button>
          <button onClick={() => doPtz("down")} className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronDown size={18} /></button>
          <button onClick={() => doPtz("left")} className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronLeft size={18} /></button>
          <button onClick={() => doPtz("right")} className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronRight size={18} /></button>
          <button onClick={() => doZoom("in")} className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ZoomIn size={18} /></button>
          <button onClick={() => doZoom("out")} className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ZoomOut size={18} /></button>
        </div>
      )}
    </div>
  );
}
