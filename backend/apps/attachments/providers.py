"""Storage provider interface for attachments.

Only a local filesystem provider exists so far. The Protocol below is
deliberately narrow — save_stream/resolve_download/head/delete, exactly what
the local implementation and its callers in apps.attachments.services actually
use today. It intentionally does NOT include presigned-URL or bucket-shaped
methods (generate_presigned_post, generate_presigned_url, endpoint_url,
bucket config): those are S3-flavored concepts that belong on a future
S3-compatible provider when one is actually built, not speculative surface
area on this one. get_storage_provider() is the single seam that provider
will plug into.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)


class StorageProvider(Protocol):
    def save_stream(self, key: str, chunks: Iterable[bytes]) -> None: ...

    def resolve_download(self, key: str) -> Path | None: ...

    def head(self, key: str) -> int | None:
        """Returns the stored object's size in bytes, or None if it doesn't
        exist."""
        ...

    def delete(self, key: str) -> None:
        """Idempotent — deleting an already-absent key is not an error."""
        ...


class LocalStorageProvider:
    def __init__(self, root: str | Path | None = None):
        self._root = Path(root or settings.ATTACHMENTS_LOCAL_ROOT).resolve()

    def _path_for(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            # Defense in depth only — storage_key is always server-generated
            # from UUIDs plus a controlled extension lookup (see
            # apps.attachments.services._build_storage_key), so a key that
            # escapes the root should never actually occur.
            raise ValueError(f"storage key resolves outside the storage root: {key!r}")
        return candidate

    def save_stream(self, key: str, chunks: Iterable[bytes]) -> None:
        """Writes to a temp file in the destination directory, then
        atomically renames into place — a failure partway through never
        leaves a partial file at the real path, since `final_path` is never
        touched until the write has fully succeeded."""
        final_path = self._path_for(key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = final_path.with_name(final_path.name + ".part")
        try:
            with open(tmp_path, "wb") as dest:
                for chunk in chunks:
                    dest.write(chunk)
            os.replace(tmp_path, final_path)  # atomic within the same filesystem
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def resolve_download(self, key: str) -> Path | None:
        path = self._path_for(key)
        return path if path.is_file() else None

    def head(self, key: str) -> int | None:
        path = self._path_for(key)
        if not path.is_file():
            return None
        return path.stat().st_size

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)


def get_storage_provider() -> StorageProvider:
    return LocalStorageProvider()
