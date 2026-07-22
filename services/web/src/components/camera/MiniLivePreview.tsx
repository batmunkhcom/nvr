import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import apiClient from "../../api/client";
import { Loader2, AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  cameraId: string;
}

type StreamState = "connecting" | "loading" | "playing" | "error";

const MAX_START_ATTEMPTS = 3;
const POLL_INTERVAL_MS = 1_000;
const MAX_POLL_ATTEMPTS = 20;

export default function MiniLivePreview({ cameraId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<StreamState>("connecting");
  const [errorMsg, setErrorMsg] = useState("");
  const hlsRef = useRef<Hls | null>(null);

  const hlsPath = `/hls/${cameraId}_sub/index.m3u8`;

  const cleanup = () => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  };

  const startStream = () => {
    cleanup();
    setState("connecting");
    setErrorMsg("");
    doStart();
  };

  const doStart = () => {
    let cancelled = false;

    async function start() {
      for (let attempt = 0; attempt < MAX_START_ATTEMPTS; attempt++) {
        if (cancelled) return;
        try {
          await apiClient.post(`/cameras/${cameraId}/live/start?stream=sub`);
          break;
        } catch {
          if (attempt === MAX_START_ATTEMPTS - 1) {
            if (!cancelled) {
              setState("error");
              setErrorMsg("Could not start stream relay");
            }
            return;
          }
          await new Promise((r) => setTimeout(r, 1_000));
        }
      }

      if (cancelled) return;
      setState("loading");

      for (let i = 0; i < MAX_POLL_ATTEMPTS; i++) {
        if (cancelled) return;
        try {
          const resp = await fetch(hlsPath);
          if (resp.ok || resp.status === 302) {
            if (!cancelled) initHls();
            return;
          }
        } catch {
          /* poll retry */
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      }

      if (!cancelled) {
        setState("error");
        setErrorMsg("Stream not available");
      }
    }

    start();

    return () => {
      cancelled = true;
    };
  };

  const initHls = () => {
    if (!videoRef.current || !Hls.isSupported()) {
      setState("error");
      setErrorMsg("HLS not supported");
      return;
    }

    cleanup();
    const hls = new Hls({ enableWorker: false });
    hlsRef.current = hls;

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setState("playing");
      videoRef.current?.play().catch(() => {});
    });

    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) {
        setState("error");
        setErrorMsg(data.type === Hls.ErrorTypes.NETWORK_ERROR
          ? "Stream network error"
          : "Stream playback error");
      }
    });

    hls.loadSource(hlsPath);
    hls.attachMedia(videoRef.current);
  };

  useEffect(() => {
    const cancel = doStart();
    return () => {
      cancel?.();
      cleanup();
    };
  }, [cameraId]);

  return (
    <div className="absolute inset-0">
      <video
        ref={videoRef}
        muted
        autoPlay
        playsInline
        className={`absolute inset-0 w-full h-full object-cover ${
          state === "playing" ? "opacity-70" : "opacity-0"
        }`}
      />

      {state === "connecting" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-gray-900/80">
          <Loader2 size={18} className="text-gray-400 animate-spin" />
          <span className="text-[10px] text-gray-400">Connecting...</span>
        </div>
      )}

      {state === "loading" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-gray-900/80">
          <Loader2 size={18} className="text-blue-400 animate-spin" />
          <span className="text-[10px] text-gray-400">Loading stream...</span>
        </div>
      )}

      {state === "error" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-gray-900/80">
          <AlertTriangle size={16} className="text-red-400" />
          <span className="text-[10px] text-gray-400">{errorMsg}</span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              startStream();
            }}
            className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 mt-0.5"
          >
            <RefreshCw size={10} /> Retry
          </button>
        </div>
      )}
    </div>
  );
}
