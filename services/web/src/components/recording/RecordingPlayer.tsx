import { useRef, useEffect } from "react";
import Hls from "hls.js";

interface Props {
  src: string;
  poster?: string;
  autoPlay?: boolean;
  controls?: boolean;
  className?: string;
  startOffset?: number; // seconds — seek position once metadata is loaded
}

export default function RecordingPlayer({ src, poster, autoPlay = true, controls = true, className = "", startOffset }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);

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
    <video
      ref={videoRef}
      controls={controls}
      poster={poster}
      className={`w-full bg-black rounded ${className}`}
      playsInline
    />
  );
}
