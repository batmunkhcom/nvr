import { useState, useCallback, useRef, type WheelEvent, type MouseEvent } from "react";

const MAX_SCALE = 4;
const STEP = 1.5;

export function useVideoZoom() {
  const [scale, setScale] = useState(1);
  const [dx, setDx] = useState(0);
  const [dy, setDy] = useState(0);
  const dragging = useRef(false);
  const last = useRef({ x: 0, y: 0 });

  const zoomIn = useCallback(() => setScale((s) => Math.min(s * STEP, MAX_SCALE)), []);
  const zoomOut = useCallback(() => {
    setScale((s) => {
      const n = s / STEP;
      if (n < 1.05) {
        setDx(0);
        setDy(0);
        return 1;
      }
      setDx((x) => x / STEP);
      setDy((y) => y / STEP);
      return n;
    });
  }, []);
  const reset = useCallback(() => {
    setScale(1);
    setDx(0);
    setDy(0);
  }, []);

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left - rect.width / 2;
    const my = e.clientY - rect.top - rect.height / 2;
    const factor = e.deltaY < 0 ? STEP : 1 / STEP;
    setScale((s) => {
      const n = s * factor;
      if (n < 1.05) {
        setDx(0);
        setDy(0);
        return 1;
      }
      const clamped = Math.min(n, MAX_SCALE);
      setDx((x) => x + mx * (s - clamped) / s);
      setDy((y) => y + my * (s - clamped) / s);
      return clamped;
    });
  }, []);

  const onMouseDown = useCallback(
    (e: MouseEvent) => {
      if (scale <= 1) return;
      dragging.current = true;
      last.current = { x: e.clientX, y: e.clientY };
    },
    [scale],
  );

  const onMouseMove = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    setDx((x) => x + e.clientX - last.current.x);
    setDy((y) => y + e.clientY - last.current.y);
    last.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseUp = useCallback(() => {
    dragging.current = false;
  }, []);

  const onDoubleClick = useCallback(() => reset(), [reset]);

  const transformStyle = {
    transform: scale > 1 ? `scale(${scale}) translate(${dx}px, ${dy}px)` : undefined,
    transformOrigin: scale > 1 ? "0 0" : "center center",
  };

  return {
    scale,
    zoomIn,
    zoomOut,
    reset,
    transformStyle,
    onWheel,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onDoubleClick,
    cursorClass: scale > 1 ? "cursor-grab" : "",
  };
}
