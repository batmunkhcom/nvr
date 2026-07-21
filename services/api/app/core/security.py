"""Security — JWT token creation/verification, password hashing, encryption."""

import base64
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


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
