import { useEffect, useRef, useState } from "react";
import MiniLivePreview from "./MiniLivePreview";

interface Props {
  cameraId: string;
}

export default function LazyMiniPreview({ cameraId }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          obs.disconnect();
        }
      },
      { rootMargin: "200px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div ref={ref} className="absolute inset-0">
      {visible ? (
        <MiniLivePreview cameraId={cameraId} />
      ) : (
        <div className="absolute inset-0 bg-gray-900/50 flex items-center justify-center">
          <div className="h-2 w-2 rounded-full bg-gray-700" />
        </div>
      )}
    </div>
  );
}
