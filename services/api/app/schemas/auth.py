"""Auth Pydantic schemas — login, token, refresh."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserInfo(BaseModel):
    id: str
    username: str
    role: str
    email: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = ["read"]


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key: str
    key_prefix: str
    permissions: list[str]
    expires_at: str | None = None
    created_at: str


class ProfileResponse(BaseModel):
    id: str
    username: str
    email: str | None = None
    role: str
    is_active: bool
    last_login_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ProfileUpdate(BaseModel):
    email: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=100)
