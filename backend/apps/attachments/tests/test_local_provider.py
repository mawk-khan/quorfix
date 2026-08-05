import pytest

from apps.attachments.providers import LocalStorageProvider


@pytest.fixture
def provider(tmp_path):
    return LocalStorageProvider(root=tmp_path / "storage-root")


class TestSaveAndResolve:
    def test_save_then_resolve_download(self, provider):
        provider.save_stream("attachments/org/bug/file.txt", [b"hello ", b"world"])
        path = provider.resolve_download("attachments/org/bug/file.txt")
        assert path is not None
        assert path.read_bytes() == b"hello world"

    def test_resolve_missing_key_returns_none(self, provider):
        assert provider.resolve_download("attachments/does/not/exist.txt") is None

    def test_creates_intermediate_directories(self, provider):
        provider.save_stream("attachments/deep/nested/path/file.txt", [b"x"])
        path = provider.resolve_download("attachments/deep/nested/path/file.txt")
        assert path is not None

    def test_no_leftover_part_file_on_success(self, provider, tmp_path):
        provider.save_stream("attachments/org/bug/file.txt", [b"data"])
        leftovers = list((tmp_path / "storage-root").rglob("*.part"))
        assert leftovers == []


class TestSaveFailureLeavesNoPartialFile:
    def test_failure_partway_leaves_no_file_at_final_path(self, provider):
        class _BoomIterable:
            def __iter__(self):
                yield b"first chunk written fine"
                raise OSError("simulated disk failure")

        with pytest.raises(OSError):
            provider.save_stream("attachments/org/bug/broken.txt", _BoomIterable())

        assert provider.resolve_download("attachments/org/bug/broken.txt") is None

    def test_failure_partway_removes_the_temp_file_too(self, provider, tmp_path):
        class _BoomIterable:
            def __iter__(self):
                yield b"partial"
                raise OSError("simulated disk failure")

        with pytest.raises(OSError):
            provider.save_stream("attachments/org/bug/broken.txt", _BoomIterable())

        leftovers = list((tmp_path / "storage-root").rglob("*.part"))
        assert leftovers == []


class TestHead:
    def test_head_returns_size(self, provider):
        provider.save_stream("attachments/org/bug/file.txt", [b"12345"])
        assert provider.head("attachments/org/bug/file.txt") == 5

    def test_head_missing_returns_none(self, provider):
        assert provider.head("attachments/does/not/exist.txt") is None


class TestDelete:
    def test_delete_removes_file(self, provider):
        provider.save_stream("attachments/org/bug/file.txt", [b"data"])
        provider.delete("attachments/org/bug/file.txt")
        assert provider.resolve_download("attachments/org/bug/file.txt") is None

    def test_delete_is_idempotent(self, provider):
        provider.delete("attachments/never/existed.txt")  # must not raise
        provider.delete("attachments/never/existed.txt")  # calling twice is still fine


class TestPathTraversalDefense:
    def test_key_escaping_root_is_rejected(self, provider):
        with pytest.raises(ValueError):
            provider._path_for("../../../etc/passwd")

    def test_absolute_path_key_is_rejected(self, provider):
        with pytest.raises(ValueError):
            provider._path_for("/etc/passwd")
