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

    result = await StreamManager.connect(relay_key, rtsp_uri, transport)

    mediamtx_target = target or "rtsp://127.0.0.1:8554"
    hls_id = relay_key
    if hls_id.endswith("_sub"):
        hls_id = hls_id
    else:
        hls_id = relay_key

    return web.json_response({
        "hls_url": f"/hls/{hls_id}/index.m3u8",
        "status": "started",
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
