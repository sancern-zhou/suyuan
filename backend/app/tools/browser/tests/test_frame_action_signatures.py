import inspect

from app.tools.browser.actions.execute_js import handle_execute_js
from app.tools.browser.actions.extract import handle_extract
from app.tools.browser.actions.file_ops import handle_download, handle_upload
from app.tools.browser.actions.interaction import handle_act
from app.tools.browser.actions.screenshot import handle_screenshot
from app.tools.browser.actions.waiting import handle_wait


def test_browser_actions_accept_frame_target_parameters():
    for func in (
        handle_execute_js,
        handle_act,
        handle_extract,
        handle_wait,
        handle_screenshot,
        handle_download,
        handle_upload,
    ):
        params = inspect.signature(func).parameters
        assert "frame_url" in params
        assert "frame_name" in params
        assert "frame_index" in params
