"""工作流停摆观测（stall watch，对齐 ZCode run 级 stall clock）。

ZCode 的停摆时钟挂在 driver 上，信号是"模型请求成功/重试上膛"；我们 v1 用
journal 事件近似——任何节点进度/状态变化都算进展。运行中的工作流若在阈值内
没有任何事件，说明所有在跑节点既没完成也没报错（典型场景：模型请求在无限
重试限流），此时发一次 `workflow.stalled` 通知。

红线（与 ZCode 一致）：纯观察。停摆通知不触发任何失败/取消决策，瞬态重试
依然无上限，逃生口是这个通知 + 节点超时预算。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Optional


class WorkflowStallWatch:
    """每个静默段至多通知一次；下个事件重新上膛。"""

    # 观察轮询间隔：阈值较短时按阈值 1/4，否则 30s。
    POLL_INTERVAL_SECONDS = 30.0

    def __init__(
        self,
        *,
        threshold_seconds: float,
        on_stalled: Callable[[Dict[str, Any]], None],
    ) -> None:
        self.threshold_seconds = max(1.0, float(threshold_seconds))
        self._on_stalled = on_stalled
        self._last_progress: Optional[float] = None
        self._notified = False
        self._task: Optional[asyncio.Task] = None
        self._stopped = False

    def note_progress(self) -> None:
        """任何节点/工作流事件都调用：重置静默计时并重新上膛。"""
        self._last_progress = time.monotonic()
        self._notified = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped = False
            # 尊重 start 前已记录的进展基准（重放/续跑场景）；全新运行从现在起算。
            if self._last_progress is None:
                self._last_progress = time.monotonic()
            self._task = asyncio.create_task(self._watch())

    async def stop(self) -> None:
        self._stopped = True
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _watch(self) -> None:
        interval = min(self.POLL_INTERVAL_SECONDS, self.threshold_seconds / 4.0)
        while not self._stopped:
            await asyncio.sleep(interval)
            if self._stopped or self._notified or self._last_progress is None:
                continue
            since_ms = (time.monotonic() - self._last_progress) * 1000.0
            if since_ms < self.threshold_seconds * 1000.0:
                continue
            self._notified = True
            try:
                self._on_stalled({"since_ms": round(since_ms), "reason": "no_journal_event"})
            except Exception:  # noqa: BLE001 —— 观察者异常绝不影响执行
                pass
