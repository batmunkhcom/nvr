import { useRef, useEffect } from "react";
import Hls from "hls.js";

interface Props {
  src: string;
  poster?: string;
  autoPlay?: boolean;
  controls?: boolean;
  className?: string;
}

export default function RecordingPlayer({ src, poster, autoPlay = true, controls = true, className = "" }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (src.endsWith(".m3u8") && Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoPlay) video.play().catch(() => {});
      });
      return () => {
        hls.destroy();
      };
    }

    video.src = src;
    if (autoPlay) video.play().catch(() => {});

    return () => {
      video.pause();
      video.src = "";
      video.load();
    };
  }, [src, autoPlay]);

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
