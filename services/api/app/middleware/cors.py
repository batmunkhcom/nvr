"""CORS middleware configuration."""

from fastapi.middleware.cors import CORSMiddleware

from ..core.config import settings


def setup_cors(app):
    origins = settings.api_cors_origins.split(",") if settings.api_cors_origins != "*" else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
