"""Seed initial system configuration from YAML to database."""

import asyncio
import os
import sys

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "default.yml"
)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+asyncpg://{os.getenv('POSTGRES_USER', 'nvr_user')}:{os.getenv('POSTGRES_PASSWORD', 'nvr')}@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'nvr')}",
)


async def seed_config(config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """Read default.yml and insert all values into system_config table."""
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        # Ensure system_config table exists
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS system_config (
                key VARCHAR(255) PRIMARY KEY,
                value JSONB NOT NULL DEFAULT '{}',
                description TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))

        def _flatten(data: dict, prefix: str = "") -> list[tuple[str, dict, str]]:
            """Flatten nested dict into key-value pairs."""
            entries = []
            for k, v in data.items():
                full_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    entries.extend(_flatten(v, full_key))
                elif isinstance(v, list):
                    entries.append((full_key, v, f"Config: {full_key}"))
                else:
                    entries.append((full_key, {"value": v}, f"Config: {full_key}"))
            return entries

        entries = _flatten(config_data)

        for key, value, desc in entries:
            await conn.execute(
                text("""
                    INSERT INTO system_config (key, value, description, updated_at)
                    VALUES (:key, :value::jsonb, :description, NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        description = EXCLUDED.description,
                        updated_at = NOW()
                """),
                {"key": key, "value": str(value).replace("'", '"'), "description": desc},
            )

        print(f"Seeded {len(entries)} configuration entries from {config_path}")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    asyncio.run(seed_config(config_path))
