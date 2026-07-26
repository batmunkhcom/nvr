import { useState, useCallback, useRef, type WheelEvent, type MouseEvent } from "react";

const MAX_SCALE = 16;
const STEP = 1.3;
const MIN_SCALE = 1;

interface Rect {
    left: number;
    top: number;
    width: number;
    height: number;
}

interface ZoomOptions {
    marquee?: boolean;
}

export function useVideoZoom(opts?: ZoomOptions) {
    const marqueeMode = opts?.marquee ?? false;
    const [scale, setScale] = useState(1);
    const [dx, setDx] = useState(0);
    const [dy, setDy] = useState(0);
    const [marquee, setMarquee] = useState<Rect | null>(null);
    const dragging = useRef(false);
    const drawingRect = useRef(false);
    const startPoint = useRef({ x: 0, y: 0 });
    const last = useRef({ x: 0, y: 0 });
    const containerRef = useRef<DOMRect | null>(null);
    const marqueeRef = useRef<Rect | null>(null);

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
            return Math.max(n, MIN_SCALE);
        });
    }, []);
    const reset = useCallback(() => {
        setScale(1);
        setDx(0);
        setDy(0);
        setMarquee(null);
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

    const onMouseDown = useCallback((e: MouseEvent) => {
        if (e.button !== 0) return; // left click only
        const rect = e.currentTarget.getBoundingClientRect();
        containerRef.current = rect;

        if (marqueeMode && scale <= 1) {
            // at 1x: draw rectangle to zoom in
            drawingRect.current = true;
            startPoint.current = { x: e.clientX, y: e.clientY };
            setMarquee(null);
        } else if (marqueeMode && e.shiftKey) {
            // zoomed + shift: draw rectangle for deeper zoom
            drawingRect.current = true;
            startPoint.current = { x: e.clientX, y: e.clientY };
            setMarquee(null);
        } else if (scale > 1) {
            // zoomed: pan
            dragging.current = true;
            last.current = { x: e.clientX, y: e.clientY };
        } else if (marqueeMode) {
            // marquee mode but scale=1 (fallback): draw rectangle
            drawingRect.current = true;
            startPoint.current = { x: e.clientX, y: e.clientY };
            setMarquee(null);
        }
    }, [scale, marqueeMode]);

    const onMouseMove = useCallback((e: MouseEvent) => {
        if (drawingRect.current && containerRef.current) {
            const cr = containerRef.current;
            const x1 = Math.min(startPoint.current.x, e.clientX) - cr.left;
            const y1 = Math.min(startPoint.current.y, e.clientY) - cr.top;
            const x2 = Math.max(startPoint.current.x, e.clientX) - cr.left;
            const y2 = Math.max(startPoint.current.y, e.clientY) - cr.top;
            const w = x2 - x1;
            const h = y2 - y1;
            if (w > 5 || h > 5) {
                const rect = { left: x1, top: y1, width: w, height: h };
                marqueeRef.current = rect;
                setMarquee(rect);
            }
            return;
        }
        if (!dragging.current) return;
        setDx((x) => x + e.clientX - last.current.x);
        setDy((y) => y + e.clientY - last.current.y);
        last.current = { x: e.clientX, y: e.clientY };
    }, []);

    const onMouseUp = useCallback(() => {
        if (drawingRect.current && marqueeRef.current && containerRef.current) {
            drawingRect.current = false;
            const mr = marqueeRef.current;
            const cr = containerRef.current;
            const targetScale = Math.min(
                cr.width / mr.width,
                cr.height / mr.height,
            );
            const clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, targetScale));
            const centerX = mr.left + mr.width / 2;
            const centerY = mr.top + mr.height / 2;
            const newDx = (cr.width / 2 - centerX);
            const newDy = (cr.height / 2 - centerY);
            setScale(clamped);
            setDx(newDx);
            setDy(newDy);
        }
        if (drawingRect.current) {
            drawingRect.current = false;
        }
        marqueeRef.current = null;
        setMarquee(null);
        dragging.current = false;
    }, []);

    const onDoubleClick = useCallback(() => reset(), [reset]);

    const transformStyle = scale > 1
        ? {
              transform: `scale(${scale}) translate(${dx}px, ${dy}px)`,
              transformOrigin: "0 0",
              transition: "transform 0.15s ease-out",
          }
        : {
              transform: undefined,
              transformOrigin: "center center",
              transition: "transform 0.15s ease-out",
          };

    return {
        scale,
        zoomIn,
        zoomOut,
        reset,
        transformStyle,
        marquee,
        onWheel,
        onMouseDown,
        onMouseMove,
        onMouseUp,
        onDoubleClick,
    };
}
