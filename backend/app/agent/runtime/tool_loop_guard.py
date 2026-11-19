"""Tool repeated-call anomaly guard（对齐 ZCode modelAnomalyGuard）。

签名 = 工具名 + 参数规范化哈希，只统计「连续」相同调用（连击制），
任何一次不同调用即重置；用户中途输入/steering 后调用 reset()。

守卫只观察、不干预：达到阈值时不拦截、不缓存、不产生错误结果——工具
照常执行，仅排队一条文本提醒，由 runtime 在本轮结束后以用户消息注入
下一轮上下文（等价 ZCode 的 <system-reminder> 注入）。每连击仅在阈值
点触发一次；注入上限 max_warnings_per_turn 按运行计——守卫随
AgentRuntime 每次运行新建，一次运行即一条用户消息的完整回合，故一次
运行内最多注入 3 条，超出只记日志。
状态查询类工具的改道指引（_REDIRECTION_HINTS）随提醒带回。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

REMINDER_BODY_TEMPLATE = (
    "工具 {tool} 已用完全相同的参数连续调用 {count} 次。"
    "除非用户明确要求原样重试，否则不要再次发起完全相同的调用。"
    "请基于已有结果选择不同的下一步、说明阻塞原因，或向用户求助。"
)


@dataclass
class ToolLoopGuard:
    warning_threshold: int = 3
    # 命名沿用 ZCode maxBudgetWarningsPerTurn；实际按运行计（守卫随
    # AgentRuntime 每次运行新建，一次运行=一条用户消息的完整回合）
    max_warnings_per_turn: int = 3

    # 状态查询类工具的循环改道指引：把正确用法随提醒带回（提醒即召回钩子）。
    # 委派轮询风暴事故（2026-11-08 复盘）后引入。
    _REDIRECTION_HINTS: Dict[str, str] = field(
        default_factory=lambda: {
            "manage_assistant_runs": (
                " 改道：委派进度查询已无进展——需要等待时用 action=get 且传 "
                "wait_seconds（如 120）一次阻塞等待终态；或先做其他工作/直接交付，"
                "委派完成后系统会自动注入结果。"
            ),
        }
    )
    _last_signature: Optional[str] = field(default=None, init=False, repr=False)
    _streak: int = field(default=0, init=False, repr=False)
    _warnings_injected: int = field(default=0, init=False, repr=False)
    _pending_reminders: List[str] = field(default_factory=list, init=False, repr=False)

    def before_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any] | None:
        """从不拦截：返回 warning 字典仅供日志/遥测；提醒经 drain_pending_reminders 注入。"""
        signature = f"{tool_name}:{self._hash(tool_args)}"
        if signature == self._last_signature:
            self._streak += 1
        else:
            self._last_signature = signature
            self._streak = 1
        if self._streak != self.warning_threshold:
            return None

        injected = self._warnings_injected < self.max_warnings_per_turn
        if injected:
            self._warnings_injected += 1
            self._pending_reminders.append(
                REMINDER_BODY_TEMPLATE.format(tool=tool_name, count=self._streak)
                + self._redirection_hint(tool_name)
            )
        return {
            "error": "tool_loop_warning",
            "severity": "warning",
            "summary": (
                f"WARNING: 工具 {tool_name} 已连续相同调用 {self._streak} 次，"
                f"提醒已{'注入' if injected else '达上限仅记录'}。"
                f"{self._redirection_hint(tool_name)}"
            ),
            "repeated": self._streak,
            "reminder_injected": injected,
            "loop_guard": True,
        }

    def drain_pending_reminders(self) -> List[str]:
        """取走本轮排队的提醒文本（runtime 注入下一轮上下文）。"""
        reminders = self._pending_reminders
        self._pending_reminders = []
        return reminders

    def reset(self) -> None:
        """用户新输入/steering 后重置连击（注入预算按运行计，不在此重置）。"""
        self._last_signature = None
        self._streak = 0

    def _redirection_hint(self, tool_name: str) -> str:
        return self._REDIRECTION_HINTS.get(tool_name, "")

    def _hash(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
