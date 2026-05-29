"""Tool no-progress loop detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolLoopGuard:
    warning_threshold: int = 3
    critical_threshold: int = 5
    soft_only_tools: frozenset[str] = frozenset({"snapshot", "status", "wait", "tabs"})
    hard_block_tools: frozenset[str] = frozenset({"navigate", "open", "act"})
    history: List[Dict[str, str]] = field(default_factory=list)

    def before_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any] | None:
        args_hash = self._hash(tool_args)
        repeated = self._count_recent(tool_name, args_hash)
        if repeated <= 1:
            self.history.append({"tool": tool_name, "args": args_hash})
            self.history = self.history[-50:]
            return None

        if tool_name in self.soft_only_tools:
            self._append_history(tool_name, args_hash)
            return self._build_warning(tool_name, repeated)

        if repeated >= self.critical_threshold or tool_name in self.hard_block_tools and repeated >= self.warning_threshold:
            return self._build_block(tool_name, repeated)

        if repeated >= self.warning_threshold:
            self._append_history(tool_name, args_hash)
            return self._build_warning(tool_name, repeated)

        self._append_history(tool_name, args_hash)
        return None

    def _append_history(self, tool_name: str, args_hash: str) -> None:
        self.history.append({"tool": tool_name, "args": args_hash})
        self.history = self.history[-50:]

    def _count_recent(self, tool_name: str, args_hash: str) -> int:
        return sum(
            1
            for item in self.history[-self.critical_threshold :]
            if item["tool"] == tool_name and item["args"] == args_hash
        )

    def _build_warning(self, tool_name: str, repeated: int) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "tool_loop_warning",
            "severity": "warning",
            "summary": f"WARNING: 工具 {tool_name} 重复调用 {repeated} 次，先提醒，不强制阻断。",
            "loop_guard": True,
        }

    def _build_block(self, tool_name: str, repeated: int) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "tool_loop_detected",
            "severity": "block",
            "summary": f"ERROR: 工具 {tool_name} 已重复调用 {repeated} 次，系统已阻止。",
            "loop_guard": True,
        }

    def _hash(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
