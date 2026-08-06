"""Tests for apps.core.tar_safety — the path-traversal validation guarding
attachment-archive restore. Pure filesystem/tarfile tests: no database, no
Docker, no Django settings dependency."""

import io
import tarfile

import pytest

from apps.core.tar_safety import UnsafeTarMemberError, safe_extract_all, validate_archive


def _build_tar(path, members):
    """members: list of (name, kind, *extra).

    kind == "file": extra[0] is the file content (bytes), default b"data".
    kind == "dir": no extra.
    kind == "symlink": extra[0] is the link target.
    kind == "hardlink": extra[0] is the link target.
    kind == "device": a character-device special file.
    """
    with tarfile.open(path, "w:gz") as tar:
        for name, kind, *extra in members:
            info = tarfile.TarInfo(name=name)
            if kind == "file":
                content = extra[0] if extra else b"data"
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = extra[0]
                tar.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = extra[0]
                tar.addfile(info)
            elif kind == "device":
                info.type = tarfile.CHRTYPE
                tar.addfile(info)
            else:
                raise ValueError(f"unknown kind {kind!r}")
    return path


class TestValidateArchive:
    def test_valid_files_and_dirs_pass(self, tmp_path):
        archive = _build_tar(
            tmp_path / "archive.tar.gz",
            [("subdir", "dir"), ("subdir/file.txt", "file", b"hello")],
        )
        with tarfile.open(archive, "r:gz") as tar:
            members = validate_archive(tar)
        assert len(members) == 2

    def test_current_dir_prefix_allowed(self, tmp_path):
        """`tar czf archive.tar.gz -C /data/attachments .` (the format
        backup_attachments.sh produces) records entries like "./" and
        "./file.txt" — these must be accepted, not treated as unsafe."""
        archive = _build_tar(
            tmp_path / "archive.tar.gz",
            [(".", "dir"), ("./file.txt", "file", b"hello")],
        )
        with tarfile.open(archive, "r:gz") as tar:
            members = validate_archive(tar)
        assert len(members) == 2

    def test_empty_archive_is_valid(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [])
        with tarfile.open(archive, "r:gz") as tar:
            assert validate_archive(tar) == []

    def test_absolute_path_rejected(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [("/etc/passwd", "file", b"x")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="absolute path"):
                validate_archive(tar)

    def test_leading_dotdot_traversal_rejected(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [("../../etc/passwd", "file", b"x")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="escapes the extraction root"):
                validate_archive(tar)

    def test_embedded_dotdot_traversal_rejected(self, tmp_path):
        """A name that only escapes once normalized, e.g. "subdir/../../evil"."""
        archive = _build_tar(tmp_path / "archive.tar.gz", [("subdir/../../evil.txt", "file", b"x")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="escapes the extraction root"):
                validate_archive(tar)

    def test_bare_dotdot_rejected(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [("..", "dir")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="escapes the extraction root"):
                validate_archive(tar)

    def test_symlink_rejected(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [("evil-link", "symlink", "/etc/passwd")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="symlink"):
                validate_archive(tar)

    def test_hardlink_rejected(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [("evil-link", "hardlink", "some-file")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="symlink or hard link"):
                validate_archive(tar)

    def test_device_node_rejected(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [("evil-device", "device")])
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError, match="not a regular file or directory"):
                validate_archive(tar)

    def test_one_unsafe_member_among_many_safe_ones_still_rejected(self, tmp_path):
        archive = _build_tar(
            tmp_path / "archive.tar.gz",
            [
                ("safe-1.txt", "file", b"ok"),
                ("safe-2.txt", "file", b"ok"),
                ("../escape.txt", "file", b"bad"),
            ],
        )
        with tarfile.open(archive, "r:gz") as tar:
            with pytest.raises(UnsafeTarMemberError):
                validate_archive(tar)


class TestSafeExtractAll:
    def test_valid_archive_extracts_all_members(self, tmp_path):
        archive = _build_tar(
            tmp_path / "archive.tar.gz",
            [("subdir", "dir"), ("subdir/file.txt", "file", b"hello")],
        )
        destination = tmp_path / "out"
        count = safe_extract_all(str(archive), str(destination))
        assert count == 2
        assert (destination / "subdir" / "file.txt").read_bytes() == b"hello"

    def test_empty_archive_extracts_nothing_and_succeeds(self, tmp_path):
        archive = _build_tar(tmp_path / "archive.tar.gz", [])
        destination = tmp_path / "out"
        count = safe_extract_all(str(archive), str(destination))
        assert count == 0
        assert destination.is_dir()

    def test_unsafe_archive_extracts_nothing(self, tmp_path):
        """Validation happens in a first pass over every member before
        extraction starts — a malicious member must not let any earlier,
        individually-safe member be written to disk first."""
        archive = _build_tar(
            tmp_path / "archive.tar.gz",
            [("safe.txt", "file", b"ok"), ("../escape.txt", "file", b"bad")],
        )
        destination = tmp_path / "out"
        with pytest.raises(UnsafeTarMemberError):
            safe_extract_all(str(archive), str(destination))
        assert not (destination / "safe.txt").exists()

    def test_not_a_tar_file_raises_tar_error(self, tmp_path):
        not_a_tar = tmp_path / "not-a-tar.tar.gz"
        not_a_tar.write_bytes(b"this is not a gzip/tar file at all")
        with pytest.raises(tarfile.TarError):
            safe_extract_all(str(not_a_tar), str(tmp_path / "out"))
