from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from agent import WeChatSender
from wechat_gui import PersonalWeChatGUI


class SenderTests(unittest.TestCase):
    def test_gui_is_reused_and_prepared_before_each_send(self):
        sender = WeChatSender()
        gui = Mock()
        gui.send_msg.return_value = {"status": "成功"}
        sender._gui_class = Mock(return_value=gui)

        sender.send_text("测试群", "第一条")
        sender.send_text("测试群", "第二条")

        sender._gui_class.assert_called_once()
        gui.prepare_for_send.assert_called_once_with()
        self.assertEqual(gui.send_msg.call_count, 2)

    def test_unconfirmed_result_still_raises(self):
        sender = WeChatSender()
        gui = Mock()
        gui.send_msg.return_value = {"status": "失败", "message": "未确认"}
        sender._gui_class = Mock(return_value=gui)
        with self.assertRaisesRegex(RuntimeError, "发送未确认"):
            sender.send_text("测试群", "内容")


class PersonalWeChatGUITests(unittest.TestCase):
    def make_gui(self) -> PersonalWeChatGUI:
        gui = PersonalWeChatGUI.__new__(PersonalWeChatGUI)
        gui._main_title = "微信"
        gui._event_logger = None
        gui.main_hwnd = 100
        gui.use_window = Mock(return_value=True)
        gui._update_render_rect = Mock()
        return gui

    @patch("wechat_gui.find_and_restore_personal_wechat_main", return_value=101)
    def test_prepare_rebinds_replaced_window(self, find_window):
        gui = self.make_gui()
        gui.prepare_for_send()
        gui.use_window.assert_called_once_with(101)
        self.assertEqual(find_window.call_args.kwargs["preferred_hwnd"], 100)

    @patch("wechat_gui.find_and_restore_personal_wechat_main", return_value=100)
    def test_prepare_refreshes_existing_window(self, _):
        gui = self.make_gui()
        gui.prepare_for_send()
        gui.use_window.assert_not_called()
        gui._update_render_rect.assert_called_once_with()

    @patch("wechat_gui.find_and_restore_personal_wechat_main", return_value=0)
    def test_prepare_never_falls_back_to_wecom(self, _):
        gui = self.make_gui()
        with self.assertRaisesRegex(RuntimeError, "已排除企业微信"):
            gui.prepare_for_send()
        gui.use_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
