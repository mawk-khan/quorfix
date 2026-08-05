"""Format validation for attachment uploads.

Two independent checks feed off the same allow-list: `content_type` must be
one of a fixed set of MIME types (no SVG — inline SVG can carry script, a
stored-XSS vector), and the *actual bytes* are checked against that declared
type wherever a reliable signature exists. Both are format validation, not
malware scanning — a byte-signature-correct file can still be malicious; see
apps.attachments.scanning for the real content-inspection extension point.
"""

from __future__ import annotations

import json
import re
import zipfile

MAX_FILENAME_LENGTH = 255
SIGNATURE_HEAD_SIZE = 32
TEXT_SNIFF_SIZE = 8192

# Single source of truth for both "is this type allowed" and "what extension
# does the server-generated storage key get" — the extension is always looked
# up from here, from the *validated* content_type, never parsed out of the
# client's filename (see apps.attachments.services._build_storage_key).
CONTENT_TYPE_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/zip": ".zip",
    "video/mp4": ".mp4",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}
ALLOWED_CONTENT_TYPES = frozenset(CONTENT_TYPE_EXTENSIONS)


class UnsupportedContentType(Exception):
    pass


class AttachmentTooLarge(Exception):
    pass


def validate_content_type(content_type: str) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedContentType()


def validate_size(size_bytes: int, *, max_size_bytes: int) -> None:
    if size_bytes <= 0 or size_bytes > max_size_bytes:
        raise AttachmentTooLarge()


def extension_for_content_type(content_type: str) -> str:
    """Callers must validate_content_type() first — this assumes membership."""
    return CONTENT_TYPE_EXTENSIONS[content_type]


_UNSAFE_FILENAME_CHARS_RE = re.compile(r'[\x00-\x1f\x7f\\/:*?"<>|]')


def sanitize_filename(raw: str) -> str:
    """Display metadata only — this value never influences the storage path
    (see apps.attachments.services._build_storage_key). Strips any path
    component the client might have sent (handles both `/` and `\\`
    separators, since a client could send Windows-style separators against a
    POSIX server), strips control/reserved characters, and falls back to a
    generic name if nothing usable remains."""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = _UNSAFE_FILENAME_CHARS_RE.sub("_", name).strip(" .")
    name = name[:MAX_FILENAME_LENGTH]
    return name or "attachment"


def _has_prefix(head: bytes, *prefixes: bytes) -> bool:
    return any(head.startswith(prefix) for prefix in prefixes)


def _check_png(head: bytes) -> bool:
    return head.startswith(b"\x89PNG\r\n\x1a\n")


def _check_jpeg(head: bytes) -> bool:
    return head.startswith(b"\xff\xd8\xff")


def _check_gif(head: bytes) -> bool:
    return _has_prefix(head, b"GIF87a", b"GIF89a")


def _check_webp(head: bytes) -> bool:
    return head.startswith(b"RIFF") and head[8:12] == b"WEBP"


def _check_pdf(head: bytes) -> bool:
    return head.startswith(b"%PDF-")


def _check_zip(head: bytes) -> bool:
    # PK\x03\x04 is a normal entry; PK\x05\x06 is a valid (empty) archive.
    return _has_prefix(head, b"PK\x03\x04", b"PK\x05\x06")


# DOCX/XLSX are ZIP containers, but a magic-byte check alone can't tell one
# apart from a plain .zip (or from each other) — that needs actually looking
# at what's inside. Every OOXML package (ECMA-376 / OPC) has
# "[Content_Types].xml" at the root; DOCX-specific parts live under "word/",
# XLSX-specific parts under "xl/". A renamed/relabeled plain ZIP has neither,
# and a DOCX relabeled as XLSX has the wrong prefix — both are rejected here,
# not just accepted on the strength of the outer ZIP signature.
_OOXML_REQUIRED_MEMBER_PREFIX = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xl/",
}


def _check_ooxml_members(uploaded_file, required_prefix: str) -> bool:
    """Opens the ZIP central directory (a small, fast read regardless of the
    archive's total size — it does not decompress or scan file contents) and
    confirms the expected OOXML package members are present. Always leaves
    `uploaded_file`'s position at 0 for the caller."""
    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return False
    finally:
        uploaded_file.seek(0)

    if "[Content_Types].xml" not in names:
        return False
    return any(name.startswith(required_prefix) for name in names)


def _check_ole(head: bytes) -> bool:
    # Legacy .doc/.xls (OLE Compound File Binary Format).
    return head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")


def _check_mp4(head: bytes) -> bool:
    # ISO BMFF: a 4-byte box size followed by the literal box type "ftyp".
    return len(head) >= 8 and head[4:8] == b"ftyp"


# Head-prefix-only checks — application/zip is deliberately here with no
# member requirement at all (a ZIP is a ZIP regardless of what's inside);
# the two OOXML types are handled separately below, not through this table.
_SIGNATURE_CHECKS = {
    "image/png": _check_png,
    "image/jpeg": _check_jpeg,
    "image/gif": _check_gif,
    "image/webp": _check_webp,
    "application/pdf": _check_pdf,
    "application/zip": _check_zip,
    "application/msword": _check_ole,
    "application/vnd.ms-excel": _check_ole,
    "video/mp4": _check_mp4,
}


def verify_uploaded_content(content_type: str, uploaded_file) -> bool:
    """Checks the actual bytes against what `content_type` claims. Always
    seeks back to the start before returning, so the caller can still stream
    the full file afterward regardless of the outcome.

    JSON is the one type that needs the *whole* document (syntax can't be
    judged from a byte prefix) — bounded by the size limit already enforced
    before this ever runs, so worst case this reads 10MB into memory once,
    a deliberate, bounded exception to the streaming-only rule that applies
    everywhere else. text/plain and text/csv have no reliable signature at
    all; they're checked only for NUL bytes in a bounded prefix, a cheap
    heuristic for "this is actually binary", not an exhaustive scan.
    """
    if content_type == "application/json":
        try:
            json.loads(uploaded_file.read())
        except (ValueError, UnicodeDecodeError):
            return False
        finally:
            uploaded_file.seek(0)
        return True

    if content_type in ("text/plain", "text/csv"):
        chunk = uploaded_file.read(TEXT_SNIFF_SIZE)
        uploaded_file.seek(0)
        return b"\x00" not in chunk

    if content_type in _OOXML_REQUIRED_MEMBER_PREFIX:
        # Cheap magic-byte pre-check first (fast-fail on obviously-not-a-zip
        # input before paying for zipfile's central-directory read).
        head = uploaded_file.read(SIGNATURE_HEAD_SIZE)
        uploaded_file.seek(0)
        if not _check_zip(head):
            return False
        return _check_ooxml_members(uploaded_file, _OOXML_REQUIRED_MEMBER_PREFIX[content_type])

    head = uploaded_file.read(SIGNATURE_HEAD_SIZE)
    uploaded_file.seek(0)
    checker = _SIGNATURE_CHECKS.get(content_type)
    if checker is None:
        return True  # no reliable signature for this type — trust declared type
    return checker(head)
