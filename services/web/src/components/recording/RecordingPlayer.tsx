import { useRef, useEffect, useState } from "react";
import { Volume2, VolumeX, Download, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { useVideoZoom } from "../../hooks/useVideoZoom";

interface Props {
  src: string;
  poster?: string;
  autoPlay?: boolean;
  controls?: boolean;
  className?: string;
  startOffset?: number;
  filename?: string;
  onDownload?: () => void;
}

const SPEEDS = [0.125, 0.25, 0.5, 0.75, 1, 1.5, 2, 4, 8];

export default function RecordingPlayer({ src, poster, autoPlay = true, controls = true, className = "", startOffset, filename, onDownload }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [speed, setSpeed] = useState(1);
  const [muted, setMuted] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [debugInfo, setDebugInfo] = useState("");
  const isPlayingRef = useRef(false);
  const hasErrorRef = useRef(false);
  const checkRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { scale, zoomIn, zoomOut, reset, transformStyle, marquee,
          onWheel, onMouseDown, onMouseMove, onMouseUp, onDoubleClick } =
    useVideoZoom({ marquee: true });

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
  }, [speed]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    setIsPlaying(false);
    setHasError(false);
    setErrorMsg("");
    isPlayingRef.current = false;
    hasErrorRef.current = false;

    if (checkRef.current) clearInterval(checkRef.current);

    let cancelled = false;
    let blobUrl: string | null = null;

    const onError = () => {
      if (cancelled) return;
      hasErrorRef.current = true;
      const codes: Record<number, string> = {
        1: "MEDIA_ERR_ABORTED",
        2: "MEDIA_ERR_NETWORK — check server, auth, or CORS",
        3: "MEDIA_ERR_DECODE — unsupported codec",
        4: "MEDIA_ERR_SRC_NOT_SUPPORTED",
      };
      setErrorMsg(codes[video.error?.code || 0] || `Error ${video.error?.code}`);
      setHasError(true);
    };
    video.addEventListener("error", onError);

    const loadAndPlay = async () => {
      try {
        setDebugInfo("fetching...");
        const resp = await fetch(src);
        if (cancelled) return;
        if (!resp.ok) {
          setErrorMsg(`HTTP ${resp.status}: ${resp.statusText}`);
          setHasError(true);
          return;
        }
        setDebugInfo("downloading...");
        const blob = await resp.blob();
        if (cancelled) return;
        blobUrl = URL.createObjectURL(blob);
        video.src = blobUrl;
        video.muted = muted;
        if (autoPlay) video.play().catch(() => {});
        setDebugInfo("playing...");
      } catch (e: any) {
        if (!cancelled) {
          setErrorMsg(e.message || "Fetch failed");
          setHasError(true);
        }
      }
    };
    loadAndPlay();

    checkRef.current = setInterval(() => {
      const rs = video.readyState;
      const rl = ["NONE","META","CUR","FUTURE","FULL"];
      setDebugInfo(`rs=${rl[rs]}(${rs}) paused=${video.paused} t=${video.currentTime.toFixed(1)} ns=${video.networkState}`);
      if (hasErrorRef.current || cancelled) return;
      if (video.readyState >= 2 && !video.paused && video.currentTime > 0) {
        if (!isPlayingRef.current) {
          isPlayingRef.current = true;
          setIsPlaying(true);
          if (startOffset && startOffset > 0 && Number.isFinite(video.duration)) {
            video.currentTime = Math.min(startOffset, Math.max(0, video.duration - 0.5));
          }
        }
      }
    }, 300);

    return () => {
      cancelled = true;
      if (checkRef.current) clearInterval(checkRef.current);
      video.removeEventListener("error", onError);
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      video.pause();
    };
  }, [src, autoPlay]);

  return (
    <div className="relative">
      {!isPlaying && !hasError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 z-10 rounded pointer-events-none">
          <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mb-2" />
          <p className="text-gray-400 text-sm">Loading video...</p>
          <p className="text-gray-600 text-[10px] mt-1 font-mono">{debugInfo}</p>
        </div>
      )}
      {hasError && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/90 z-10 rounded">
          <div className="text-center p-4">
            <p className="text-red-400 text-sm font-medium mb-2">Playback Error</p>
            <p className="text-gray-500 text-xs max-w-xs break-all">{errorMsg}</p>
          </div>
        </div>
      )}
      <div
        className="relative overflow-hidden rounded bg-black"
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onDoubleClick={onDoubleClick}
        onContextMenu={(e) => e.preventDefault()}
      >
        <video
          ref={videoRef}
          controls={controls}
          muted={muted}
          autoPlay={autoPlay}
          poster={poster}
          playsInline
          preload="auto"
          className={`w-full max-w-3xl aspect-video bg-black rounded ${className}`}
          style={transformStyle}
        />
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
        {/* Zoom indicator badge */}
        {scale > 1 && (
          <span className="absolute top-2 right-2 bg-black/75 text-white text-xs px-2 py-0.5 rounded z-20 pointer-events-none font-mono">
            {scale.toFixed(1)}x
          </span>
        )}
      </div>
      <div className="flex items-center gap-1 mt-2 flex-wrap">
        <button onClick={() => {
          const video = videoRef.current;
          if (!video) return;
          video.muted = !video.muted;
          setMuted(video.muted);
        }}
          className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white mr-1"
          title={muted ? "Unmute" : "Mute"}>
          {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
        </button>
        {onDownload && (
          <button onClick={onDownload}
            className="p-1 rounded bg-gray-800 hover:bg-indigo-600 text-gray-400 hover:text-white mr-1"
            title="Download">
            <Download size={14} /></button>
        )}
        <span className="text-xs text-gray-500">Speed:</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => setSpeed(s)}
            className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
              speed === s
                ? "bg-blue-600 text-white"
                : s < 1
                  ? "bg-gray-800 text-amber-400 hover:bg-gray-700 hover:text-amber-300"
                  : s > 1
                    ? "bg-gray-800 text-emerald-400 hover:bg-gray-700 hover:text-emerald-300"
                    : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200"
            }`}
          >
            {s}x
          </button>
        ))}
        <span className="text-gray-600 mx-1">|</span>
        <span className="text-xs text-gray-500">Zoom:</span>
        <button
          onClick={zoomOut}
          disabled={scale <= 1}
          className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-30"
          title="Zoom out"
        >
          <ZoomOut size={14} />
        </button>
        <span className="text-xs text-gray-400 font-mono min-w-[36px] text-center">{scale.toFixed(1)}x</span>
        <button
          onClick={zoomIn}
          disabled={scale >= 16}
          className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white disabled:opacity-30"
          title="Zoom in"
        >
          <ZoomIn size={14} />
        </button>
        {scale > 1 && (
          <button
            onClick={reset}
            className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white"
            title="Reset zoom"
          >
            <RotateCcw size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
