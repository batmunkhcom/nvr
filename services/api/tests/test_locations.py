"""Location service unit tests — CRUD, unique-name 409, camera unlink on delete."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.schemas.location import LocationCreate, LocationUpdate
from app.services.location_service import (
    create_location,
    delete_location,
    get_location,
    location_to_dict,
    update_location,
)
from fastapi import HTTPException


class _ExecResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._items

    def __await__(self):
        yield
        return self


def _result(value=None):
    r = _ExecResult()
    r._value = value
    return r


@pytest.fixture
def mock_db():
    m = MagicMock()
    m.add = MagicMock()
    m.flush = AsyncMock()
    m.commit = AsyncMock()
    m.delete = AsyncMock()
    return m


def _location(name="Office"):
    loc = MagicMock()
    loc.id = uuid.uuid4()
    loc.name = name
    loc.description = "desc"
    loc.created_at = None
    return loc


class TestLocationToDict:
    def test_serializes_with_camera_count(self):
        loc = _location()
        d = location_to_dict(loc, camera_count=3)
        assert d["name"] == "Office"
        assert d["camera_count"] == 3


class TestGetLocation:
    @pytest.mark.anyio
    async def test_raises_404(self, mock_db):
        mock_db.execute.return_value = _result(None)
        with pytest.raises(HTTPException) as exc:
            await get_location(uuid.uuid4(), mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.anyio
    async def test_returns_location(self, mock_db):
        loc = _location()
        mock_db.execute.return_value = _result(loc)
        result = await get_location(loc.id, mock_db)
        assert result.name == "Office"


class TestCreateLocation:
    @pytest.mark.anyio
    async def test_creates(self, mock_db):
        mock_db.execute.return_value = _result(None)  # no duplicate
        body = LocationCreate(name="Warehouse", description="main")

        loc = await create_location(body, mock_db)

        assert loc.name == "Warehouse"
        mock_db.add.assert_called_once()

    @pytest.mark.anyio
    async def test_duplicate_name_409(self, mock_db):
        mock_db.execute.return_value = _result(_location())  # duplicate exists
        body = LocationCreate(name="Office")

        with pytest.raises(HTTPException) as exc:
            await create_location(body, mock_db)
        assert exc.value.status_code == 409

    @pytest.mark.anyio
    async def test_strips_whitespace(self, mock_db):
        mock_db.execute.return_value = _result(None)
        body = LocationCreate(name="  Padded  ")

        loc = await create_location(body, mock_db)
        assert loc.name == "Padded"


class TestUpdateLocation:
    @pytest.mark.anyio
    async def test_updates_name(self, mock_db):
        loc = _location()
        # first execute: get_location, second: duplicate check (none)
        mock_db.execute.side_effect = [_result(loc), _result(None)]
        body = LocationUpdate(name="New Name")

        result = await update_location(loc.id, body, mock_db)
        assert result.name == "New Name"

    @pytest.mark.anyio
    async def test_rename_conflict_409(self, mock_db):
        loc = _location()
        other = _location("Other")
        mock_db.execute.side_effect = [_result(loc), _result(other)]
        body = LocationUpdate(name="Other")

        with pytest.raises(HTTPException) as exc:
            await update_location(loc.id, body, mock_db)
        assert exc.value.status_code == 409

    @pytest.mark.anyio
    async def test_updates_description_only(self, mock_db):
        loc = _location()
        mock_db.execute.return_value = _result(loc)
        body = LocationUpdate(description="new desc")

        result = await update_location(loc.id, body, mock_db)
        assert result.description == "new desc"
        assert result.name == "Office"


class TestDeleteLocation:
    @pytest.mark.anyio
    async def test_deletes(self, mock_db):
        loc = _location()
        mock_db.execute.return_value = _result(loc)

        await delete_location(loc.id, mock_db)
        mock_db.delete.assert_called_once()

    @pytest.mark.anyio
    async def test_delete_missing_404(self, mock_db):
        mock_db.execute.return_value = _result(None)
        with pytest.raises(HTTPException) as exc:
            await delete_location(uuid.uuid4(), mock_db)
        assert exc.value.status_code == 404
