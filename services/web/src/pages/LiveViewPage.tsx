import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Maximize, Minimize, Play, Square, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import Hls from "hls.js";
import { useCameras } from "../hooks/useCameras";
import apiClient from "../api/client";
import type { Camera as CameraType } from "../types/camera";

export default function LiveView() {
  const params = useParams();
  const navigate = useNavigate();
  const { data: cameras } = useCameras();
  const camera = (cameras || []).find((c: CameraType) => c.id === params.cameraId);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [hlsUrl, setHlsUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");

  const toggleFullscreen = useCallback(() => setFullscreen((f) => !f), []);

  const startStream = useCallback(async () => {
    if (!camera) return;
    setStatus("connecting");
    try {
      const res = await apiClient.post(`/cameras/${camera.id}/live/start`);
      const url = res.data?.data?.hls_url;
      if (url) {
        setHlsUrl(url);
        setPlaying(true);
        setStatus("playing");
      }
    } catch {
      setStatus("error");
    }
  }, [camera]);

  const stopStream = useCallback(async () => {
    if (!camera) return;
    try {
      await apiClient.post(`/cameras/${camera.id}/live/stop`);
    } catch { /* ignore */ }
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
    } catch { /* ignore */ }
  }, [camera]);

  const doZoom = useCallback(async (z: string) => {
    if (!camera) return;
    try {
      await apiClient.post(`/cameras/${camera.id}/ptz`, null, {
        params: { action: "move", zoom: z, speed: 0.5 },
      });
    } catch { /* ignore */ }
  }, [camera]);

  useEffect(() => {
    if (hlsUrl && videoRef.current && Hls.isSupported()) {
      const hls = new Hls({ enableWorker: false });
      hls.loadSource(hlsUrl);
      hls.attachMedia(videoRef.current);
      return () => {
        hls.destroy();
      };
    }
  }, [hlsUrl]);

  useEffect(() => {
    return () => {
      stopStream();
    };
  }, []);

  if (!camera) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">Camera not found</p>
      </div>
    );
  }

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
            <Play size={48} />
            <p className="text-sm">
              {status === "connecting" ? "Connecting..." : status === "error" ? "Stream error" : "Press Start Stream to begin"}
            </p>
          </div>
        )}

        <div className="absolute top-4 right-4 flex gap-2 z-10">
          <span className={`px-2 py-0.5 rounded text-xs font-mono ${camera.status === "online" ? "bg-green-700 text-green-200" : "bg-red-700 text-red-200"}`}>
            {camera.status}
          </span>
        </div>

        {playing && (
          <div className="absolute bottom-4 right-4 z-10 flex items-center gap-1">
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
            <button onClick={toggleFullscreen} className="p-2 bg-black/50 hover:bg-black/70 rounded text-white ml-1">
              {fullscreen ? <Minimize size={16} /> : <Maximize size={16} />}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
