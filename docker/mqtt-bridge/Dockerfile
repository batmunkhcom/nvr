FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir "redis>=5.2" "paho-mqtt>=2.1" \
    "structlog>=24.4" "pyyaml>=6.0" "pydantic>=2.10"

COPY services/mqtt-bridge/ ./services/mqtt_bridge/
COPY packages/ ./packages/

ENV PYTHONPATH=/app:/app/packages/common
CMD ["python", "-m", "services.mqtt_bridge.app.main"]
