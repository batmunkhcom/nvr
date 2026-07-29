import { useEffect, useRef, useState, useCallback } from "react";
import Hls from "hls.js";
import apiClient from "../api/client";

export type StreamState = "connecting" | "loading" | "playing" | "retrying" | "error";
export type StreamType = "main" | "sub";
export type StreamProtocol = "webrtc" | "hls";

interface UseStreamPlayerOptions {
  cameraId: string;
  streamType: StreamType;
  /** Preferred protocol. "webrtc" (default) falls back to HLS on failure. */
  protocol?: StreamProtocol;
  pollAttempts?: number;
  retryIntervalMs?: number;
}

const STALL_CHECK_S = 2;
const STALL_TRIGGER_S = 6;
const MAX_SOFT_RECOVERIES = 2;
const RTC_ICE_TIMEOUT_MS = 8000;
const RTC_GATHER_TIMEOUT_MS = 3000;
const HLS_POLL_INTERVAL_MS = 750;

export function useStreamPlayer({
  cameraId,
  streamType,
  protocol = "webrtc",
  pollAttempts = 60,
  retryIntervalMs = 60_000,
}: UseStreamPlayerOptions) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const rtcSessionRef = useRef<string | null>(null);
  // Per-run token: each startStream() call increments it; async continuations
  // check identity instead of a shared boolean (fixes SUB↔MAIN toggle race).
  const runIdRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stallMonitorRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startStreamRef = useRef<() => Promise<void>>(async () => {});
  // Survives restarts so fatal-error backoff actually escalates.
  const fatalCountRef = useRef(0);
  const softRecoveriesRef = useRef(0);
  // Set when WebRTC fails once — subsequent retries go straight to HLS.
  const rtcDisabledRef = useRef(false);

  const [state, setState] = useState<StreamState>("connecting");
  const [retrySec, setRetrySec] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const finalUrlRef = useRef<string | null>(null);

  const suffix = streamType === "sub" ? "_sub" : "";
  const streamPath = cameraId ? `${cameraId}${suffix}` : "";
  const hlsPath = cameraId ? `/hls/${streamPath}/index.m3u8` : "";
  const whepPath = cameraId ? `/mtx/${streamPath}/whep` : "";

  const isCurrent = useCallback((runId: number) => runId === runIdRef.current, []);

  const clearTimers = useCallback(() => {
    if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
  }, []);

  const cleanupHls = useCallback(() => {
    if (hlsRef.current) { hlsRef.current.destroy(); hlsRef.current = null; }
  }, []);

  const cleanupRtc = useCallback(() => {
    if (rtcSessionRef.current) {
      // Best-effort WHEP session teardown (fire-and-forget).
      fetch(rtcSessionRef.current, { method: "DELETE" }).catch(() => {});
      rtcSessionRef.current = null;
    }
    if (pcRef.current) {
      pcRef.current.ontrack = null;
      pcRef.current.oniceconnectionstatechange = null;
      pcRef.current.close();
      pcRef.current = null;
    }
    const v = videoRef.current;
    if (v?.srcObject) {
      (v.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      v.srcObject = null;
    }
  }, []);

  const stopStallMonitor = useCallback(() => {
    if (stallMonitorRef.current) {
      clearInterval(stallMonitorRef.current);
      stallMonitorRef.current = null;
    }
  }, []);

  const startStallMonitor = useCallback(() => {
    stopStallMonitor();
    softRecoveriesRef.current = 0;
    let lastTime = videoRef.current?.currentTime ?? 0;
    let stallCount = 0;
    stallMonitorRef.current = setInterval(() => {
      const v = videoRef.current;
      if (!v) { stallCount = 0; lastTime = 0; return; }
      const ct = v.currentTime;
      if (!v.paused && Math.abs(ct - lastTime) < 0.05) {
        stallCount++;
        if (stallCount >= STALL_TRIGGER_S / STALL_CHECK_S) {
          stallCount = 0;
          softRecoveriesRef.current += 1;
          const hls = hlsRef.current;
          if (hls && softRecoveriesRef.current <= MAX_SOFT_RECOVERIES) {
            // Soft recovery first: re-sync to the live edge without a full restart.
            hls.startLoad(-1);
            try {
              if (v.seekable.length > 0) {
                v.currentTime = Math.max(0, v.seekable.end(v.seekable.length - 1) - 0.5);
              }
            } catch { /* seekable not ready */ }
          } else {
            stopStallMonitor();
            cleanupHls();
            cleanupRtc();
            startStreamRef.current();
          }
        }
      } else {
        stallCount = 0;
      }
      lastTime = ct;
    }, STALL_CHECK_S * 1000);
  }, [stopStallMonitor, cleanupHls, cleanupRtc]);

  const startCountdown = useCallback((seconds: number) => {
    clearTimers();
    setState("retrying");
    setRetrySec(seconds);
    countdownRef.current = setInterval(() => {
      setRetrySec((prev) => {
        if (prev <= 1) {
          if (countdownRef.current) {
            clearInterval(countdownRef.current);
            countdownRef.current = null;
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [clearTimers]);

  const scheduleRetry = useCallback((delayMs: number) => {
    clearTimers();
    startCountdown(Math.ceil(delayMs / 1000));
    const runId = runIdRef.current;
    retryTimerRef.current = setTimeout(() => {
      if (isCurrent(runId)) startStreamRef.current();
    }, delayMs);
  }, [clearTimers, startCountdown, isCurrent]);

  /** Escalating backoff for fatal errors (persists across restarts). */
  const scheduleFatalRetry = useCallback(() => {
    fatalCountRef.current += 1;
    const delay = Math.min(2000 * Math.pow(2, fatalCountRef.current - 1), 15000);
    scheduleRetry(delay);
  }, [scheduleRetry]);

  // ── HLS (LL-HLS) playback ────────────────────────────────────────────────

  const initHls = useCallback((runId: number) => {
    if (!videoRef.current || !Hls.isSupported()) { setState("error"); return; }
    cleanupHls();
    cleanupRtc();
    stopStallMonitor();
    const hls = new Hls({
      // Demux in a worker — 11 grid tiles otherwise share the main thread.
      enableWorker: true,
      maxBufferLength: 30,
      maxMaxBufferLength: 60,
      maxBufferHole: 2.0,
      // LL-HLS: MediaMTX serves partial segments; latency target comes from
      // the playlist hold-back (~3x 500ms parts) instead of full segments.
      lowLatencyMode: true,
      liveDurationInfinity: false,
    });
    hlsRef.current = hls;

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      fatalCountRef.current = 0;
      if (isCurrent(runId)) {
        setState("playing");
        videoRef.current?.play().catch(() => {});
        startStallMonitor();
      }
    });
    hls.on(Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) {
        cleanupHls();
        stopStallMonitor();
        if (isCurrent(runId)) scheduleFatalRetry();
      }
    });
    const src = finalUrlRef.current || hlsPath;
    hls.loadSource(src);
    hls.attachMedia(videoRef.current);
  }, [hlsPath, cleanupHls, cleanupRtc, stopStallMonitor, startStallMonitor, scheduleFatalRetry, isCurrent]);

  const startHlsPolling = useCallback(async (runId: number) => {
    setState("loading");
    await new Promise((r) => setTimeout(r, 600));
    for (let i = 0; i < pollAttempts; i++) {
      if (!isCurrent(runId)) return;
      try {
        const resp = await fetch(hlsPath, { cache: "no-store" });
        if (resp.ok) {
          finalUrlRef.current = resp.url;
          if (isCurrent(runId)) initHls(runId);
          return;
        }
      } catch { /* poll */ }
      await new Promise((r) => setTimeout(r, HLS_POLL_INTERVAL_MS));
    }
    if (isCurrent(runId)) scheduleRetry(retryIntervalMs);
  }, [hlsPath, pollAttempts, retryIntervalMs, initHls, scheduleRetry, isCurrent]);

  // ── WebRTC (WHEP) playback ───────────────────────────────────────────────

  const startWebRtc = useCallback(async (runId: number): Promise<boolean> => {
    const video = videoRef.current;
    if (!video || typeof RTCPeerConnection === "undefined") return false;

    setState("loading");
    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    try {
      pc.addTransceiver("video", { direction: "recvonly" });
      pc.addTransceiver("audio", { direction: "recvonly" });

      pc.ontrack = (ev) => {
        if (!isCurrent(runId) || pcRef.current !== pc) return;
        const stream = ev.streams[0] || new MediaStream([ev.track]);
        const v = videoRef.current;
        if (v) {
          v.srcObject = stream;
          v.play().catch(() => {});
        }
        fatalCountRef.current = 0;
        setState("playing");
        startStallMonitor();
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // Gather ICE candidates (LAN: host candidates only, no STUN).
      await new Promise<void>((resolve) => {
        if (pc.iceGatheringState === "complete") { resolve(); return; }
        const t = setTimeout(resolve, RTC_GATHER_TIMEOUT_MS);
        pc.addEventListener("icegatheringstatechange", () => {
          if (pc.iceGatheringState === "complete") { clearTimeout(t); resolve(); }
        });
      });
      if (!isCurrent(runId)) return false;

      const resp = await fetch(whepPath, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: pc.localDescription?.sdp ?? "",
      });
      if (!resp.ok) throw new Error(`whep ${resp.status}`);

      const loc = resp.headers.get("location");
      if (loc) {
        try {
          const u = new URL(loc, window.location.origin);
          rtcSessionRef.current = `/mtx${u.pathname}`;
        } catch { /* session teardown optional */ }
      }

      const answerSdp = await resp.text();
      await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

      // Wait for ICE connectivity before declaring success.
      await new Promise<void>((resolve, reject) => {
        if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
          resolve(); return;
        }
        const t = setTimeout(() => reject(new Error("ice timeout")), RTC_ICE_TIMEOUT_MS);
        pc.addEventListener("iceconnectionstatechange", () => {
          if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
            clearTimeout(t); resolve();
          } else if (pc.iceConnectionState === "failed") {
            clearTimeout(t); reject(new Error("ice failed"));
          }
        });
      });

      // After establishment, treat disconnects as fatal → full restart.
      pc.oniceconnectionstatechange = () => {
        if (!isCurrent(runId) || pcRef.current !== pc) return;
        if (pc.iceConnectionState === "failed" || pc.iceConnectionState === "closed") {
          cleanupRtc();
          stopStallMonitor();
          scheduleFatalRetry();
        }
      };
      return true;
    } catch {
      if (pcRef.current === pc) cleanupRtc();
      else pc.close();
      return false;
    }
  }, [whepPath, cleanupRtc, stopStallMonitor, scheduleFatalRetry, startStallMonitor, isCurrent]);

  // ── Main start flow ──────────────────────────────────────────────────────

  const startStream = useCallback(async () => {
    const runId = ++runIdRef.current;
    if (!cameraId) return;
    cleanupHls();
    cleanupRtc();
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

    if (!isCurrent(runId)) return;

    // WebRTC first (sub-second latency); fall back to LL-HLS on any failure.
    if (!startFailed && protocol === "webrtc" && !rtcDisabledRef.current) {
      const ok = await startWebRtc(runId);
      if (!isCurrent(runId)) return;
      if (ok) return;
      rtcDisabledRef.current = true;
    }

    if (startFailed) {
      // Server-side start failed: short probe budget, then report.
      for (let i = 0; i < 3; i++) {
        if (!isCurrent(runId)) return;
        try {
          const resp = await fetch(hlsPath, { cache: "no-store" });
          if (resp.ok) {
            finalUrlRef.current = resp.url;
            if (isCurrent(runId)) initHls(runId);
            return;
          }
        } catch { /* probe */ }
        await new Promise((r) => setTimeout(r, 500));
      }
      if (!isCurrent(runId)) return;
      setErrorMsg("Failed to start stream");
      setState("error");
      return;
    }

    await startHlsPolling(runId);
  }, [cameraId, streamType, protocol, hlsPath, cleanupHls, cleanupRtc, stopStallMonitor, clearTimers, scheduleRetry, startWebRtc, startHlsPolling, initHls, isCurrent]);

  useEffect(() => {
    startStreamRef.current = startStream;
  }, [startStream]);

  const attachVideo = useCallback((el: HTMLVideoElement | null) => { videoRef.current = el; }, []);

  useEffect(() => {
    startStream();

    // Stop consuming while the tab is hidden (MediaMTX reader count drops;
    // the idle reaper can then stop the relay). Resume on visibility.
    const onVisibility = () => {
      if (document.hidden) {
        runIdRef.current += 1;  // invalidate in-flight async work
        stopStallMonitor();
        cleanupHls();
        cleanupRtc();
        clearTimers();
      } else {
        rtcDisabledRef.current = false;  // re-probe WebRTC on return
        startStreamRef.current();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      runIdRef.current += 1;
      document.removeEventListener("visibilitychange", onVisibility);
      stopStallMonitor();
      cleanupHls();
      cleanupRtc();
      clearTimers();
    };
  }, [cameraId, streamType]);

  return { state, retrySec, errorMsg, attachVideo, startStream };
}
