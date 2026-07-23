import { useEffect, useRef, useCallback } from "react";

type WsMessage = {
  type: "camera_status" | "event";
  camera_id?: string;
  status?: string;
  connection_error?: string | null;
  event?: Record<string, unknown>;
};

export function useNvrWebSocket(
  onCameraStatus?: (cameraId: string, status: string, error: string | null) => void,
  onEvent?: (event: Record<string, unknown>) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef(0);
  const callbacksRef = useRef({ onCameraStatus, onEvent });
  callbacksRef.current = { onCameraStatus, onEvent };

  const connect = useCallback(() => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/v1/ws?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => { reconnectRef.current = 0; };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as WsMessage;
        if (msg.type === "camera_status" && msg.camera_id && callbacksRef.current.onCameraStatus) {
          callbacksRef.current.onCameraStatus(msg.camera_id, msg.status || "", msg.connection_error || null);
        } else if (msg.type === "event" && msg.event && callbacksRef.current.onEvent) {
          callbacksRef.current.onEvent(msg.event);
        }
      } catch { /* ignore malformed */ }
    };
    ws.onclose = () => {
      wsRef.current = null;
      const delay = Math.min(1000 * (reconnectRef.current + 1), 10000);
      reconnectRef.current++;
      setTimeout(connect, delay);
    };
    ws.onerror = () => { ws.close(); };
  }, []);

  useEffect(() => {
    connect();
    return () => { wsRef.current?.close(); };
  }, [connect]);

  return wsRef;
}
