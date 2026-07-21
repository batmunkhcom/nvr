FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libpq-dev gcc libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.34" \
    "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.30" "pydantic>=2.10" \
    "redis>=5.2" "httpx>=0.28" "structlog>=24.4" "pyyaml>=6.0" \
    "aiohttp>=3.11" "opencv-python-headless>=4.10" "numpy>=2.2" \
    "psutil>=6.1" "tenacity>=9.0" "python-dateutil>=2.9"

COPY services/recording-engine/ ./services/recording-engine/
COPY packages/ ./packages/

CMD ["python", "-m", "services.recording_engine.app.main"]
