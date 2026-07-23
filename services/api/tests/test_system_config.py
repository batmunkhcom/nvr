"""System config tests — ui-config get/patch roundtrip, key-prefix guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.api.v1.system import UiConfigUpdate, update_ui_config
from fastapi import HTTPException


class _ExecResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def __await__(self):
        yield
        return self


@pytest.fixture
def mock_db():
    m = MagicMock()
    m.add = MagicMock()
    m.flush = AsyncMock()
    return m


class TestUiConfigUpdate:
    @pytest.mark.anyio
    async def test_creates_new_key(self, mock_db):
        mock_db.execute.return_value = _ExecResult(None)
        body = UiConfigUpdate(key="ui.dashboard_columns", value=3)

        result = await update_ui_config(body, {}, mock_db)

        assert result["data"]["value"] == 3
        mock_db.add.assert_called_once()

    @pytest.mark.anyio
    async def test_updates_existing_key(self, mock_db):
        existing = MagicMock()
        existing.key = "ui.sidebar_collapsed"
        existing.value = False
        mock_db.execute.return_value = _ExecResult(existing)
        body = UiConfigUpdate(key="ui.sidebar_collapsed", value=True)

        result = await update_ui_config(body, {}, mock_db)

        assert existing.value is True
        assert result["data"]["value"] is True
        mock_db.add.assert_not_called()

    @pytest.mark.anyio
    async def test_rejects_non_ui_key(self, mock_db):
        body = UiConfigUpdate(key="mediamtx.rtsp_url", value="rtsp://x")

        with pytest.raises(HTTPException) as exc:
            await update_ui_config(body, {}, mock_db)
        assert exc.value.status_code == 400

    @pytest.mark.anyio
    async def test_roundtrip_preserves_types(self, mock_db):
        """Values round-trip as JSON types: int, bool, str."""
        mock_db.execute.return_value = _ExecResult(None)
        for value in (2, True, "dark"):
            body = UiConfigUpdate(key="ui.test", value=value)
            result = await update_ui_config(body, {}, mock_db)
            assert result["data"]["value"] == value
            assert type(result["data"]["value"]) is type(value)
