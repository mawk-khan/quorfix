"""Attachment-storage writability check.

Shared by ReadinessCheckView (apps.core.views, polled repeatedly over HTTP)
and the `check_attachment_storage` management command (run once at
container startup, before the entrypoint execs the real process) — one
implementation, two callers, so the container-boot check and the ongoing
readiness check can never silently drift apart.
"""

import os
import uuid
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class StorageCheckResult:
    ok: bool
    detail: str


def check_attachment_storage_writable() -> StorageCheckResult:
    """Creates ATTACHMENTS_LOCAL_ROOT if it doesn't exist yet (and only that
    exact path — never anything else), then proves it's writable by writing
    and removing a small, uniquely-named probe file. Never touches any other
    path on disk."""
    root = settings.ATTACHMENTS_LOCAL_ROOT
    if not root:
        return StorageCheckResult(False, "ATTACHMENTS_LOCAL_ROOT is not configured")

    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:
        return StorageCheckResult(False, f"could not create attachment root: {exc.strerror or exc}")

    probe_path = os.path.join(root, f".writable-check-{uuid.uuid4().hex}")
    try:
        with open(probe_path, "wb") as probe_file:
            probe_file.write(b"ok")
        os.remove(probe_path)
    except OSError as exc:
        return StorageCheckResult(False, f"attachment root is not writable: {exc.strerror or exc}")

    return StorageCheckResult(True, "writable")
