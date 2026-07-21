FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.34" \
    "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.30" "alembic>=1.14" \
    "pydantic>=2.10" "pydantic-settings>=2.7" "redis>=5.2" \
    "python-jose[cryptography]>=3.3" "passlib[bcrypt]>=1.7" \
    "httpx>=0.28" "python-multipart>=0.0.18" "websockets>=14.1" \
    "structlog>=24.4" "pyyaml>=6.0" "aiohttp>=3.11" \
    "tenacity>=9.0" "python-dateutil>=2.9" "prometheus-client>=0.21" "bcrypt>=4.0,<5.0"

COPY services/api/ ./services/api/
COPY packages/ ./packages/
COPY config/ ./config/

EXPOSE 8000

CMD ["uvicorn", "services.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
