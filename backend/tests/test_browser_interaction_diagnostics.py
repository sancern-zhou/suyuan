import pytest


class _FakeLocator:
    def __init__(self, count=0, fill_error=None):
        self._count = count
        self._fill_error = fill_error

    def count(self):
        return self._count

    def fill(self, text, timeout=None):
        if self._fill_error:
            raise self._fill_error


class _FakeFrame:
    def __init__(self, url, selector_counts=None, fill_error=None):
        self.url = url
        self._selector_counts = selector_counts or {}
        self._fill_error = fill_error

    def locator(self, selector):
        return _FakeLocator(
            count=self._selector_counts.get(selector, 0),
            fill_error=self._fill_error,
        )


class _FakePage:
    title = "Login"
    url = "https://example.test/login"

    def __init__(self):
        self.frames = [
            _FakeFrame(
                "https://example.test/login",
                fill_error=Exception(
                    'Locator.fill: Timeout 30000ms exceeded.\n'
                    'Call log:\n  - waiting for locator("#txtVcode")'
                ),
            ),
            _FakeFrame(
                "https://example.test/login/captcha-frame",
                selector_counts={"#txtVcode": 1},
            ),
        ]


def test_text_action_timeout_mentions_iframe_selector_match():
    from app.tools.browser.actions.interaction import handle_act

    manager = type("Manager", (), {"get_active_page": lambda self, session_id: _FakePage()})()

    with pytest.raises(RuntimeError) as exc_info:
        handle_act(manager, selector="#txtVcode", text="2857")

    error = str(exc_info.value)
    assert "frame_index=1" in error
    assert "selector=\"#txtVcode\"" in error
    assert "snapshot" in error
    assert "error_code=SELECTOR_IN_OTHER_FRAME" in error
    assert "required_action=snapshot" in error


def test_click_unknown_ref_error_keeps_ref_descriptor():
    from app.tools.browser.actions.interaction import handle_act

    manager = type("Manager", (), {"get_active_page": lambda self, session_id: _FakePage()})()

    with pytest.raises(RuntimeError) as exc_info:
        handle_act(manager, ref="e15", click=True)

    error = str(exc_info.value)
    assert "Failed to click e15" in error
    assert "Failed to click None" not in error


def test_unknown_ref_error_exposes_structured_contract():
    from app.tools.browser.actions.interaction import handle_act

    manager = type("Manager", (), {"get_active_page": lambda self, session_id: _FakePage()})()

    with pytest.raises(RuntimeError) as exc_info:
        handle_act(manager, ref="e15", click=True)

    error = str(exc_info.value)
    assert "UNKNOWN_REF" in error
    assert "required_action=snapshot" in error
    assert "current_refs" in error


def test_bare_ref_is_ambiguous_when_frame_refs_are_available():
    from app.tools.browser.refs.ref_resolver import RefResolver

    resolver = RefResolver()
    resolver.set_refs({"f0:e1": {"role": "button", "name": "Submit"}})

    with pytest.raises(ValueError) as exc_info:
        resolver.resolve(_FakePage(), "e1")

    error = str(exc_info.value)
    assert "AMBIGUOUS_REF" in error
    assert "f0:e1" in error
