"""Runtime event helpers with legacy event compatibility."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from .types import RunState


class RuntimeEventBus:
    """Builds events in the legacy shape currently consumed by callers."""

    def start(self, state: RunState) -> Dict[str, Any]:
        return {
            "type": "start",
            "stream": "lifecycle",
            "data": {
                "query": state.user_query,
                "session_id": state.session_id,
                "run_id": state.run_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def assistant_delta(self, state: RunState, chunk: str, is_complete: bool = False) -> Dict[str, Any]:
        return {
            "type": "streaming_text",
            "stream": "assistant",
            "data": {
                "chunk": chunk,
                "is_complete": is_complete,
                "timestamp": datetime.now().isoformat(),
            },
            "session_id": state.session_id,
            "run_id": state.run_id,
        }

    def thought(self, state: RunState, thought: Any) -> Dict[str, Any]:
        return {
            "type": "thought",
            "stream": "assistant",
            "data": {
                "iteration": state.iteration,
                "thought": thought,
                "session_id": state.session_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def tool_use(self, state: RunState, tool_use_id: str, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "tool_use",
            "stream": "tool",
            "data": {
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "input": tool_input,
                "iteration": state.iteration,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def tool_result(
        self,
        state: RunState,
        tool_use_id: str,
        result: Dict[str, Any],
        is_error: bool,
        tool_name: str | None = None,
    ) -> Dict[str, Any]:
        data = {
            "tool_use_id": tool_use_id,
            "result": result,
            "is_error": is_error,
            "iteration": state.iteration,
            "timestamp": datetime.now().isoformat(),
        }
        if tool_name:
            data["tool_name"] = tool_name
        data_id = self._extract_data_id(result.get("data_id") if isinstance(result, dict) else None)
        if data_id:
            data["data_id"] = data_id
        data_ids = self._extract_data_ids(result.get("data_ids") if isinstance(result, dict) else None)
        if data_ids:
            data["data_ids"] = data_ids
        return {
            "type": "tool_result",
            "stream": "tool",
            "data": data,
        }

    def result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"type": "result", "stream": "result", "data": data}

    def office_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"type": "office_document", "stream": "result", "data": data}

    def notebook_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"type": "notebook_document", "stream": "result", "data": data}

    def agent_finish(self, state: RunState, thought: Any = None) -> Dict[str, Any]:
        return {
            "type": "agent_finish",
            "stream": "final",
            "answer": state.response_text,
            "data": {
                "iterations": state.iteration,
                "session_id": state.session_id,
                "thought": thought,
            },
        }

    def complete(self, state: RunState, status: str = "completed", reason: str | None = None) -> Dict[str, Any]:
        """
        生成complete事件

        ⚠️ 重要：complete事件只返回文本答案，不包含visuals
        visuals应该从tool_result事件中获取，符合单一职责原则

        Args:
            state: 运行状态
            status: 完成状态（completed/incomplete）
            reason: 未完成原因

        Returns:
            complete事件字典
        """
        data = {
            "answer": state.response_text,
            "response": state.response_text,
            "iterations": state.iteration,
            "session_id": state.session_id,
            "run_id": state.run_id,
            "timestamp": datetime.now().isoformat(),
            # ✅ 保留sources字段（用于知识溯源）
            "sources": state.workflow_sources,
            # ❌ 移除visuals字段（应该从tool_result获取）
            # ❌ 移除direct_from_workflow字段（不需要）
        }
        if status != "completed":
            data["status"] = status
        if reason:
            data["reason"] = reason
        return {"type": "complete", "stream": "final", "data": data}

    def error(self, state: RunState, error: Exception) -> Dict[str, Any]:
        return {
            "type": "error",
            "stream": "error",
            "data": {
                "iteration": state.iteration,
                "error": str(error),
                "error_type": type(error).__name__,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def fatal_error(self, state: RunState, error: Exception) -> Dict[str, Any]:
        return {
            "type": "fatal_error",
            "stream": "error",
            "data": {
                "error": str(error),
                "error_type": type(error).__name__,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def _extract_data_id(self, value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("data_id")
            if isinstance(nested, str) and nested:
                return nested
        return None

    def _extract_data_ids(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        data_ids = []
        for item in value:
            data_id = self._extract_data_id(item)
            if data_id:
                data_ids.append(data_id)
        return data_ids
