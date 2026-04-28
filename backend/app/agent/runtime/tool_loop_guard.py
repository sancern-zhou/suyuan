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
    history: List[Dict[str, str]] = field(default_factory=list)

    def before_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any] | None:
        args_hash = self._hash(tool_args)
        repeated = sum(1 for item in self.history[-self.critical_threshold:] if item["tool"] == tool_name and item["args"] == args_hash)
        if repeated >= self.critical_threshold:
            return {
                "success": False,
                "error": "tool_loop_detected",
                "summary": f"CRITICAL: 工具 {tool_name} 使用相同参数重复调用 {repeated} 次，已阻止继续调用以避免无进展循环。",
                "loop_guard": True,
            }
        if repeated >= self.warning_threshold:
            return {
                "success": False,
                "warning": True,
                "summary": f"WARNING: 工具 {tool_name} 使用相同参数重复调用 {repeated} 次。如果没有进展，请停止重试并报告失败。",
                "loop_guard": True,
            }
        self.history.append({"tool": tool_name, "args": args_hash})
        self.history = self.history[-50:]
        return None

    def _hash(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
