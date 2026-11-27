"""wechatauto 的个人微信专用 GUI 封装。"""

from __future__ import annotations

from typing import Callable

from wechatauto.guia import WeChatGUI

from wechat_window import find_and_restore_personal_wechat_main


class PersonalWeChatGUI(WeChatGUI):
    """把上游通用窗口查找替换为个人微信专用识别与隐藏窗口恢复。"""

    def __init__(
        self,
        *args,
        event_logger: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        self._event_logger = event_logger
        super().__init__(*args, **kwargs)

    def _find_main_window(self, title: str) -> int:
        # 上游句柄失联重挂也走这里，保证不会在中途退回通用逻辑误选企业微信。
        return find_and_restore_personal_wechat_main(
            preferred_hwnd=getattr(self, "main_hwnd", None),
            logger=self._event_logger,
        )

    def prepare_for_send(self) -> None:
        """每次实发前复核窗口，覆盖长驻期间被隐藏到托盘或微信重启。"""
        hwnd = self._find_main_window(getattr(self, "_main_title", "微信"))
        if not hwnd:
            raise RuntimeError(
                "未找到可用的个人微信主窗口（已排除企业微信）；"
                "请确认微信 4.x 已登录、桌面未锁屏"
            )
        if hwnd != self.main_hwnd:
            if not self.use_window(hwnd):
                raise RuntimeError("个人微信主窗口重新绑定失败")
        else:
            self._update_render_rect()
