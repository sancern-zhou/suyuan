from app.api.utility_routes import get_file_media_type


def test_get_file_media_type_supports_browser_preview_formats():
    assert get_file_media_type(".html") == "text/html"
    assert get_file_media_type(".htm") == "text/html"
    assert get_file_media_type(".png") == "image/png"
    assert get_file_media_type(".jpg") == "image/jpeg"
    assert get_file_media_type(".svg") == "image/svg+xml"
    assert get_file_media_type(".qmd") == "text/markdown"
