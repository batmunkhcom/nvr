"""Unit tests for storage backends (LocalStorage)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from nvr_common.storage import LocalStorage


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def local_storage(temp_dir):
    return LocalStorage(
        backend_id="test-local",
        name="Test Local",
        config={"path": temp_dir},
    )


class TestLocalStorageInit:
    def test_creates_root_directory(self, temp_dir):
        root = Path(temp_dir) / "sub" / "recordings"
        LocalStorage("test", "Test", {"path": str(root)})
        assert root.exists()

    def test_defaults_path(self):
        storage = LocalStorage("test", "Test", {})
        assert storage.root == Path("/data/recordings")

    def test_stores_config(self, local_storage):
        assert local_storage.name == "Test Local"
        assert local_storage.backend_id == "test-local"


class TestLocalStorageHealth:
    @pytest.mark.anyio
    async def test_reports_status_and_latency(self, local_storage):
        result = await local_storage.health_check()
        assert result["status"] == "healthy"
        assert "latency_ms" in result


class TestLocalStorageSpace:
    @pytest.mark.anyio
    async def test_total_bytes_positive(self, local_storage):
        total = await local_storage.total_bytes()
        assert total > 0

    @pytest.mark.anyio
    async def test_available_bytes_positive(self, local_storage):
        avail = await local_storage.available_bytes()
        assert avail > 0


class TestLocalStorageIO:
    @pytest.mark.anyio
    async def test_write_and_read(self, local_storage):
        path = "test_write.txt"
        data = b"Hello NVR Storage"

        async def source():
            yield data

        bytes_written = await local_storage.write_stream(path, source())
        assert bytes_written == len(data)

        chunks = []
        async for chunk in local_storage.read_stream(path):
            chunks.append(chunk)

        assert b"".join(chunks) == data

    @pytest.mark.anyio
    async def test_list_files(self, local_storage):
        for idx in range(3):

            def _make_source(n):
                async def source():
                    yield f"data_{n}".encode()

                return source

            await local_storage.write_stream(f"ls_{idx}.txt", _make_source(idx)())

        files = await local_storage.list_files("")
        matching = [f for f in files if "ls_" in f]
        assert len(matching) == 3

    @pytest.mark.anyio
    async def test_delete_removes_file(self, local_storage):
        async def source():
            yield b"test"

        await local_storage.write_stream("to_delete.txt", source())

        await local_storage.delete("to_delete.txt")

        with pytest.raises(FileNotFoundError):
            async for _ in local_storage.read_stream("to_delete.txt"):
                pass

    @pytest.mark.anyio
    async def test_delete_nonexistent_noop(self, local_storage):
        try:
            await local_storage.delete("does_not_exist")
        except Exception:
            pytest.fail("delete(nonexistent) should not raise")


class TestLocalStorageCopy:
    @pytest.mark.anyio
    async def test_copy_to_another_backend(self, local_storage, temp_dir):
        path = "verify_test.bin"
        data = b"A" * 10000

        async def source():
            yield data

        await local_storage.write_stream(path, source())

        dest = LocalStorage("dest", "Dest", {"path": str(Path(temp_dir) / "dest")})
        await local_storage.copy_to(path, dest, "copied.bin")

        chunks = []
        async for chunk in dest.read_stream("copied.bin"):
            chunks.append(chunk)
        assert b"".join(chunks) == data


class TestLocalStorageChecksum:
    @pytest.mark.anyio
    async def test_checksum_sha256(self, local_storage):
        path = "checksum_test.bin"
        data = b"Hello Checksum World"

        async def source():
            yield data

        await local_storage.write_stream(path, source())
        result = await local_storage.checksum(path)
        assert len(result) == 64


class TestLocalStorageEdgeCases:
    @pytest.mark.anyio
    async def test_read_nonexistent_raises(self, local_storage):
        with pytest.raises(FileNotFoundError):
            async for _ in local_storage.read_stream("nonexistent"):
                pass

    @pytest.mark.anyio
    async def test_free_percent(self, local_storage):
        pct = await local_storage.free_percent()
        assert 0 <= pct <= 100

    @pytest.mark.anyio
    async def test_path_traversal_prevented(self, local_storage):
        with pytest.raises(ValueError, match="traversal"):
            local_storage._resolve("../outside")
