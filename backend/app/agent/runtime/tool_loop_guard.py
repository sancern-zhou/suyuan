"""Tool no-progress loop detection.

计数语义对齐 ZCode modelAnomalyGuard：签名 = 工具名 + 参数规范化哈希，
只统计「连续」相同调用（连击制），任何一次不同调用即重置计数；
用户中途输入/steering 后也应调用 reset()——明确指示下的重试不受罚。

拦截文本不是单纯报错：block 附带行动指引与上一次相同调用的真实结果
（见 record_result()），避免「错误结果诱发原样重试」的反馈环；
状态查询类工具的改道指引（_REDIRECTION_HINTS）继续随错误信息带回。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# block 提示附带的上次真实结果截断长度（字符），防止大结果反复撑上下文
LAST_RESULT_EXCERPT_LIMIT = 2000
# 保留最近多少个签名的结果摘要
LAST_RESULT_CACHE_SIZE = 20


@dataclass
class ToolLoopGuard:
    warning_threshold: int = 3
    critical_threshold: int = 5
    soft_only_tools: frozenset[str] = frozenset({"snapshot", "status", "wait", "tabs"})
    hard_block_tools: frozenset[str] = frozenset({"navigate", "open", "act"})
    history: List[Dict[str, str]] = field(default_factory=list)

    # 状态查询类工具的循环改道指引：拦截不是终点，把正确用法随错误信息带回
    # （错误信息即召回钩子）。委派轮询风暴事故（2026-11-08 复盘）后引入。
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
    _last_results: Dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def before_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any] | None:
        args_hash = self._hash(tool_args)
        signature = f"{tool_name}:{args_hash}"
        if signature == self._last_signature:
            self._streak += 1
        else:
            self._last_signature = signature
            self._streak = 1
        self.history.append({"tool": tool_name, "args": args_hash})
        self.history = self.history[-50:]
        repeated = self._streak

        if tool_name in self.soft_only_tools:
            if repeated >= self.warning_threshold:
                return self._build_warning(tool_name, repeated)
            return None

        if repeated >= self.critical_threshold or tool_name in self.hard_block_tools and repeated >= self.warning_threshold:
            return self._build_block(tool_name, repeated)

        if repeated >= self.warning_threshold:
            return self._build_warning(tool_name, repeated)
        return None

    def record_result(self, tool_name: str, tool_args: Dict[str, Any], result: Any) -> None:
        """记录一次真实执行结果，block 时附带其摘要，让模型有据可用。"""
        if not isinstance(result, dict):
            return
        signature = f"{tool_name}:{self._hash(tool_args)}"
        excerpt = json.dumps(result, ensure_ascii=False, default=str)
        if len(excerpt) > LAST_RESULT_EXCERPT_LIMIT:
            excerpt = excerpt[:LAST_RESULT_EXCERPT_LIMIT] + "…(截断)"
        self._last_results[signature] = excerpt
        if len(self._last_results) > LAST_RESULT_CACHE_SIZE:
            for key in list(self._last_results)[:-LAST_RESULT_CACHE_SIZE]:
                del self._last_results[key]

    def reset(self) -> None:
        """用户新输入/steering 后重置连击：明确指示下的重试不受罚。"""
        self._last_signature = None
        self._streak = 0

    def _build_warning(self, tool_name: str, repeated: int) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "tool_loop_warning",
            "severity": "warning",
            "summary": (
                f"WARNING: 工具 {tool_name} 已连续相同调用 {repeated} 次，重复执行不会产生新结果。"
                "请直接使用已有结果继续下一步；若结果不符合预期，请说明原因并更换参数或换用其他工具，不要原样重发。"
                f"{self._redirection_hint(tool_name)}"
            ),
            "loop_guard": True,
        }

    def _build_block(self, tool_name: str, repeated: int) -> Dict[str, Any]:
        last_result = self._last_results.get(self._last_signature or "")
        return {
            "success": False,
            "error": "tool_loop_detected",
            "severity": "block",
            "summary": (
                f"ERROR: 工具 {tool_name} 已连续相同调用 {repeated} 次，本次调用已拦截（相同参数不会再有新结果，原样重试同样会被拦截）。"
                "请勿重试本次调用，三选一：1) 直接使用 last_result_excerpt 附带的上次真实结果继续任务；"
                "2) 说明上次结果为何不可用，更换参数或换用其他工具；3) 向用户说明当前阻塞原因并等待指示。"
                f"{self._redirection_hint(tool_name)}"
            ),
            "last_result_excerpt": last_result,
            "loop_guard": True,
        }

    def _redirection_hint(self, tool_name: str) -> str:
        return self._REDIRECTION_HINTS.get(tool_name, "")

    def _hash(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
