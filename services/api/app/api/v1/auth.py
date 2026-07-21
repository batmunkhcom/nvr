"""Auth endpoints — login, refresh, logout, API keys."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    verify_password,
)
from ...middleware.auth import get_current_user, require_admin
from ...models.api_key import ApiKey
from ...models.user import User
from ...schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")

    access_token = create_access_token(user.id, user.username, user.role)
    refresh_token = create_refresh_token(user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=86400,
        user={
            "id": str(user.id),
            "username": user.username,
            "role": user.role,
            "email": user.email,
        },
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        payload = decode_token(body.refresh_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from e
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled"
        )

    access_token = create_access_token(user.id, user.username, user.role)
    new_refresh = create_refresh_token(user.id)
    return RefreshResponse(access_token=access_token, refresh_token=new_refresh, expires_in=86400)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest):
    pass


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreateRequest,
    current_user: Annotated[dict, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    raw_key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        user_id=uuid.UUID(current_user["sub"]),
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        permissions=body.permissions,
    )
    db.add(api_key)
    await db.flush()
    return ApiKeyResponse(
        id=str(api_key.id),
        name=api_key.name,
        key=raw_key,
        key_prefix=key_prefix,
        permissions=api_key.permissions,
        created_at=api_key.created_at.isoformat() if api_key.created_at else "",
    )


@router.get("/api-keys")
async def list_api_keys(
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == uuid.UUID(current_user["sub"]))
    )
    keys = result.scalars().all()
    return {
        "data": [
            {
                "id": str(k.id),
                "name": k.name,
                "key_prefix": k.key_prefix,
                "permissions": k.permissions,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else "",
            }
            for k in keys
        ]
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: uuid.UUID,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == uuid.UUID(current_user["sub"]))
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.delete(key)
