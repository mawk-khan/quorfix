"""Safety validation for tar archives extracted during attachment restore.

A backup archive is untrusted input by the time it reaches restore — it may
have been copied across hosts, sat on removable media, or (in the failure
case this module defends against) been tampered with. Without validation, a
crafted member name (an absolute path, a `..` traversal, a symlink pointing
outside the extraction root) could let `tarfile.extractall` write files
anywhere the restoring process has permission to write, not just under the
intended attachments root.

Every member is validated in a first pass, before any extraction happens —
one unsafe member aborts the whole restore with nothing written to disk,
rather than extracting some files before hitting a bad one partway through.
"""

from __future__ import annotations

import os
import tarfile

_SAFE_TYPES = (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE)


class UnsafeTarMemberError(ValueError):
    """Raised when a tar archive contains a member that is unsafe to extract."""


def _is_within_root(name: str) -> bool:
    # A purely lexical check on the member's *name* as recorded in the
    # archive — deliberately does not resolve symlinks or touch the
    # filesystem, since nothing has been extracted yet at validation time.
    normalized = os.path.normpath(name)
    if normalized in (".", ""):
        return True
    if normalized == ".." or normalized.startswith(f"..{os.sep}"):
        return False
    if os.path.isabs(normalized):
        return False
    return True


def validate_member(member: tarfile.TarInfo) -> None:
    """Raises UnsafeTarMemberError if `member` is not safe to extract under
    the intended attachments root."""
    name = member.name
    if name is None or name.strip() == "":
        raise UnsafeTarMemberError("archive contains a member with an empty name")
    if os.path.isabs(name):
        raise UnsafeTarMemberError(f"archive member {name!r} is an absolute path")
    if not _is_within_root(name):
        raise UnsafeTarMemberError(f"archive member {name!r} escapes the extraction root")
    if member.issym() or member.islnk():
        # A plain filesystem tar of the attachments root (see
        # scripts/backup_attachments.sh) never legitimately contains a
        # symlink or hard link — reject rather than silently follow a link
        # that could point outside the extraction root, or silently drop it.
        raise UnsafeTarMemberError(
            f"archive member {name!r} is a symlink or hard link, which is not allowed"
        )
    if member.type not in _SAFE_TYPES:
        raise UnsafeTarMemberError(
            f"archive member {name!r} is not a regular file or directory (tar type {member.type!r})"
        )


def validate_archive(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Validates every member of an already-open tar file. Returns the
    member list on success. Raises UnsafeTarMemberError on the first unsafe
    member found — the caller must not extract anything from `tar` after
    this raises, and nothing is extracted by this function itself."""
    members = tar.getmembers()
    for member in members:
        validate_member(member)
    return members


def safe_extract_all(archive_path: str, destination: str) -> int:
    """Validates then extracts every member of the tar archive at
    `archive_path` into `destination`. Returns the number of members
    extracted. Raises UnsafeTarMemberError, leaving `destination` untouched,
    if any member fails validation; raises tarfile.TarError if the file is
    not a valid tar archive at all.

    Passes filter="data" (Python 3.12+, PEP 706) to extractall as a second,
    independent layer of defense on top of the explicit validation above."""
    os.makedirs(destination, exist_ok=True)
    with tarfile.open(archive_path, "r:*") as tar:
        members = validate_archive(tar)
        tar.extractall(destination, members=members, filter="data")
    return len(members)
