"""FastAPI application factory with lifespan and exception handlers."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .api.v1 import router as v1_router
from .core.config import settings
from .core.database import engine
from .core.redis import close_redis, get_redis
from .middleware.cors import setup_cors
from .middleware.logging import RequestLoggingMiddleware

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting", version="0.1.0", env=settings.api_log_level)
    await get_redis()
    yield
    await close_redis()
    await engine.dispose()
    logger.info("app_stopped")


app = FastAPI(
    title="NVR System API",
    version="0.1.0",
    description="Network Video Recorder System — API Gateway",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

setup_cors(app)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "unknown")
    logger.error("unhandled_exception", error=str(exc), path=str(request.url), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "data": None,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "trace_id": trace_id,
            },
        },
    )


@app.get("/")
async def root():
    return {"status": "ok", "service": "nvr-api", "version": "0.1.0"}


app.include_router(v1_router)
