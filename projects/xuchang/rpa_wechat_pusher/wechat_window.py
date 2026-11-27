"""个人微信 4.x 主窗口识别与隐藏窗口恢复。

企业微信与个人微信可能同时运行，且“企业微信”标题同样包含“微信”。因此
进程名 Weixin.exe 是硬条件，标题/Qt 类名只用于识别个人微信主窗；WXWork.exe
及其他进程一律不参与选择，更不能被恢复或置前。
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable, Iterable

PERSONAL_WECHAT_PROCESS = "weixin.exe"
WECOM_PROCESS = "wxwork.exe"
MAIN_CLASS_PREFIX = "Qt51514QWindowIcon"
MAIN_TITLE_KEYWORDS = ("微信", "wechat", "weixin")
MIN_WINDOW_SIZE = 800
MIN_WINDOW_PORTRAIT = 600


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    process_name: str
    title: str
    class_name: str
    visible: bool
    iconic: bool
    rect: tuple[int, int, int, int]

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]


def _title_matches(title: str) -> bool:
    lowered = title.strip().lower()
    return any(keyword in lowered for keyword in MAIN_TITLE_KEYWORDS)


def _is_minimized_main(window: WindowInfo) -> bool:
    # 最小化时 Windows 返回 157x25 左右的占位矩形，不能据此排除主窗。
    return window.iconic and window.class_name.startswith(MAIN_CLASS_PREFIX)


def is_personal_wechat_main(window: WindowInfo) -> bool:
    """只接受个人微信主窗；可见性由调用方按查找/恢复阶段另行判断。"""
    process = window.process_name.strip().lower()
    title = window.title.strip()
    if process != PERSONAL_WECHAT_PROCESS or process == WECOM_PROCESS:
        return False
    # 进程条件已经能区分两者；标题条件再防异常窗口属性或测试替身漏标进程。
    if "企业微信" in title or "wecom" in title.lower():
        return False
    if not _title_matches(title):
        return False
    if _is_minimized_main(window):
        return True
    width, height = window.width, window.height
    if width <= 0 or height <= 0:
        return False
    return (
        width >= MIN_WINDOW_SIZE
        or height >= MIN_WINDOW_SIZE
        or (width < height and height >= MIN_WINDOW_PORTRAIT)
    )


def select_personal_wechat_main(
    windows: Iterable[WindowInfo],
    *,
    visible_only: bool = True,
    preferred_hwnd: int | None = None,
) -> WindowInfo | None:
    """从候选中选主窗，优先沿用当前句柄，避免可见候选间无谓切换。

    可见候选不含最小化窗口；最小化窗口仅供恢复分支选取，不能直接用于发送。
    """
    candidates = [
        window
        for window in windows
        if is_personal_wechat_main(window)
        and (not visible_only or (window.visible and not window.iconic))
    ]
    if not candidates:
        return None
    if preferred_hwnd:
        for window in candidates:
            if window.hwnd == preferred_hwnd:
                return window

    def rank(window: WindowInfo) -> tuple[int, int]:
        score = 0
        if window.title.strip().lower() in {"微信", "wechat", "weixin"}:
            score += 4
        if window.class_name.startswith(MAIN_CLASS_PREFIX):
            score += 2
        return score, window.width * window.height

    return max(candidates, key=rank)


class Win32WindowApi:
    """窗口恢复所需的最小 Win32 边界，测试用替身替换，不碰真实桌面。"""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

    def _process_name(self, pid: int) -> str:
        if not pid:
            return ""
        handle = self._kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if self._kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return os.path.basename(buffer.value).lower()
            return ""
        finally:
            self._kernel32.CloseHandle(handle)

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        user32 = self._user32

        def callback(hwnd, _):
            title_buffer = ctypes.create_unicode_buffer(512)
            class_buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buffer, 512)
            user32.GetClassNameW(hwnd, class_buffer, 256)
            title = title_buffer.value.strip()
            class_name = class_buffer.value
            # 非微信特征的桌面窗口无需逐个 OpenProcess 查进程名。
            if not _title_matches(title) and not class_name.startswith("Qt"):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            windows.append(WindowInfo(
                hwnd=int(hwnd),
                pid=pid.value,
                process_name=self._process_name(pid.value),
                title=title,
                class_name=class_name,
                visible=bool(user32.IsWindowVisible(hwnd)),
                iconic=bool(user32.IsIconic(hwnd)),
                rect=(rect.left, rect.top, rect.right, rect.bottom),
            ))
            return True

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
        )
        callback_ref = callback_type(callback)
        user32.EnumWindows(callback_ref, 0)
        return windows

    def restore_window(self, hwnd: int) -> None:
        """显示隐藏到托盘的窗口；若已最小化，再恢复正常尺寸。"""
        self._user32.ShowWindowAsync(hwnd, 5)  # SW_SHOW
        if self._user32.IsIconic(hwnd):
            self._user32.ShowWindowAsync(hwnd, 9)  # SW_RESTORE
        self._user32.SetWindowPos(
            hwnd,
            ctypes.c_void_p(0),  # HWND_TOP，不保留置顶
            0,
            0,
            0,
            0,
            0x0001 | 0x0002 | 0x0040,  # NOSIZE | NOMOVE | SHOWWINDOW
        )


def describe_window_for_diagnostics(window: WindowInfo) -> str:
    """把窗口原始属性与识别结论压成一行，供"未找到主窗"时定位真值。

    只读、不改变任何状态；列出被拒绝的具体原因（进程名查询失败、标题不符、
    尺寸低于阈值），避免事后只能靠系统事件猜测。
    """
    process = window.process_name.strip().lower()
    reasons: list[str] = []
    if process != PERSONAL_WECHAT_PROCESS:
        reasons.append(f"process={process or '查询失败'}")
    title = window.title.strip()
    if "企业微信" in title or "wecom" in title.lower():
        reasons.append("企业微信标题")
    elif not _title_matches(title):
        reasons.append(f"title={title!r}")
    width, height = window.width, window.height
    if not _is_minimized_main(window):
        if width <= 0 or height <= 0:
            reasons.append(f"size={width}x{height}非正")
        elif not (
            width >= MIN_WINDOW_SIZE
            or height >= MIN_WINDOW_SIZE
            or (width < height and height >= MIN_WINDOW_PORTRAIT)
        ):
            reasons.append(f"size={width}x{height}低于阈值")
    verdict = "ACCEPT" if is_personal_wechat_main(window) else "reject:" + ";".join(reasons)
    return (
        f"hwnd=0x{window.hwnd:x} pid={window.pid} class={window.class_name!r} "
        f"{'visible' if window.visible else 'hidden'} rect={window.rect} -> {verdict}"
    )


def _emit_window_diagnostics(windows: Iterable[WindowInfo], emit) -> None:
    """找不到主窗时输出枚举真值：微信相关窗口逐条列出，其余应用只计数。"""
    related, other = [], 0
    for window in windows:
        process = window.process_name.strip().lower()
        if (
            process in (PERSONAL_WECHAT_PROCESS, WECOM_PROCESS)
            or not process
            or _title_matches(window.title)
            or "企业微信" in window.title
            or window.class_name.startswith(MAIN_CLASS_PREFIX)
        ):
            related.append(window)
        else:
            other += 1
    if not related:
        emit(
            f"[warn] 诊断：本次 {other} 个候选窗口中没有任何微信相关窗口"
            "（主窗可能未创建、已销毁，或标题/类名读取异常被前置过滤）"
        )
        return
    emit(
        f"[warn] 诊断：本次枚举 {len(related) + other} 个候选，"
        f"其中 {len(related)} 个微信相关（其余 {other} 个为其他应用），逐条："
    )
    for window in related:
        emit("  " + describe_window_for_diagnostics(window))


def find_and_restore_personal_wechat_main(
    api=None,
    *,
    preferred_hwnd: int | None = None,
    logger: Callable[[str], None] | None = None,
    timeout_seconds: float = 3.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """返回可见个人微信主窗；可见查找失败时恢复隐藏或最小化主窗并复查。

    恢复只发生在实际发送前。没有个人微信主窗、恢复失败或桌面锁定时返回 0，
    由上层保留队列稍后重试；绝不拿企业微信窗口充当兜底。
    """
    api = api or Win32WindowApi()
    emit = logger or (lambda _: None)
    windows = api.list_windows()
    visible = select_personal_wechat_main(
        windows, preferred_hwnd=preferred_hwnd
    )
    if visible:
        return visible.hwnd

    hidden = select_personal_wechat_main(
        windows, visible_only=False, preferred_hwnd=preferred_hwnd
    )
    if hidden is None:
        emit("[warn] 未找到个人微信主窗口（仅识别 Weixin.exe，已排除企业微信 WXWork.exe）")
        _emit_window_diagnostics(windows, emit)
        return 0

    state = "最小化" if hidden.iconic else "隐藏"
    emit(f"[info] 发现{state}的个人微信主窗口 hwnd=0x{hidden.hwnd:x}，尝试恢复")
    try:
        api.restore_window(hidden.hwnd)
    except OSError as exc:
        emit(f"[warn] 恢复个人微信主窗口失败：{exc}")
        return 0

    deadline = clock() + timeout_seconds
    while True:
        restored = select_personal_wechat_main(
            api.list_windows(),
            preferred_hwnd=hidden.hwnd,
        )
        if restored:
            emit(f"[info] 个人微信主窗口已恢复 hwnd=0x{restored.hwnd:x}")
            return restored.hwnd
        if clock() >= deadline:
            emit("[warn] 个人微信主窗口恢复后仍不可见，可能已锁屏或桌面会话断开")
            return 0
        sleep(0.2)
