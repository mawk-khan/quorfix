"""Malware-scanning extension point.

Community ships no scanner and never registers one — apps.attachments.
services checks apps.core.registries.capability_registry for the
"malware_scanning" key and no-ops when it's absent (per that registry's own
"unregistered key = capability not available" contract; pre-registering a
Community no-op here would only block a real Professional scanner from ever
registering, since Registry.register() raises on a duplicate key). A
Professional module that wants real scanning registers a MalwareScanner here,
typically from its AppConfig.ready().

This is local-storage-shaped on purpose (a real file path, not a storage key)
— that's the only thing this chunk has a scanner for. A future S3-compatible
provider will need its own way to hand a scanner something inspectable
(likely a downloaded temp copy or a streaming read), decided when that
provider actually exists.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Protocol


class MalwareScanResult(str, Enum):
    CLEAN = "clean"
    INFECTED = "infected"


class MalwareScanner(Protocol):
    def scan(self, *, file_path: Path, content_type: str, size_bytes: int) -> MalwareScanResult: ...
