import pytest
from playwright.sync_api import sync_playwright

from app.tools.browser.actions.interaction import handle_act
from app.tools.browser.actions.waiting import handle_wait
from app.tools.browser import tool as browser_tool_module
from app.tools.browser.refs.ref_resolver import set_global_refs
from app.tools.browser.tool import BrowserTool


class FakePage:
    url = "http://example.test"

    def __init__(self):
        self.waited = []
        self.frames = [self]

    def wait_for_timeout(self, time_ms):
        self.waited.append(time_ms)

    def title(self):
        return "Example"


class FakeManager:
    def __init__(self):
        self.page = FakePage()
        self._contexts = {}

    def get_active_page(self, session_id="default"):
        return self.page


def test_wait_timeout_only_is_treated_as_fixed_seconds_wait():
    manager = FakeManager()

    result = handle_wait(manager, timeout=3)

    assert manager.page.waited == [3000]
    assert result["success"] is True
    assert result["conditions_applied"] == ["timeMs(3000ms)"]


class FakeExecutor:
    active_sessions = 1

    def get_session_thread(self, session_id):
        return 123

    def submit(self, session_id, func, action, **kwargs):
        return {"type": "error", "error": "SyntaxError: Unexpected token ';'"}


@pytest.mark.asyncio
async def test_browser_execute_reports_handler_error_as_failed(monkeypatch):
    monkeypatch.setattr(browser_tool_module, "get_session_executor", lambda: FakeExecutor())

    result = await BrowserTool().execute("execute_js", code="document.title;")

    assert result["success"] is False
    assert "SyntaxError" in result["error"]
    assert "execute_js" in result["summary"]


def test_act_rejects_text_on_non_editable_ref_with_click_hint():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.set_content('<a href="javascript:void(0)">运维管理</a>')

        manager = FakeManager()
        manager.page = page
        set_global_refs({"f0:e22": {"role": "link", "name": "运维管理"}})

        with pytest.raises(RuntimeError) as exc_info:
            handle_act(manager, ref="f0:e22", text="运维管理")

        message = str(exc_info.value)
        assert "non-editable" in message
        assert "role=link" in message
        assert "click=True" in message

        browser.close()
