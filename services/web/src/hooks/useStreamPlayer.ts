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

const STALL_CHECK_S = 2;
const STALL_TRIGGER_S = 6;

export function useStreamPlayer({
  cameraId,
  streamType,
  pollAttempts = 30,
  retryIntervalMs = 60_000,
}: UseStreamPlayerOptions) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const abortRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stallMonitorRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startStreamRef = useRef<() => Promise<void>>(async () => {});

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

  const stopStallMonitor = useCallback(() => {
    if (stallMonitorRef.current) {
      clearInterval(stallMonitorRef.current);
      stallMonitorRef.current = null;
    }
  }, []);

  const startStallMonitor = useCallback(() => {
    stopStallMonitor();
    let lastTime = videoRef.current?.currentTime ?? 0;
    let stallCount = 0;
    stallMonitorRef.current = setInterval(() => {
      const v = videoRef.current;
      if (!v) { stallCount = 0; lastTime = 0; return; }
      const ct = v.currentTime;
      if (!v.paused && Math.abs(ct - lastTime) < 0.05) {
        stallCount++;
        if (stallCount >= STALL_TRIGGER_S / STALL_CHECK_S) {
          stopStallMonitor();
          cleanupHls();
          startStreamRef.current();
        }
      } else {
        stallCount = 0;
      }
      lastTime = ct;
    }, STALL_CHECK_S * 1000);
  }, [stopStallMonitor, cleanupHls]);

  const startCountdown = useCallback((seconds: number) => {
    clearTimers();
    setState("retrying");
    setRetrySec(seconds);
    countdownRef.current = setInterval(() => {
      setRetrySec((prev) => {
        if (prev <= 1) {
          if (countdownRef.current) clearInterval(countdownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [clearTimers]);

  const scheduleRetry = useCallback((delayMs: number) => {
    clearTimers();
    startCountdown(Math.ceil(delayMs / 1000));
    retryTimerRef.current = setTimeout(() => {
      if (!abortRef.current) startStreamRef.current();
    }, delayMs);
  }, [clearTimers, startCountdown]);

  const initHls = useCallback(() => {
    if (!videoRef.current || !Hls.isSupported()) { setState("error"); return; }
    cleanupHls();
    stopStallMonitor();
    const hls = new Hls({
      enableWorker: false,
      maxBufferLength: 30,
      maxMaxBufferLength: 60,
      maxBufferHole: 2.0,
      lowLatencyMode: false,
      liveDurationInfinity: false,
      liveSyncDurationCount: 5,
    });
    hlsRef.current = hls;

    let fatalCount = 0;
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      fatalCount = 0;
      if (!abortRef.current) {
        setState("playing");
        videoRef.current?.play().catch(() => {});
        startStallMonitor();
      }
    });
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) {
        fatalCount++;
        cleanupHls();
        stopStallMonitor();
        if (!abortRef.current) {
          const delay = Math.min(2000 * Math.pow(2, fatalCount - 1), 15000);
          scheduleRetry(delay);
        }
      }
    });
    const src = finalUrlRef.current || hlsPath;
    hls.loadSource(src);
    hls.attachMedia(videoRef.current);
  }, [hlsPath, cleanupHls, stopStallMonitor, startStallMonitor, scheduleRetry]);

  const destroyAll = useCallback(() => {
    stopStallMonitor();
    cleanupHls();
    clearTimers();
  }, [stopStallMonitor, cleanupHls, clearTimers]);

  const startStream = useCallback(async () => {
    if (abortRef.current || !cameraId) return;
    cleanupHls();
    stopStallMonitor();
    clearTimers();
    setErrorMsg(null);
    setState("connecting");

    let startFailed = false;
    try {
      const res = await apiClient.post(`/cameras/${cameraId}/live/start?stream=${streamType}`);
      const d = res.data?.data;
      if (d?.status === "cooldown") { scheduleRetry(Math.ceil((d.cooldown_remaining_s || 10) * 1000)); return; }
      if (d?.error && !d?.hls_url) {
        setErrorMsg(d.error);
        setState("error");
        return;
      }
    } catch {
      startFailed = true;
    }

    if (abortRef.current) return;
    setState("loading");

    await new Promise((r) => setTimeout(r, 600));

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
      scheduleRetry(retryIntervalMs);
    }
  }, [cameraId, streamType, hlsPath, pollAttempts, retryIntervalMs, cleanupHls, stopStallMonitor, clearTimers, initHls, scheduleRetry]);

  startStreamRef.current = startStream;

  const attachVideo = useCallback((el: HTMLVideoElement | null) => { videoRef.current = el; }, []);

  useEffect(() => {
    abortRef.current = false;
    startStream();
    return () => { abortRef.current = true; destroyAll(); };
  }, [cameraId, streamType]);

  return { state, retrySec, errorMsg, attachVideo, startStream };
}
