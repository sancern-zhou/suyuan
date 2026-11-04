import pytest

from app.api.upload_routes import (
    MAX_ARCHIVE_SIZE,
    MAX_DOCUMENT_SIZE,
    _attachment_renderer,
    get_file_category,
    get_max_size,
    validate_file_type,
    validate_svg_content,
)


def test_html_upload_type_is_supported() -> None:
    assert validate_file_type("index.html", "text/html") == (True, "")
    assert get_file_category("text/html", "index.html") == "document"


def test_htm_upload_extension_is_supported_with_unknown_mime() -> None:
    assert validate_file_type("legacy.htm", "application/octet-stream") == (True, "")
    assert get_file_category("application/octet-stream", "legacy.htm") == "document"


def test_svg_upload_type_is_supported() -> None:
    assert validate_file_type("framework.svg", "image/svg+xml") == (True, "")
    assert get_file_category("image/svg+xml", "framework.svg") == "image"


def test_zip_upload_extension_is_supported() -> None:
    assert validate_file_type("materials.zip", "application/zip") == (True, "")
    assert validate_file_type("materials.zip", "application/x-zip-compressed") == (True, "")
    assert validate_file_type("materials.zip", "application/octet-stream") == (True, "")
    assert get_file_category("application/zip", "materials.zip") == "document"


def test_zip_archive_size_limit_is_relaxed() -> None:
    assert get_max_size("application/zip", "materials.zip") == MAX_ARCHIVE_SIZE
    assert get_max_size("application/octet-stream", "materials.zip") == MAX_ARCHIVE_SIZE
    assert MAX_ARCHIVE_SIZE > MAX_DOCUMENT_SIZE


def test_non_archive_document_keeps_document_size_limit() -> None:
    assert get_max_size("application/pdf", "report.pdf") == MAX_DOCUMENT_SIZE
    assert get_max_size(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "report.docx",
    ) == MAX_DOCUMENT_SIZE


def test_zip_attachment_renders_as_plain_file() -> None:
    assert _attachment_renderer("application/zip", "materials.zip") == "file"
    assert _attachment_renderer("application/x-zip-compressed", "materials.zip") == "file"


def test_safe_svg_content_is_supported() -> None:
    validate_svg_content(b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>')


def test_active_svg_content_is_rejected() -> None:
    with pytest.raises(ValueError, match="不允许的元素"):
        validate_svg_content(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
