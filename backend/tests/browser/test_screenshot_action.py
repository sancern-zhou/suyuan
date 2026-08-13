from app.tools.browser.actions import screenshot


class FakePage:
    url = "https://example.com/page"

    def title(self):
        return "Example Page"

    def screenshot(self, full_page=False, type="png"):
        assert full_page is True
        assert type == "png"
        return b"png-bytes"

    def evaluate(self, _script):
        return {
            "title": "Example Page",
            "heading": "Example Heading",
            "description": "Example Description",
            "structure": {
                "images": 0,
                "links": 1,
                "forms": 0,
                "tables": 0,
                "headings": 1,
            },
        }


class FakeManager:
    def get_active_page(self, session_id):
        assert session_id == "session-1"
        return FakePage()


class FakeImageCache:
    def save(self, base64_data, chart_id=None):
        assert base64_data
        assert chart_id.startswith("screenshot_")
        return {
            "image_id": chart_id,
            "local_path": f"/tmp/{chart_id}.png",
            "url": f"/api/image/{chart_id}",
            "size_kb": 1.23,
        }


def test_screenshot_returns_local_path_for_tool_chaining(monkeypatch):
    monkeypatch.setattr(screenshot, "get_image_cache", lambda: FakeImageCache())

    result = screenshot.handle_screenshot(
        FakeManager(),
        session_id="session-1",
        full_page=True,
    )

    assert result["image_id"].startswith("screenshot_")
    assert result["image_url"] == f"/api/image/{result['image_id']}"
    assert result["local_path"] == f"/tmp/{result['image_id']}.png"
    assert result["size_kb"] == 1.23
    assert result["markdown_image"] == f"![Example Page](/api/image/{result['image_id']})"
