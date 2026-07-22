"""Security — JWT token creation/verification, password hashing, encryption."""

import base64
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import jwt

from .config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(user_id: uuid.UUID, username: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": datetime.now(UTC),
        "exp": expire,
        "jti": secrets.token_hex(16),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(days=7)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "jti": secrets.token_hex(16),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def encrypt_password_aes(plaintext: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(settings.nvr_encryption_key)
    nonce = os.urandom(12)
    cipher = AESGCM(key)
    ct = cipher.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_password_aes(ciphertext: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    key = base64.b64decode(settings.nvr_encryption_key)
    cipher = AESGCM(key)
    return cipher.decrypt(nonce, ct, None).decode()


def generate_api_key() -> tuple[str, str, str]:
    raw = f"nvr_{secrets.token_hex(24)}"
    key_hash = hash_password(raw)
    key_prefix = raw[:12]
    return raw, key_hash, key_prefix
