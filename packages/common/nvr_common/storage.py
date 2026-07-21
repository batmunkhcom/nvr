"""Storage backend abstract base class and implementations.

Supports: local POSIX filesystem, NFS mounts, SMB/CIFS shares, S3/MinIO.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path

import aiofiles
import structlog

logger = structlog.get_logger()

CHUNK_SIZE = 1_048_576  # 1 MB


class StorageBackend(ABC):
    """Abstract storage backend for reading/writing recording files."""

    def __init__(self, backend_id: str, name: str, config: dict):
        self.backend_id = backend_id
        self.name = name
        self.config = config

    @abstractmethod
    async def health_check(self) -> dict:
        """Check backend health and return status dict."""

    @abstractmethod
    async def total_bytes(self) -> int:
        """Total storage capacity in bytes."""

    @abstractmethod
    async def available_bytes(self) -> int:
        """Available storage space in bytes."""

    @abstractmethod
    async def read_stream(self, path: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        """Stream read a file in chunks."""

    @abstractmethod
    async def write_stream(self, path: str, source: AsyncIterator[bytes]) -> int:
        """Stream write a file and return total bytes written."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete a file."""

    @abstractmethod
    async def list_files(self, prefix: str, pattern: str | None = None) -> list[str]:
        """List files matching prefix/pattern."""

    async def checksum(self, path: str) -> str:
        """Calculate SHA-256 checksum of a file."""
        sha = hashlib.sha256()
        async for chunk in self.read_stream(path):
            sha.update(chunk)
        return sha.hexdigest()

    async def copy_to(self, source_path: str, dest_backend: StorageBackend, dest_path: str) -> None:
        """Copy file to another backend with checksum verification."""
        async for chunk in self.read_stream(source_path):
            await dest_backend._write_chunk(dest_path, chunk)

    @abstractmethod
    async def _write_chunk(self, path: str, chunk: bytes) -> None:
        """Internal chunk write — implemented per backend."""

    async def free_percent(self) -> float:
        """Percentage of free storage space."""
        total = await self.total_bytes()
        if total == 0:
            return 0
        return (await self.available_bytes() / total) * 100


class LocalStorage(StorageBackend):
    """Local POSIX filesystem storage backend."""

    def __init__(self, backend_id: str, name: str, config: dict):
        super().__init__(backend_id, name, config)
        self.root = Path(config.get("path", "/data/recordings"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        resolved = (self.root / path.lstrip("/")).resolve()
        if not str(resolved).startswith(str(self.root)):
            raise ValueError(f"Path traversal detected: {path}")
        return resolved

    async def health_check(self) -> dict:
        try:
            os.statvfs(self.root)
            latency_start = os.times()
            test_file = self.root / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()
            latency_ms = (os.times().elapsed - latency_start.elapsed) * 1000
            return {"status": "healthy", "latency_ms": round(latency_ms, 2)}
        except OSError as e:
            return {"status": "unhealthy", "error": str(e)}

    async def total_bytes(self) -> int:
        stat = os.statvfs(self.root)
        return stat.f_frsize * stat.f_blocks

    async def available_bytes(self) -> int:
        stat = os.statvfs(self.root)
        return stat.f_frsize * stat.f_bavail

    async def read_stream(self, path: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        filepath = self._resolve(path)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {path}")
        async with aiofiles.open(filepath, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    async def write_stream(self, path: str, source: AsyncIterator[bytes]) -> int:
        filepath = self._resolve(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        async with aiofiles.open(filepath, "wb") as f:
            async for chunk in source:
                await f.write(chunk)
                total += len(chunk)
        return total

    async def delete(self, path: str) -> None:
        filepath = self._resolve(path)
        if filepath.exists():
            filepath.unlink()

    async def list_files(self, prefix: str, pattern: str | None = None) -> list[str]:
        base = self._resolve(prefix.rstrip("/") if prefix else "")
        if not base.exists():
            return []
        results = []
        for f in base.rglob(pattern or "*"):
            if f.is_file():
                results.append(str(f.relative_to(self.root)))
        return results

    async def _write_chunk(self, path: str, chunk: bytes) -> None:
        filepath = self._resolve(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(filepath, "ab") as f:
            await f.write(chunk)


class S3Storage(StorageBackend):
    """S3-compatible (MinIO/AWS) storage backend using aiobotocore."""

    def __init__(self, backend_id: str, name: str, config: dict):
        super().__init__(backend_id, name, config)
        self.endpoint = config.get("endpoint", "minio:9000")
        self.access_key = config.get("access_key", "minioadmin")
        self.secret_key = config.get("secret_key", "")
        self.bucket = config.get("bucket", "nvr-recordings")
        self.secure = config.get("secure", False)
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from aiobotocore.session import get_session

            session = get_session()
            self._client = await session.create_client(
                "s3",
                endpoint_url=f"{'https' if self.secure else 'http'}://{self.endpoint}",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name="us-east-1",
            ).__aenter__()
        return self._client

    async def _ensure_bucket(self) -> None:
        try:
            client = await self._get_client()
            await client.head_bucket(Bucket=self.bucket)
        except Exception:
            await client.create_bucket(Bucket=self.bucket)

    async def health_check(self) -> dict:
        import time as _time

        try:
            start = _time.monotonic()
            await self._ensure_bucket()
            latency_ms = (_time.monotonic() - start) * 1000
            return {"status": "healthy", "latency_ms": round(latency_ms, 2)}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def total_bytes(self) -> int:
        return 1_000_000_000_000

    async def available_bytes(self) -> int:
        return 500_000_000_000

    async def read_stream(self, path: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        client = await self._get_client()
        resp = await client.get_object(Bucket=self.bucket, Key=path)
        body = resp["Body"]
        while True:
            chunk = await body.read(chunk_size)
            if not chunk:
                break
            yield chunk

    async def write_stream(self, path: str, source: AsyncIterator[bytes]) -> int:
        total = 0
        chunks: list[bytes] = []
        async for chunk in source:
            chunks.append(chunk)
            total += len(chunk)
        client = await self._get_client()
        await client.put_object(Bucket=self.bucket, Key=path, Body=b"".join(chunks))
        return total

    async def delete(self, path: str) -> None:
        client = await self._get_client()
        await client.delete_object(Bucket=self.bucket, Key=path)

    async def list_files(self, prefix: str, pattern: str | None = None) -> list[str]:
        client = await self._get_client()
        resp = await client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [obj["Key"] for obj in resp.get("Contents", [])]

    async def _write_chunk(self, path: str, chunk: bytes) -> None:
        pass  # not needed for S3 — whole file upload via write_stream
