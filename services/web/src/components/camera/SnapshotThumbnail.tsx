import { useEffect, useState, useRef } from "react";
import apiClient from "../../api/client";

interface Props {
  cameraId: string;
  className?: string;
}

export default function SnapshotThumbnail({ cameraId, className = "" }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    setSrc(null);
    setError(false);

    apiClient
      .post(`/cameras/${cameraId}/snapshot`)
      .then((res) => {
        if (!mountedRef.current) return;
        const url = res.data?.data?.snapshot_url;
        if (url) setSrc(url);
        else setError(true);
      })
      .catch(() => {
        if (mountedRef.current) setError(true);
      });

    return () => {
      mountedRef.current = false;
    };
  }, [cameraId]);

  if (error || !src) return null;

  return (
    <img
      src={src}
      alt="Camera snapshot"
      className={`absolute inset-0 w-full h-full object-cover ${className}`}
    />
  );
}
