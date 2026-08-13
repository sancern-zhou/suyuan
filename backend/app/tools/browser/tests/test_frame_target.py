from app.tools.browser.services.frame_target import FrameTarget, resolve_frame


class FakeFrame:
    def __init__(self, url="", name=""):
        self.url = url
        self.name = name


class FakePage:
    def __init__(self, frames):
        self.frames = frames


def test_resolve_frame_defaults_to_main_frame():
    main = FakeFrame("http://app.local/", "")
    child = FakeFrame("http://app.local/Page/workingOrderList", "")

    assert resolve_frame(FakePage([main, child])) is main


def test_resolve_frame_by_url_fragment():
    main = FakeFrame("http://app.local/", "")
    child = FakeFrame("http://app.local/Page/workingOrderList", "")

    assert resolve_frame(FakePage([main, child]), frame_url="workingOrderList") is child


def test_resolve_frame_by_name():
    main = FakeFrame("http://app.local/", "")
    child = FakeFrame("http://app.local/Page/workingOrderList", "orders")

    assert resolve_frame(FakePage([main, child]), frame_name="orders") is child


def test_resolve_frame_by_index():
    main = FakeFrame("http://app.local/", "")
    child = FakeFrame("http://app.local/Page/workingOrderList", "")

    assert resolve_frame(FakePage([main, child]), frame_index=1) is child


def test_frame_target_from_prefixed_ref():
    target = FrameTarget.from_ref("f2:e8")

    assert target.frame_index == 2
    assert target.element_ref == "e8"
