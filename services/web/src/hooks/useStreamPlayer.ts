import { useEffect, useRef, useState, useCallback } from "react";
import Hls from "hls.js";
import apiClient from "../api/client";

export type StreamState = "connecting" | "loading" | "playing" | "retrying" | "error";
export type StreamType = "main" | "sub";

interface UseStreamPlayerOptions {
  cameraId: string;
  streamType: StreamType;
  pollAttempts?: number;
  retryIntervalMs?: number;
}

export function useStreamPlayer({
  cameraId,
  streamType,
  pollAttempts = 30,
  retryIntervalMs = 10_000,
}: UseStreamPlayerOptions) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const abortRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [state, setState] = useState<StreamState>("connecting");
  const [retrySec, setRetrySec] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const finalUrlRef = useRef<string | null>(null);

  const suffix = streamType === "sub" ? "_sub" : "";
  const hlsPath = cameraId ? `/hls/${cameraId}${suffix}/index.m3u8` : "";

  const clearTimers = useCallback(() => {
    if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
  }, []);

  const cleanupHls = useCallback(() => {
    if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null; }
  }, []);

  const scheduleRetry = useCallback(() => {
    clearTimers();
    setState("retrying");
    setRetrySec(Math.ceil(retryIntervalMs / 1000));
    countdownRef.current = setInterval(() => {
      setRetrySec((prev) => { if (prev <= 1) { if (countdownRef.current) clearInterval(countdownRef.current); return 0; } return prev - 1; });
    }, 1000);
    retryTimerRef.current = setTimeout(() => {
      if (!abortRef.current) startStream();
    }, retryIntervalMs);
  }, [retryIntervalMs, clearTimers]);

  const initHls = useCallback(() => {
    if (!videoRef.current || !Hls.isSupported()) { setState("error"); return; }
    cleanupHls();
    const hls = new Hls({
      enableWorker: false,
      maxBufferLength: 10,
      maxMaxBufferLength: 15,
      maxBufferHole: 1.0,
      lowLatencyMode: true,
      liveDurationInfinity: false,
      liveSyncDurationCount: 3,
    });
    hlsRef.current = hls;

    let fatalCount = 0;
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      fatalCount = 0;
      if (!abortRef.current) { setState("playing"); videoRef.current?.play().catch(() => {}); }
    });
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) {
        fatalCount++;
        cleanupHls();
        if (!abortRef.current) {
          const delay = Math.min(2000 * Math.pow(2, fatalCount - 1), 15000);
          setRetrySec(Math.ceil(delay / 1000));
          setTimeout(() => { if (!abortRef.current) startStream(); }, delay);
        }
      }
    });
    const src = finalUrlRef.current || hlsPath;
    hls.loadSource(src);
    hls.attachMedia(videoRef.current);
  }, [hlsPath, cleanupHls, scheduleRetry]);

  const startStream = useCallback(async () => {
    if (abortRef.current || !cameraId) return;
    cleanupHls();
    clearTimers();
    setErrorMsg(null);
    setState("connecting");

    let startFailed = false;
    try {
      const res = await apiClient.post(`/cameras/${cameraId}/live/start?stream=${streamType}`);
      const d = res.data?.data;
      if (d?.status === "cooldown") { setRetrySec(Math.ceil(d.cooldown_remaining_s || 10)); scheduleRetry(); return; }
      if (d?.error && !d?.hls_url) {
        // explicit failure (e.g. camera has no stream URI configured)
        setErrorMsg(d.error);
        setState("error");
        return;
      }
    } catch {
      // live/start unreachable — the stream may already be running from
      // another session, so we still try HLS below
      startFailed = true;
    }

    if (abortRef.current) return;
    setState("loading");

    // give FFmpeg time to connect to MediaMTX before polling HLS
    await new Promise((r) => setTimeout(r, 600));

    // when the start call itself failed, only a couple of probes are needed
    // to confirm no already-running stream exists — fail fast
    const attempts = startFailed ? Math.min(pollAttempts, 3) : pollAttempts;
    for (let i = 0; i < attempts; i++) {
      if (abortRef.current) return;
      try {
        const resp = await fetch(hlsPath, { cache: "no-store" });
        if (resp.ok) {
          finalUrlRef.current = resp.url;
          if (!abortRef.current) initHls();
          return;
        }
      } catch { /* poll */ }
      await new Promise((r) => setTimeout(r, 500));
    }

    if (abortRef.current) return;
    if (startFailed) {
      setErrorMsg("Failed to start stream");
      setState("error");
    } else {
      scheduleRetry();
    }
  }, [cameraId, streamType, hlsPath, pollAttempts, cleanupHls, clearTimers, initHls, scheduleRetry]);

  const attachVideo = useCallback((el: HTMLVideoElement | null) => { videoRef.current = el; }, []);

  useEffect(() => {
    abortRef.current = false;
    startStream();
    return () => { abortRef.current = true; cleanupHls(); clearTimers(); };
  }, [cameraId, streamType]);

  return { state, retrySec, errorMsg, attachVideo, startStream };
}
