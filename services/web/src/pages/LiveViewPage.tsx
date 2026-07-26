import { useCallback, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Maximize, Minimize, Square, Volume2, VolumeX,
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RefreshCw, RotateCcw,
} from "lucide-react";
import { useCameras } from "../hooks/useCameras";
import apiClient from "../api/client";
import { useStreamPlayer, type StreamType } from "../hooks/useStreamPlayer";
import { useVideoAudio } from "../hooks/useVideoAudio";
import { useVideoZoom } from "../hooks/useVideoZoom";
import type { Camera as CameraType } from "../types/camera";

export default function LiveView() {
  const params = useParams();
  const navigate = useNavigate();
  const { data: cameras } = useCameras();
  const camera = (cameras || []).find((c: CameraType) => c.id === params.cameraId);
  const [fullscreen, setFullscreen] = useState(false);
  const [streamType, setStreamType] = useState<StreamType>("main");
  const cameraId = camera?.id || "";

  const { state, retrySec, errorMsg, attachVideo, startStream } = useStreamPlayer({
    cameraId,
    streamType,
  });

  const { muted, toggleMute, attachVideo: attachWithAudio } = useVideoAudio(attachVideo);
  const { scale, zoomIn: digiZoomIn, zoomOut: digiZoomOut, reset, transformStyle, marquee, onWheel, onMouseDown, onMouseMove, onMouseUp, onDoubleClick } = useVideoZoom({ marquee: true });

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

      <div className={`relative bg-black rounded-lg overflow-hidden ${fullscreen ? "h-full" : "aspect-video"}`}
        onWheel={onWheel} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onDoubleClick={onDoubleClick}>
        <video ref={attachWithAudio} autoPlay muted playsInline
          className={`w-full h-full object-contain ${isPlaying ? "" : "hidden"}`}
          style={transformStyle} />

        {/* Marquee selection overlay */}
        {marquee && (
          <div
            className="absolute border-2 border-dashed border-blue-400 bg-blue-500/20 pointer-events-none z-20"
            style={{
              left: marquee.left,
              top: marquee.top,
              width: marquee.width,
              height: marquee.height,
            }}
          />
        )}
        {/* Zoom badge */}
        {scale > 1 && (
          <span className="absolute top-2 right-2 bg-black/75 text-white text-xs px-2 py-0.5 rounded z-20 pointer-events-none font-mono">
            {scale.toFixed(1)}x
          </span>
        )}

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
              <>
                <p className="text-sm text-red-400">{errorMsg || "Stream failed"}</p>
                <button onClick={startStream} className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
                  <RefreshCw size={14} /> Retry
                </button>
              </>
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

      <div className="flex flex-wrap items-center justify-center gap-1 mt-2">
        <button onClick={toggleMute}
          className="p-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400 hover:text-white"
          title={muted ? "Unmute" : "Mute"}>
          {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
        </button>
        {scale > 1 && (
          <>
            <button onClick={reset}
              className="p-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-400 hover:text-white"
              title="Reset zoom">
              <RotateCcw size={18} />
            </button>
            <span className="text-xs text-gray-400 font-mono">{scale.toFixed(1)}x</span>
          </>
        )}
        <button onClick={digiZoomOut} disabled={scale <= 1}
          className="p-2 bg-gray-800 hover:bg-gray-700 rounded disabled:opacity-30" title="Digital zoom out">
          <ZoomOut size={18} /></button>
        <button onClick={digiZoomIn} disabled={scale >= 16}
          className="p-2 bg-gray-800 hover:bg-gray-700 rounded disabled:opacity-30" title="Digital zoom in">
          <ZoomIn size={18} /></button>
        {camera.has_ptz && isPlaying && (
          <><span className="w-px h-5 bg-gray-700 mx-2" />
          <button onClick={() => doPtz("up")} title="Pan Up" className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronUp size={18} /></button>
          <button onClick={() => doPtz("down")} title="Pan Down" className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronDown size={18} /></button>
          <button onClick={() => doPtz("left")} title="Pan Left" className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronLeft size={18} /></button>
          <button onClick={() => doPtz("right")} title="Pan Right" className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ChevronRight size={18} /></button>
          <button onClick={() => doZoom("in")} title="PTZ Zoom In" className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ZoomIn size={18} /></button>
          <button onClick={() => doZoom("out")} title="PTZ Zoom Out" className="p-2 bg-gray-800 hover:bg-gray-700 rounded"><ZoomOut size={18} /></button></>
        )}
      </div>
    </div>
  );
}
