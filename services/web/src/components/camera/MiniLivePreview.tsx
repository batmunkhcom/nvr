import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import apiClient from "../../api/client";

interface Props {
  cameraId: string;
}

export default function MiniLivePreview({ cameraId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function start() {
      try {
        await apiClient.post(`/cameras/${cameraId}/live/start`);
      } catch {}
      for (let i = 0; i < 15; i++) {
        if (cancelled) return;
        try {
          const resp = await fetch(`/hls/${cameraId}/index.m3u8`);
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
  }, [cameraId]);

  useEffect(() => {
    if (!ready || !videoRef.current || !Hls.isSupported()) return;
    const hls = new Hls({ enableWorker: false });
    hls.loadSource(`/hls/${cameraId}/index.m3u8`);
    hls.attachMedia(videoRef.current);
    return () => { hls.destroy(); };
  }, [ready, cameraId]);

  return (
    <video ref={videoRef} muted autoPlay playsInline
      className="absolute inset-0 w-full h-full object-cover opacity-70"
    />
  );
}
