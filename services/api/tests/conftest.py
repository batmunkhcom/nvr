"""Test configuration and shared fixtures for NVR API tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.main import app as _app
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def mock_db() -> AsyncMock:
    """Mock async database session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.scalars = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Async HTTP test client for FastAPI app."""
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def test_camera_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def test_recording_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def test_event_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def auth_headers() -> dict:
    """Fake auth headers for protected endpoints.

    In integration tests, you'd use a real JWT from login.
    Unit tests that mock auth middleware can use these.
    """
    return {"Authorization": "Bearer test-jwt-token"}
