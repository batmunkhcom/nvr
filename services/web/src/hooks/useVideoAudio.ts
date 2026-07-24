import { useState, useCallback, useRef } from "react";

export function useVideoAudio(attachVideo: (el: HTMLVideoElement | null) => void) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [muted, setMuted] = useState(true);

  const mergedAttach = useCallback(
    (el: HTMLVideoElement | null) => {
      attachVideo(el);
      videoRef.current = el;
      if (el) setMuted(el.muted);
    },
    [attachVideo],
  );

  const toggleMute = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setMuted(video.muted);
  }, []);

  return { muted, toggleMute, attachVideo: mergedAttach };
}
