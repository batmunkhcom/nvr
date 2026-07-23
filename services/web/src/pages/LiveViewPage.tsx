import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Maximize, Minimize, Play, Square, RotateCcw,
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ZoomIn, ZoomOut,
} from "lucide-react";
import Hls from "hls.js";
import { useCameras } from "../hooks/useCameras";
import apiClient from "../api/client";
import type { Camera as CameraType } from "../types/camera";

function wait(ms: number) { return new Promise((r) => setTimeout(r, ms)); }

type StreamStatus = "idle" | "connecting" | "playing" | "error";

export default function LiveView() {
  const params = useParams();
  const navigate = useNavigate();
  const { data: cameras } = useCameras();
  const camera = (cameras || []).find((c: CameraType) => c.id === params.cameraId);
  const videoRef = useRef<HTMLVideoElement>(null);
  const startingRef = useRef(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [hlsUrl, setHlsUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const cameraId = camera?.id;

  const toggleFullscreen = useCallback(() => setFullscreen((f) => !f), []);

  const startStream = useCallback(async () => {
    if (!camera || startingRef.current) return;
    startingRef.current = true;
    setStatus("connecting");
    setErrorMsg("");
    try {
      const res = await apiClient.post(`/cameras/${camera.id}/live/start`);
      const url = res.data?.data?.hls_url;
      if (!url) {
        setStatus("error");
        setErrorMsg(res.data?.data?.error || "Camera has no stream configured");
        return;
      }

      for (let i = 0; i < 20; i++) {
        await wait(1000);
        try {
          const st = await apiClient.get(`/cameras/${camera.id}/live/status`);
          if (st.data?.data?.running) {
            setHlsUrl(url);
            setPlaying(true);
            setStatus("playing");
            return;
          }
        } catch { /* retry */ }
      }
      setStatus("error");
      setErrorMsg("Stream did not start in time — check camera connection");
    } catch {
      setStatus("error");
      setErrorMsg("Failed to start stream");
    } finally {
      startingRef.current = false;
    }
  }, [camera]);

  const stopStream = useCallback(async () => {
    if (!camera) return;
    try { await apiClient.post(`/cameras/${camera.id}/live/stop`); } catch { /* noop */ }
    setPlaying(false);
    setHlsUrl(null);
    setStatus("idle");
  }, [camera]);

  const doPtz = useCallback(async (direction: string) => {
    if (!camera) return;
    try {
      await apiClient.post(`/cameras/${camera.id}/ptz`, null, {
        params: { action: "move", direction, speed: 0.5 },
      });
    } catch { /* PTZ failure is non-fatal */ }
  }, [camera]);

  const doZoom = useCallback(async (zoom: "in" | "out") => {
    if (!camera) return;
    try {
      await apiClient.post(`/cameras/${camera.id}/ptz`, null, {
        params: { action: "zoom", zoom },
      });
    } catch { /* PTZ failure is non-fatal */ }
  }, [camera]);

  useEffect(() => {
    if (!hlsUrl || !videoRef.current) return;

    let cancelled = false;
    const hls = new Hls({ enableWorker: false });

    const waitForPlaylist = async () => {
      for (let i = 0; i < 30; i++) {
        if (cancelled) return;
        try {
          const r = await fetch(hlsUrl);
          if (r.ok) {
            if (!cancelled && Hls.isSupported()) {
              hls.loadSource(hlsUrl);
              hls.attachMedia(videoRef.current!);
              hls.on(Hls.Events.ERROR, (_e, data) => {
                if (data.fatal) {
                  setPlaying(false);
                  setStatus("error");
                  const detail = data.details || data.error?.message || "unknown";
                  setErrorMsg(`Stream playback failed: ${detail}`);
                  hls.destroy();
                }
              });
            }
            return;
          }
        } catch { /* retry */ }
        await wait(1000);
      }
      if (!cancelled) {
        setPlaying(false);
        setStatus("error");
        setErrorMsg("Stream not available — check camera connection");
      }
    };

    if (Hls.isSupported()) {
      waitForPlaylist();
    }

    return () => { cancelled = true; hls.destroy(); };
  }, [hlsUrl]);

  useEffect(() => {
    if (camera) startStream();
    return () => { if (camera) stopStream(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraId]);

  if (!camera) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Camera not found</p>
      </div>
    );
  }

  const statusText: Record<StreamStatus, string> = {
    idle: "Press Start Stream to begin",
    connecting: "Connecting to camera...",
    playing: "",
    error: errorMsg || "Stream error",
  };

  return (
    <div className={fullscreen ? "fixed inset-0 z-50 bg-black" : ""}>
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
            {!playing ? (
              <button onClick={startStream} className="flex items-center gap-1.5 px-3 py-1.5 bg-green-700 hover:bg-green-600 rounded text-white text-sm">
                <Play size={14} /> Start Stream
              </button>
            ) : (
              <button onClick={stopStream} className="flex items-center gap-1.5 px-3 py-1.5 bg-red-700 hover:bg-red-600 rounded text-white text-sm">
                <Square size={14} /> Stop
              </button>
            )}
          </div>
        </div>
      )}

      <div className={`relative bg-black rounded-lg overflow-hidden ${fullscreen ? "h-full" : "aspect-video"}`}>
        {playing && hlsUrl ? (
          <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-contain" />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 gap-3">
            {status === "connecting" ? (
              <div className="w-10 h-10 border-2 border-gray-600 border-t-blue-500 rounded-full animate-spin" />
            ) : (
              <Play size={48} />
            )}
            <p className={`text-sm ${status === "error" ? "text-red-400" : ""}`}>
              {statusText[status]}
            </p>
            {status === "error" && (
              <button
                onClick={startStream}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-white text-sm"
              >
                <RotateCcw size={14} /> Retry
              </button>
            )}
          </div>
        )}

        <div className="absolute top-4 right-4 flex gap-2 z-10">
          <span className={`px-2 py-0.5 rounded text-xs font-mono ${camera.status === "online" ? "bg-green-700 text-green-200" : "bg-red-700 text-red-200"}`}>
            {camera.status}
          </span>
        </div>

        {playing && (
          <div className="absolute bottom-4 right-4 z-10 flex items-center gap-1">
            {camera.has_ptz && (
              <>
                <div className="bg-black/50 rounded p-1 flex gap-0.5">
                  <button onClick={() => doPtz("left")} title="Pan Left" className="p-1 hover:bg-white/20 rounded"><ChevronLeft size={16} className="text-white" /></button>
                  <button onClick={() => doPtz("up")} title="Pan Up" className="p-1 hover:bg-white/20 rounded"><ChevronUp size={16} className="text-white" /></button>
                  <button onClick={() => doPtz("down")} title="Pan Down" className="p-1 hover:bg-white/20 rounded"><ChevronDown size={16} className="text-white" /></button>
                  <button onClick={() => doPtz("right")} title="Pan Right" className="p-1 hover:bg-white/20 rounded"><ChevronRight size={16} className="text-white" /></button>
                </div>
                <div className="bg-black/50 rounded p-1 flex gap-0.5 ml-1">
                  <button onClick={() => doZoom("in")} title="Zoom In" className="p-1 hover:bg-white/20 rounded"><ZoomIn size={16} className="text-white" /></button>
                  <button onClick={() => doZoom("out")} title="Zoom Out" className="p-1 hover:bg-white/20 rounded"><ZoomOut size={16} className="text-white" /></button>
                </div>
              </>
            )}
            <button onClick={toggleFullscreen} className="p-2 bg-black/50 hover:bg-black/70 rounded text-white ml-1">
              {fullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
