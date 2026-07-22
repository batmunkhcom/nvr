import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import apiClient from "../../api/client";

interface Props {
  cameraId: string;
}

/** Mini live preview for dashboard tiles — uses the low-bandwidth sub stream. */
export default function MiniLivePreview({ cameraId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const hlsPath = `/hls/${cameraId}_sub/index.m3u8`;

  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        await apiClient.post(`/cameras/${cameraId}/live/start?stream=sub`);
      } catch {}
      for (let i = 0; i < 15; i++) {
        if (cancelled) return;
        try {
          const resp = await fetch(hlsPath);
          if (resp.ok || resp.status === 302) {
            if (!cancelled) setReady(true);
            return;
          }
        } catch {}
        await new Promise((r) => setTimeout(r, 1000));
      }
    }
    start();
    return () => { cancelled = true; };
  }, [cameraId, hlsPath]);

  useEffect(() => {
    if (!ready || !videoRef.current || !Hls.isSupported()) return;
    const hls = new Hls({ enableWorker: false });
    hls.loadSource(hlsPath);
    hls.attachMedia(videoRef.current);
    return () => { hls.destroy(); };
  }, [ready, hlsPath]);

  return (
    <video ref={videoRef} muted autoPlay playsInline
      className="absolute inset-0 w-full h-full object-cover opacity-70"
    />
  );
}
