from __future__ import annotations

import unittest

from wechat_window import (
    WindowInfo,
    find_and_restore_personal_wechat_main,
    is_personal_wechat_main,
    select_personal_wechat_main,
)


def make_window(
    hwnd: int,
    *,
    process: str = "Weixin.exe",
    title: str = "微信",
    class_name: str = "Qt51514QWindowIcon",
    visible: bool = True,
    iconic: bool = False,
    rect=(0, 0, 1100, 700),
) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        pid=1000 + hwnd,
        process_name=process,
        title=title,
        class_name=class_name,
        visible=visible,
        iconic=iconic,
        rect=rect,
    )


class FakeWindowApi:
    def __init__(self, windows: list[WindowInfo], restore_works: bool = True):
        self.windows = {window.hwnd: window for window in windows}
        self.restore_works = restore_works
        self.restored: list[int] = []

    def list_windows(self) -> list[WindowInfo]:
        return list(self.windows.values())

    def restore_window(self, hwnd: int) -> None:
        self.restored.append(hwnd)
        if not self.restore_works:
            return
        old = self.windows[hwnd]
        self.windows[hwnd] = WindowInfo(
            hwnd=old.hwnd,
            pid=old.pid,
            process_name=old.process_name,
            title=old.title,
            class_name=old.class_name,
            visible=True,
            iconic=False,
            rect=old.rect,
        )


class WindowIdentityTests(unittest.TestCase):
    def test_personal_wechat_main_accepted(self):
        self.assertTrue(is_personal_wechat_main(make_window(1)))

    def test_wecom_excluded_by_process_even_though_title_contains_wechat(self):
        enterprise = make_window(2, process="WXWork.exe", title="企业微信")
        self.assertFalse(is_personal_wechat_main(enterprise))
        self.assertIsNone(select_personal_wechat_main([enterprise]))

    def test_wecom_title_defensively_excluded_even_with_wrong_process(self):
        enterprise = make_window(3, process="Weixin.exe", title="企业微信")
        self.assertFalse(is_personal_wechat_main(enterprise))

    def test_small_or_unrelated_weixin_windows_rejected(self):
        small = make_window(4, title="Weixin", rect=(0, 0, 260, 180))
        unrelated = make_window(5, title="图片查看器")
        self.assertFalse(is_personal_wechat_main(small))
        self.assertFalse(is_personal_wechat_main(unrelated))

    def test_preferred_visible_window_is_retained(self):
        current = make_window(10, rect=(0, 0, 1000, 700))
        larger = make_window(11, rect=(0, 0, 1600, 1000))
        selected = select_personal_wechat_main(
            [larger, current], preferred_hwnd=current.hwnd
        )
        self.assertEqual(selected.hwnd, current.hwnd)


class WindowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def recover(self, api, logs):
        return find_and_restore_personal_wechat_main(
            api,
            logger=logs.append,
            timeout_seconds=0.6,
            clock=self.clock,
            sleep=self.sleep,
        )

    def test_visible_personal_wechat_wins_without_restoring_wecom(self):
        personal = make_window(20)
        enterprise = make_window(
            21, process="WXWork.exe", title="企业微信", rect=(0, 0, 2000, 1200)
        )
        api = FakeWindowApi([enterprise, personal])
        logs = []
        self.assertEqual(self.recover(api, logs), personal.hwnd)
        self.assertEqual(api.restored, [])

    def test_hidden_personal_wechat_restored_while_visible_wecom_untouched(self):
        personal = make_window(30, visible=False)
        enterprise = make_window(31, process="WXWork.exe", title="企业微信")
        api = FakeWindowApi([enterprise, personal])
        logs = []
        self.assertEqual(self.recover(api, logs), personal.hwnd)
        self.assertEqual(api.restored, [personal.hwnd])
        self.assertFalse(api.windows[enterprise.hwnd].visible is False)
        self.assertTrue(any("已恢复" in line for line in logs))

    def test_wecom_alone_is_not_restored(self):
        enterprise = make_window(40, process="WXWork.exe", title="企业微信")
        api = FakeWindowApi([enterprise])
        logs = []
        self.assertEqual(self.recover(api, logs), 0)
        self.assertEqual(api.restored, [])
        self.assertTrue(any("已排除企业微信" in line for line in logs))

    def test_failed_restore_returns_zero_instead_of_using_wecom(self):
        personal = make_window(50, visible=False)
        enterprise = make_window(51, process="WXWork.exe", title="企业微信")
        api = FakeWindowApi([enterprise, personal], restore_works=False)
        logs = []
        self.assertEqual(self.recover(api, logs), 0)
        self.assertEqual(api.restored, [personal.hwnd])
        self.assertTrue(any("仍不可见" in line for line in logs))


class WindowDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def recover(self, api, logs):
        return find_and_restore_personal_wechat_main(
            api,
            logger=logs.append,
            timeout_seconds=0.6,
            clock=self.clock,
            sleep=self.sleep,
        )

    def test_not_found_logs_size_rejection_reason(self):
        small = make_window(60, title="微信", rect=(0, 0, 500, 400), visible=False)
        logs = []
        self.assertEqual(self.recover(FakeWindowApi([small]), logs), 0)
        joined = "\n".join(logs)
        self.assertIn("诊断", joined)
        self.assertIn("size=500x400低于阈值", joined)

    def test_not_found_logs_process_lookup_failure(self):
        no_process = make_window(61, process="", visible=False)
        logs = []
        self.assertEqual(self.recover(FakeWindowApi([no_process]), logs), 0)
        self.assertIn("process=查询失败", "\n".join(logs))

    def test_not_found_with_only_unrelated_windows_reports_absence(self):
        other = make_window(62, process="other.exe", title="记事本", class_name="Notepad")
        logs = []
        self.assertEqual(self.recover(FakeWindowApi([other]), logs), 0)
        joined = "\n".join(logs)
        self.assertIn("没有任何微信相关窗口", joined)


if __name__ == "__main__":
    unittest.main()
