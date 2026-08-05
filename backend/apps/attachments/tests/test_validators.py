import io
import zipfile

import pytest

from apps.attachments import validators
from apps.attachments.validators import (
    ALLOWED_CONTENT_TYPES,
    AttachmentTooLarge,
    UnsupportedContentType,
)

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG_HEAD = b"\xff\xd8\xff\xe0" + b"\x00" * 28
GIF_HEAD = b"GIF89a" + b"\x00" * 26
WEBP_HEAD = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
PDF_HEAD = b"%PDF-1.4\n" + b"\x00" * 23
ZIP_HEAD = b"PK\x03\x04" + b"\x00" * 28
OLE_HEAD = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24
MP4_HEAD = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


class _FakeUploadedFile(io.BytesIO):
    """Minimal stand-in with the subset of UploadedFile's API
    verify_uploaded_content actually uses (.read/.seek); real API/service
    tests use Django's SimpleUploadedFile instead."""


@pytest.mark.parametrize(
    "content_type",
    [
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/json",
        "application/zip",
        "video/mp4",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ],
)
def test_every_allowed_format_is_in_the_allow_list(content_type):
    assert content_type in ALLOWED_CONTENT_TYPES
    validators.validate_content_type(content_type)  # must not raise


def test_svg_rejected():
    assert "image/svg+xml" not in ALLOWED_CONTENT_TYPES
    with pytest.raises(UnsupportedContentType):
        validators.validate_content_type("image/svg+xml")


def test_unknown_type_rejected():
    with pytest.raises(UnsupportedContentType):
        validators.validate_content_type("application/x-executable")


class TestSizeValidation:
    def test_at_limit_accepted(self):
        validators.validate_size(10 * 1024 * 1024, max_size_bytes=10 * 1024 * 1024)  # no raise

    def test_over_limit_rejected(self):
        with pytest.raises(AttachmentTooLarge):
            validators.validate_size(10 * 1024 * 1024 + 1, max_size_bytes=10 * 1024 * 1024)

    def test_zero_rejected(self):
        with pytest.raises(AttachmentTooLarge):
            validators.validate_size(0, max_size_bytes=10 * 1024 * 1024)


class TestExtensionForContentType:
    def test_extension_matches_type(self):
        assert validators.extension_for_content_type("image/png") == ".png"
        assert validators.extension_for_content_type("application/pdf") == ".pdf"

    def test_every_allowed_type_has_an_extension(self):
        for content_type in ALLOWED_CONTENT_TYPES:
            ext = validators.extension_for_content_type(content_type)
            assert ext.startswith(".")


class TestSanitizeFilename:
    def test_strips_posix_path_components(self):
        assert validators.sanitize_filename("../../etc/passwd") == "passwd"

    def test_strips_windows_path_components(self):
        assert validators.sanitize_filename("C:\\Users\\evil\\payload.exe") == "payload.exe"

    def test_removes_control_characters(self):
        assert validators.sanitize_filename("evil\x00name\x1f.txt") == "evil_name_.txt"

    def test_strips_reserved_characters(self):
        assert validators.sanitize_filename('weird<>:"|?*name.txt') == "weird_______name.txt"

    def test_empty_falls_back_to_generic_name(self):
        assert validators.sanitize_filename("") == "attachment"

    def test_whitespace_and_dots_only_falls_back(self):
        assert validators.sanitize_filename("   ...   ") == "attachment"

    def test_caps_length(self):
        long_name = "a" * 500 + ".txt"
        result = validators.sanitize_filename(long_name)
        assert len(result) == validators.MAX_FILENAME_LENGTH

    def test_ordinary_filename_untouched(self):
        assert validators.sanitize_filename("screenshot (1).png") == "screenshot (1).png"


class TestSignatureVerification:
    @pytest.mark.parametrize(
        "content_type,valid_head",
        [
            ("image/png", PNG_HEAD),
            ("image/jpeg", JPEG_HEAD),
            ("image/gif", GIF_HEAD),
            ("image/webp", WEBP_HEAD),
            ("application/pdf", PDF_HEAD),
            ("application/zip", ZIP_HEAD),
            # DOCX/XLSX are deliberately NOT parametrized here — a bare magic
            # -byte header isn't a valid zip archive at all (no central
            # directory), and those two types are verified structurally, not
            # by prefix alone. See TestOOXMLValidation below.
            ("application/msword", OLE_HEAD),
            ("application/vnd.ms-excel", OLE_HEAD),
            ("video/mp4", MP4_HEAD),
        ],
    )
    def test_true_positive(self, content_type, valid_head):
        f = _FakeUploadedFile(valid_head)
        assert validators.verify_uploaded_content(content_type, f) is True
        assert f.tell() == 0  # seeked back for the caller to stream afterward

    @pytest.mark.parametrize(
        "content_type",
        [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "application/pdf",
            "application/zip",
            "application/msword",
            "video/mp4",
        ],
    )
    def test_true_negative(self, content_type):
        f = _FakeUploadedFile(b"not the right bytes at all" + b"\x00" * 20)
        assert validators.verify_uploaded_content(content_type, f) is False
        assert f.tell() == 0

    def test_json_valid_document_accepted(self):
        f = _FakeUploadedFile(b'{"hello": "world"}')
        assert validators.verify_uploaded_content("application/json", f) is True
        assert f.tell() == 0

    def test_json_malformed_document_rejected(self):
        f = _FakeUploadedFile(b"{not valid json")
        assert validators.verify_uploaded_content("application/json", f) is False

    def test_json_non_utf8_bytes_rejected(self):
        f = _FakeUploadedFile(b"\xff\xfe\x00\x01")
        assert validators.verify_uploaded_content("application/json", f) is False

    def test_text_plain_accepted(self):
        f = _FakeUploadedFile(b"just some ordinary text content")
        assert validators.verify_uploaded_content("text/plain", f) is True

    def test_text_plain_with_nul_byte_rejected(self):
        f = _FakeUploadedFile(b"looks like text\x00but has a NUL byte")
        assert validators.verify_uploaded_content("text/plain", f) is False

    def test_csv_with_nul_byte_rejected(self):
        f = _FakeUploadedFile(b"a,b,c\n1,\x00,3")
        assert validators.verify_uploaded_content("text/csv", f) is False

    def test_csv_ordinary_content_accepted(self):
        f = _FakeUploadedFile(b"a,b,c\n1,2,3\n")
        assert validators.verify_uploaded_content("text/csv", f) is True

    def test_mp4_missing_ftyp_rejected(self):
        f = _FakeUploadedFile(b"\x00\x00\x00\x18wrongbox" + b"\x00" * 16)
        assert validators.verify_uploaded_content("video/mp4", f) is False

    def test_mp4_too_short_rejected(self):
        f = _FakeUploadedFile(b"\x00\x00\x00")
        assert validators.verify_uploaded_content("video/mp4", f) is False


DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _docx_bytes() -> bytes:
    return _build_zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "_rels/.rels": b"<Relationships/>",
            "word/document.xml": b"<w:document/>",
        }
    )


def _xlsx_bytes() -> bytes:
    return _build_zip(
        {
            "[Content_Types].xml": b"<Types/>",
            "_rels/.rels": b"<Relationships/>",
            "xl/workbook.xml": b"<workbook/>",
        }
    )


def _plain_zip_bytes() -> bytes:
    return _build_zip({"readme.txt": b"just a plain zip, no OOXML parts at all"})


class TestOOXMLValidation:
    """A magic-byte check alone can't distinguish DOCX/XLSX from a plain ZIP
    (or from each other) — all three share the same PK\\x03\\x04 signature.
    These exercise the structural check in
    apps.attachments.validators._check_ooxml_members."""

    def test_real_docx_accepted_as_docx(self):
        f = _FakeUploadedFile(_docx_bytes())
        assert validators.verify_uploaded_content(DOCX_TYPE, f) is True
        assert f.tell() == 0

    def test_real_xlsx_accepted_as_xlsx(self):
        f = _FakeUploadedFile(_xlsx_bytes())
        assert validators.verify_uploaded_content(XLSX_TYPE, f) is True
        assert f.tell() == 0

    def test_plain_zip_declared_as_docx_rejected(self):
        f = _FakeUploadedFile(_plain_zip_bytes())
        assert validators.verify_uploaded_content(DOCX_TYPE, f) is False

    def test_plain_zip_declared_as_xlsx_rejected(self):
        f = _FakeUploadedFile(_plain_zip_bytes())
        assert validators.verify_uploaded_content(XLSX_TYPE, f) is False

    def test_docx_content_declared_as_xlsx_rejected(self):
        # Right OOXML shape, wrong part prefix — a genuine DOCX must not pass
        # as an XLSX just because both are OOXML/ZIP.
        f = _FakeUploadedFile(_docx_bytes())
        assert validators.verify_uploaded_content(XLSX_TYPE, f) is False

    def test_xlsx_content_declared_as_docx_rejected(self):
        f = _FakeUploadedFile(_xlsx_bytes())
        assert validators.verify_uploaded_content(DOCX_TYPE, f) is False

    def test_zip_missing_content_types_xml_rejected(self):
        # Has a word/ member but isn't a real OOXML package (no
        # [Content_Types].xml at all) — still must not pass.
        f = _FakeUploadedFile(_build_zip({"word/document.xml": b"<w:document/>"}))
        assert validators.verify_uploaded_content(DOCX_TYPE, f) is False

    def test_corrupted_non_zip_bytes_declared_as_docx_rejected(self):
        f = _FakeUploadedFile(b"not a zip file at all, just garbage bytes")
        assert validators.verify_uploaded_content(DOCX_TYPE, f) is False

    def test_plain_zip_still_valid_as_plain_zip(self):
        # The one type with no member requirement at all — contents don't
        # matter, only the outer ZIP signature does.
        f = _FakeUploadedFile(_plain_zip_bytes())
        assert validators.verify_uploaded_content("application/zip", f) is True

    def test_docx_bytes_also_valid_as_plain_zip(self):
        # A real DOCX is, at the container level, also a valid ZIP — declaring
        # it as application/zip is unusual but not something this layer
        # should reject (it has no OOXML-specific expectations to violate).
        f = _FakeUploadedFile(_docx_bytes())
        assert validators.verify_uploaded_content("application/zip", f) is True
