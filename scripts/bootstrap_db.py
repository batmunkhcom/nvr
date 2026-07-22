#!/usr/bin/env python3
"""Bootstrap script — create all tables and seed admin user directly.

Uses SQLAlchemy ORM to create tables (handles enums correctly).
"""

import asyncio
import os

from passlib.context import CryptContext

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "nvr_user")
if not os.environ.get("POSTGRES_PASSWORD"):
    raise SystemExit("POSTGRES_PASSWORD env var is required (set it in .env)")
os.environ.setdefault("POSTGRES_DB", "nvr")

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import select
from app.models.base import Base
from app.models.user import User
from app.models.system_config import SystemConfig


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def main():
    url = (
        f"postgresql+asyncpg://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ['POSTGRES_DB']}"
    )

    engine = create_async_engine(url, echo=False)

    # 1. Enable extensions
    async with engine.connect() as conn:
        await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS timescaledb")
        await conn.commit()

    # 2. Create all tables via ORM (handles enums correctly)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 3. Seed default admin user
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        existing = result.scalar_one_or_none()

        if existing:
            print("Admin user already exists — skipping")
        else:
            admin = User(
                username="admin",
                email="admin@nvr.local",
                hashed_password=pwd_context.hash("admin"),
                role="admin",
                is_active=True,
            )
            session.add(admin)
            await session.flush()
            print("Admin user created (admin / admin)")

        # 4. Seed default system config
        defaults = {
            "system.name": "NVR System",
            "system.timezone": "UTC",
            "storage.default_path": "/data/recordings",
            "retention.default_days": "30",
            "recording.default_mode": "continuous",
            "ai.default_model": "yolov8n",
            "notifications.email_enabled": "false",
        }
        for key, value in defaults.items():
            result = await session.execute(select(SystemConfig).where(SystemConfig.key == key))
            if not result.scalar_one_or_none():
                session.add(SystemConfig(key=key, value=value))

        await session.commit()

    await engine.dispose()
    print("\nDatabase bootstrap complete.")
    print("Login: admin / admin")


if __name__ == "__main__":
    asyncio.run(main())
