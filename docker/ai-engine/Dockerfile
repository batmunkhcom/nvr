FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir "redis>=5.2" "httpx>=0.28" \
    "structlog>=24.4" "pyyaml>=6.0" "aiohttp>=3.11" \
    "tenacity>=9.0" "pydantic>=2.10" \
    "onnxruntime>=1.20" "opencv-python-headless>=4.10" \
    "numpy>=2.2" "ultralytics>=8.3" "scikit-learn>=1.6"

RUN mkdir -p /app/models
COPY services/ai-engine/ ./services/ai-engine/
COPY packages/ ./packages/

CMD ["python", "-m", "services.ai_engine.app.main"]
