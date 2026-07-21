"""User Pydantic schemas."""

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6)
    role: str = Field(default="viewer", pattern="^(admin|operator|viewer)$")
    email: str | None = None


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=6)
    role: str | None = Field(default=None, pattern="^(admin|operator|viewer)$")
    is_active: bool | None = None
    email: str | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    email: str | None = None
    is_active: bool
    last_login_at: str | None = None
    created_at: str
    updated_at: str
