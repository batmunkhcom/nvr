import { useRef, useEffect, useState } from "react";
import { Volume2, VolumeX, Download } from "lucide-react";

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

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = speed;
  }, [speed]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const seekIfNeeded = () => {
      if (startOffset && startOffset > 0 && Number.isFinite(video.duration)) {
        video.currentTime = Math.min(startOffset, Math.max(0, video.duration - 0.5));
      }
    };

    video.addEventListener("loadedmetadata", seekIfNeeded, { once: true });
    video.src = src;
    video.muted = muted;
    if (autoPlay) video.play().catch(() => {});

    return () => {
      video.removeEventListener("loadedmetadata", seekIfNeeded);
      video.pause();
      video.src = "";
      video.load();
    };
  }, [src, autoPlay, startOffset]);

  return (
    <div className="relative">
      <video
        ref={videoRef}
        controls={controls}
        muted={muted}
        autoPlay={autoPlay}
        poster={poster}
        playsInline
        preload="auto"
        className={`w-full max-w-3xl aspect-video bg-black rounded ${className}`}
      />
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
      </div>
    </div>
  );
}
