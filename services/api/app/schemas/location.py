"""Location Pydantic schemas."""

from pydantic import BaseModel, Field


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    color: str = "#3b82f6"


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    color: str | None = None


class LocationResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    color: str = "#3b82f6"
    camera_count: int = 0
    created_at: str
