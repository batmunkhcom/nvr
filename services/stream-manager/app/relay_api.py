"""Stream Manager relay HTTP API — handles relay start/stop requests from nvr-api."""

from __future__ import annotations

from aiohttp import web

from .manager import StreamManager

routes = web.RouteTableDef()


@routes.post("/relay/start")
async def relay_start(request: web.Request) -> web.Response:
    body = await request.json()
    relay_key = body["relay_key"]
    rtsp_uri = body["rtsp_uri"]
    transport = body.get("transport", "tcp")
    target = body.get("target")
    bitrate = body.get("bitrate")  # optional: kbps value
    threads = body.get("threads")  # optional: -threads N

    try:
        await StreamManager.connect(
            relay_key, rtsp_uri, transport,
            force=body.get("force", False),
            bitrate=bitrate,
            threads=threads,
        )
    except Exception as exc:
        return web.json_response(
            {"hls_url": None, "status": "error", "error": str(exc)},
            status=500,
        )

    breaker = StreamManager._get_breaker(relay_key)
    if await breaker.is_open():
        remaining = breaker.cooldown_remaining()
        return web.json_response(
            {
                "hls_url": None,
                "status": "cooldown",
                "cooldown_remaining_s": round(remaining, 1),
            },
            status=503,
        )

    running = relay_key in StreamManager._processes and (
        StreamManager._processes[relay_key].returncode is None
    )

    mediamtx_target = target or "rtsp://127.0.0.1:8554"
    return web.json_response({
        "hls_url": f"/hls/{relay_key}/index.m3u8",
        "status": "started" if running else "pending",
        "mediamtx_target": mediamtx_target,
    })


@routes.post("/relay/stop")
async def relay_stop(request: web.Request) -> web.Response:
    body = await request.json()
    relay_key = body["relay_key"]
    await StreamManager.disconnect(relay_key)
    return web.json_response({"status": "stopped"})


@routes.get("/relay/status")
async def relay_status(request: web.Request) -> web.Response:
    relay_key = request.query.get("relay_key", "")
    is_active = relay_key in StreamManager._processes and (
        StreamManager._processes[relay_key].returncode is None
    )
    return web.json_response({"running": is_active})


async def start_relay_api(port: int = 8001) -> None:
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
