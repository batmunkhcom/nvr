FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.34" \
    "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.30" "pydantic>=2.10" \
    "redis>=5.2" "httpx>=0.28" "websockets>=14.1" "structlog>=24.4" \
    "pyyaml>=6.0" "aiohttp>=3.11" "tenacity>=9.0" \
    "python-dateutil>=2.9" "psutil>=6.1" \
    "onvif-zeep-async>=3.1" "zeep>=4.3"

COPY services/stream-manager/ ./services/stream-manager/
COPY packages/ ./packages/
COPY config/ ./config/

CMD ["python", "-m", "services.stream_manager.app.main"]
