"""Shared AES-256-GCM password encryption helpers.

Used by recording-engine and ai-engine to decrypt camera passwords.
Reads NVR_ENCRYPTION_KEY from the environment (base64-encoded 32-byte key).
Format: base64(nonce[12] + ciphertext) — same as api app.core.security.
"""

from __future__ import annotations

import base64
import os


def _get_key() -> bytes:
    key_b64 = os.environ.get("NVR_ENCRYPTION_KEY", "")
    if not key_b64:
        raise ValueError("NVR_ENCRYPTION_KEY is not set")
    return base64.b64decode(key_b64)


def decrypt_password_aes(ciphertext: str) -> str:
    """Decrypt a camera password encrypted with encrypt_password_aes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    cipher = AESGCM(_get_key())
    return cipher.decrypt(nonce, ct, None).decode()


def encrypt_password_aes(plaintext: str) -> str:
    """Encrypt a plaintext password (for tooling/tests)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    cipher = AESGCM(_get_key())
    ct = cipher.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()
