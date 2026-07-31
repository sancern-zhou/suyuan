import pytest

from app.api.upload_routes import get_file_category, validate_file_type, validate_svg_content


def test_html_upload_type_is_supported() -> None:
    assert validate_file_type("index.html", "text/html") == (True, "")
    assert get_file_category("text/html", "index.html") == "document"


def test_htm_upload_extension_is_supported_with_unknown_mime() -> None:
    assert validate_file_type("legacy.htm", "application/octet-stream") == (True, "")
    assert get_file_category("application/octet-stream", "legacy.htm") == "document"


def test_svg_upload_type_is_supported() -> None:
    assert validate_file_type("framework.svg", "image/svg+xml") == (True, "")
    assert get_file_category("image/svg+xml", "framework.svg") == "image"


def test_safe_svg_content_is_supported() -> None:
    validate_svg_content(b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>')


def test_active_svg_content_is_rejected() -> None:
    with pytest.raises(ValueError, match="不允许的元素"):
        validate_svg_content(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
