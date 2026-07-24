import { useEffect, useRef, useCallback } from "react";

type WsMessage = {
  type: "camera_status" | "event" | "network_metric";
  camera_id?: string;
  status?: string;
  connection_error?: string | null;
  event?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
};

type WsCallbacks = {
  onCameraStatus?: (cameraId: string, status: string, error: string | null) => void;
  onEvent?: (event: Record<string, unknown>) => void;
  onNetworkMetric?: (cameraId: string, metrics: Record<string, unknown>) => void;
};

let globalWs: WebSocket | null = null;
let globalReconnectTimeout: ReturnType<typeof setTimeout> | null = null;
let globalReconnectCount = 0;
const subscribers = new Set<React.MutableRefObject<WsCallbacks>>();

function globalConnect() {
  if (globalReconnectTimeout) {
    clearTimeout(globalReconnectTimeout);
    globalReconnectTimeout = null;
  }

  const token = localStorage.getItem("access_token");
  if (!token) return;

  if (globalWs) {
    globalWs.onclose = null;
    globalWs.onopen = null;
    globalWs.onmessage = null;
    globalWs.close();
    globalWs = null;
  }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/v1/ws?token=${token}`);
  globalWs = ws;

  ws.onopen = () => {
    console.log("[WS] connected");
    globalReconnectCount = 0;
  };

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data) as WsMessage;
      subscribers.forEach((ref) => {
        const cb = ref.current;
        if (msg.type === "camera_status" && msg.camera_id && cb.onCameraStatus) {
          cb.onCameraStatus(msg.camera_id, msg.status || "", msg.connection_error || null);
        } else if (msg.type === "event" && msg.event && cb.onEvent) {
          cb.onEvent(msg.event);
        } else if (msg.type === "network_metric" && msg.camera_id && cb.onNetworkMetric) {
          cb.onNetworkMetric(msg.camera_id, msg.metrics || {});
        }
      });
    } catch { /* ignore malformed */ }
  };

  ws.onclose = () => {
    console.log("[WS] closed");
    globalWs = null;
    if (subscribers.size === 0) return;
    const delay = Math.min(1000 * (globalReconnectCount + 1), 10000);
    globalReconnectCount++;
    globalReconnectTimeout = setTimeout(globalConnect, delay);
  };
}

export function useNvrWebSocket(
  onCameraStatus?: (cameraId: string, status: string, error: string | null) => void,
  onEvent?: (event: Record<string, unknown>) => void,
  onNetworkMetric?: (cameraId: string, metrics: Record<string, unknown>) => void,
) {
  const callbacksRef = useRef<WsCallbacks>({ onCameraStatus, onEvent, onNetworkMetric });
  callbacksRef.current = { onCameraStatus, onEvent, onNetworkMetric };

  useEffect(() => {
    subscribers.add(callbacksRef);

    if (!globalWs || globalWs.readyState === WebSocket.CLOSED || globalWs.readyState === WebSocket.CLOSING) {
      globalConnect();
    }

    return () => {
      subscribers.delete(callbacksRef);
      setTimeout(() => {
        if (subscribers.size === 0 && globalWs) {
          if (globalReconnectTimeout) {
            clearTimeout(globalReconnectTimeout);
            globalReconnectTimeout = null;
          }
          globalWs.onclose = null;
          globalWs.close();
          globalWs = null;
        }
      }, 100);
    };
  }, []);

  return useCallback(() => globalWs, []);
}
