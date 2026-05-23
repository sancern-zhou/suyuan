"""Tool no-progress loop detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolLoopGuard:
    warning_threshold: int = 2  # 降低到2次
    critical_threshold: int = 3  # 降低到3次
    history: List[Dict[str, str]] = field(default_factory=list)

    def before_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any] | None:
        args_hash = self._hash(tool_args)
        repeated = sum(1 for item in self.history[-self.critical_threshold:] if item["tool"] == tool_name and item["args"] == args_hash)
        if repeated >= self.critical_threshold:
            return {
                "success": False,
                "error": "tool_loop_detected",
                "summary": f"ERROR: 工具 {tool_name} 已重复调用 {repeated} 次，系统已阻止。必须更换工具或修改参数。",
                "loop_guard": True,
            }
        if repeated >= self.warning_threshold:
            # 警告级别也返回失败，强制LLM改变策略
            return {
                "success": False,
                "error": "tool_loop_warning",
                "summary": f"WARNING: 工具 {tool_name} 重复调用 {repeated} 次，已被阻止。请使用其他工具或修改参数。",
                "loop_guard": True,
            }
        self.history.append({"tool": tool_name, "args": args_hash})
        self.history = self.history[-50:]
        return None

    def _hash(self, value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
