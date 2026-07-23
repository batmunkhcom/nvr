"""Application configuration loaded from environment variables (Pydantic Settings)."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_file": os.environ.get(
            "NVR_ENV_FILE", os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env")
        ),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # Application
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_reload: bool = False
    api_log_level: str = "info"
    api_cors_origins: str = "*"

    # Database
    postgres_host: str = "nvr-db"
    postgres_port: int = 5432
    postgres_db: str = "nvr"
    postgres_user: str = "nvr_user"
    postgres_password: str = ""  # REQUIRED via POSTGRES_PASSWORD env var
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 10

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_host: str = "nvr-redis"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # JWT
    jwt_secret_key: str = "dev_secret_change_me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 1440

    # Encryption
    nvr_encryption_key: str = ""

    # Storage
    storage_local_path: str = "/data/recordings"
    s3_endpoint: str = "nvr-minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin_change_me"
    s3_bucket: str = "nvr-recordings"
    s3_secure: bool = False

    # Discovery
    discovery_subnets: str = "192.168.1.0/24,192.168.2.0/24"
    vendor_patterns_path: str = "/app/config/vendor_patterns.yml"

    # AI
    ai_model_path: str = "/app/models"
    ai_yolo_model: str = "yolov8n.onnx"
    ai_confidence_threshold: float = 0.5
    ai_device: str = "cpu"


settings = Settings()
