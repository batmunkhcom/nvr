# Stream Playback Guide

## Live View (WebRTC WHEP → LL-HLS fallback)

### Flow

1. Frontend calls `POST /api/v1/cameras/{id}/live/start?stream=sub`
2. API delegates to stream-manager via HTTP (`http://nvr-stream-manager:8001`)
3. **Sub**: stream-manager creates a MediaMTX `sourceOnDemand` pull path (MediaMTX fetches the camera itself). **Main**: FFmpeg libx264 relay-push to `rtsp://nvr-mediamtx:8554/{id}`
4. `useStreamPlayer` tries **WebRTC (WHEP)**: SDP offer → `POST /mtx/{id}_sub/whep` (MediaMTX :8889) → answer → ICE over UDP 8189 (<1s latency)
5. Any WebRTC failure → automatic fallback to **LL-HLS**: poll `/hls/{id}_sub/index.m3u8` → hls.js with `lowLatencyMode: true` (~2-4s)

### useStreamPlayer Hook (Frontend)

**All video playback MUST use the shared `useStreamPlayer` hook** (`src/hooks/useStreamPlayer.ts`):

```tsx
import { useStreamPlayer, type StreamType } from "../hooks/useStreamPlayer";

const { state, retrySec, attachVideo, startStream } = useStreamPlayer({
  cameraId,           // UUID string
  streamType,         // "main" | "sub"
  protocol,           // optional: "webrtc" (default) or "hls"
  pollAttempts,       // optional, default 60
  retryIntervalMs,    // optional, default 60000
});
```

### Return Values

| Value | Type | Description |
|-------|------|-------------|
| `state` | `"connecting"` \| `"loading"` \| `"playing"` \| `"retrying"` \| `"error"` | Current stream state |
| `retrySec` | `number` | Countdown seconds when in `retrying` state |
| `attachVideo` | `(el: HTMLVideoElement \| null) => void` | Ref callback for `<video>` element |
| `startStream` | `() => Promise<void>` | Manually retry/start |

### Usage Pattern

```tsx
<video ref={attachVideo} muted autoPlay playsInline
  className={state === "playing" ? "opacity-80" : "opacity-0"} />

{state === "connecting" && <Spinner label="Connecting..." />}
{state === "loading" && <Spinner label="Buffering..." />}
{state === "retrying" && <button onClick={startStream}>Retry ({retrySec}s)</button>}
{state === "playing" && <StreamToggle streamType={streamType} onChange={setStreamType} />}
```

### Where It's Used

- `MiniLivePreview.tsx` — dashboard grid tiles
- `CameraGrid.tsx:ExpandedView` — modal on single click
- `LiveViewPage.tsx` — full live view with PTZ

---

## Recording Playback (MP4 Progressive Download)

### Flow

1. Browser requests `/api/v1/recordings/{id}/stream`
2. API serves MP4 via HTTP Range requests:
   - Full file request (`Range: bytes=0-`) → `200 OK` (progressive download, browser buffers)
   - Partial request (seeking) → `206 Partial Content` + `Content-Range` header
3. Native `<video>` element plays MP4 — no hls.js needed

### RecordingPlayer Component

```tsx
// RecordingPlayer uses native <video> ONLY — NO hls.js
<video controls muted autoPlay playsInline preload="auto"
  src={`${streamUrl}?token=${authToken}`} />
```

### Key Behaviors

- **Playback speed controls**: 0.125x, 0.25x, 0.5x, 0.75x, 1x, 1.5x, 2x, 4x, 8x (slow/fast color coded)
- **Download button**: `?download=true` → `Content-Disposition: attachment`
- **Token auth**: `?token=` query parameter via `get_current_user`

---

## Browser Compatibility

| Feature | Chrome | Safari | Firefox |
|---------|--------|--------|---------|
| Live HLS (LL-HLS) | ✅ hls.js | ✅ hls.js | ✅ hls.js |
| Recording MP4 playback | ✅ Progressive `<video>` | ✅ Progressive `<video>` | ✅ Progressive `<video>` |
| CSP `script-src` enforcement | ⚠️ Strict (blocks `new Function()`) | Lenient | Moderate |
| `Range: bytes=0-` handling | Requires `206 Partial Content` | Accepts `200 OK` | Accepts `200 OK` |
| `pix_fmt=yuvj420p` full-range | ❌ Rejects | ✅ Accepts | ❌ Rejects |

### Design Decisions for Universal Compatibility

1. RecordingPlayer uses progressive MP4 download (NO hls.js) — avoids CSP `unsafe-eval` conflict
2. Recording engine normalizes all codecs to H.264 `yuv420p` `color_range=tv` — Chrome-safe format
3. Stream endpoint returns `200 OK` for full-file requests, `206 Partial Content` for seeking — satisfies Chrome's strict Range handling

---

## Troubleshooting Playback

See [Troubleshooting](Troubleshooting) page for common issues:
- CSP blocks hls.js in Chrome (works in Safari)
- Chrome vs Safari video playback differences
- HEVC codec normalization
- HTTP Range request handling
- `Content-Disposition` header issues
