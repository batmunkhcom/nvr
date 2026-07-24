import { useRef, useEffect, useState } from "react";
import Hls from "hls.js";

interface Props {
  src: string;
  poster?: string;
  autoPlay?: boolean;
  controls?: boolean;
  className?: string;
  startOffset?: number;
}

const SPEEDS = [0.125, 0.25, 0.5, 0.75, 1, 1.5, 2, 4, 8];

export default function RecordingPlayer({ src, poster, autoPlay = true, controls = true, className = "", startOffset }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [speed, setSpeed] = useState(1);

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

    if (src.endsWith(".m3u8") && Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        seekIfNeeded();
        if (autoPlay) video.play().catch(() => {});
      });
      return () => {
        hls.destroy();
      };
    }

    video.addEventListener("loadedmetadata", seekIfNeeded, { once: true });
    video.src = src;
    if (autoPlay) video.play().catch(() => {});

    return () => {
      video.removeEventListener("loadedmetadata", seekIfNeeded);
      video.pause();
      video.src = "";
      video.load();
    };
  }, [src, autoPlay, startOffset]);

  return (
    <div>
      <video
        ref={videoRef}
        controls={controls}
        poster={poster}
        className={`w-full bg-black rounded ${className}`}
        playsInline
      />
      <div className="flex items-center gap-1 mt-2 flex-wrap">
        <span className="text-xs text-gray-500 mr-1">Speed:</span>
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
            {s < 1 ? `${s}x` : `${s}x`}
          </button>
        ))}
      </div>
    </div>
  );
}
