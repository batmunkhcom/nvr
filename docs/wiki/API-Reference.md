# API Reference

All endpoints under `/api/v1/`. Responses wrapped in `{"data": ...}`.

## Authentication

```
POST /api/v1/auth/login          # JWT login — returns access + refresh tokens
POST /api/v1/auth/refresh        # Token refresh — uses httpOnly cookie
```

## Cameras

```
GET    /api/v1/cameras                        # List cameras (paginated, filtered)
POST   /api/v1/cameras                        # Add camera
GET    /api/v1/cameras/{id}                   # Get camera details
PATCH  /api/v1/cameras/{id}                   # Update camera
DELETE /api/v1/cameras/{id}                   # Delete camera
POST   /api/v1/cameras/{id}/test              # Test connection
POST   /api/v1/cameras/{id}/live/start        # Start live relay (stream=main|sub)
POST   /api/v1/cameras/{id}/live/stop         # Stop live relay
GET    /api/v1/cameras/{id}/live/status       # Relay status
POST   /api/v1/cameras/{id}/ptz               # PTZ control
POST   /api/v1/cameras/discover               # Start discovery scan
GET    /api/v1/cameras/discover/{id}/status   # Scan status
```

## Recordings

```
GET    /api/v1/recordings                     # List recordings (paginated, filtered)
GET    /api/v1/recordings/{id}                # Get recording details
GET    /api/v1/recordings/{id}/stream         # Stream recording (HTTP Range — 206 Partial Content for seeking)
GET    /api/v1/recordings/{id}/thumbnail      # Get thumbnail JPEG
POST   /api/v1/recordings/bulk-delete         # Bulk delete by IDs, camera, or date range
GET    /api/v1/recordings/timeline            # Per-day timeline bar data
```

## Events

```
GET    /api/v1/events                         # List events (paginated, filtered)
GET    /api/v1/events/{id}                    # Get event details
GET    /api/v1/events/{id}/snapshot           # Get event snapshot (token auth via ?token=)
PATCH  /api/v1/events/{id}/acknowledge        # Acknowledge event
WS     /api/v1/events/stream                  # Real-time event WebSocket
```

## Network Monitoring

```
GET    /api/v1/network/metrics                # Latest metrics all cameras
GET    /api/v1/network/metrics/{id}           # Latest metrics one camera
GET    /api/v1/network/metrics/{id}/history   # Historical metrics (time-range selector)
GET    /api/v1/network/summary                # Dashboard summary stats
```

## Storage & System

```
GET    /api/v1/storage/usage                  # Storage usage statistics
GET    /api/v1/locations                      # List locations (CRUD)
GET    /api/v1/users                          # List users (admin CRUD)
GET    /api/v1/system/health                  # System health check
GET    /api/v1/system/config                  # System config values
PATCH  /api/v1/system/config                  # Update config
```

## WebSocket

```
WS     /api/v1/ws                             # Camera status + events + network_metric pushes
```

---

## Response Format

All endpoints return:

```json
{"data": {...}}
```

Frontend unwraps: `r.data.data` (axios), `json.data` (fetch).

## Media Auth

`<img>` and `<video>` tags use `?token=` query parameter which passes through `get_current_user` for authentication.
