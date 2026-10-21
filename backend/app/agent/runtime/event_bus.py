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

    def thought(
        self,
        state: RunState,
        thought: Any,
        text_content: str | None = None,
        will_use_tool: bool = False,
    ) -> Dict[str, Any]:
        data = {
            "iteration": state.iteration,
            "thought": thought,
            "session_id": state.session_id,
            "timestamp": datetime.now().isoformat(),
        }
        if text_content:
            data["text_content"] = text_content
        if will_use_tool:
            data["will_use_tool"] = True
        return {
            "type": "thought",
            "stream": "assistant",
            "data": data,
        }

    def thinking_content(self, state: RunState, content: str) -> Dict[str, Any]:
        return {
            "type": "thinking_content",
            "stream": "assistant",
            "data": {
                "content": content,
                "iteration": state.iteration,
                "session_id": state.session_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def steering_applied(
        self,
        state: RunState,
        messages: list[str],
        input_ids: list[str] | None = None,
        inputs: list[dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        return {
            "type": "steering_applied",
            "stream": "lifecycle",
            "data": {
                "messages": messages,
                "input_ids": input_ids or [],
                "inputs": inputs or [],
                "count": len(messages),
                "session_id": state.session_id,
                "run_id": state.run_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

    def steering_deferred(
        self,
        state: RunState,
        inputs: list[dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "type": "steering_deferred",
            "data": {
                "inputs": inputs,
                "count": len(inputs),
                "session_id": state.session_id,
                "run_id": state.run_id,
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
        file_path = self._extract_file_path(result.get("file_path") if isinstance(result, dict) else None)
        if file_path:
            data["file_path"] = file_path
        file_paths = self._extract_file_paths(result.get("file_paths") if isinstance(result, dict) else None)
        if file_paths:
            data["file_paths"] = file_paths
        report_file_path = self._extract_file_path(result.get("report_file_path") if isinstance(result, dict) else None)
        if report_file_path:
            data["report_file_path"] = report_file_path
        report_file_paths = self._extract_file_paths(result.get("report_file_paths") if isinstance(result, dict) else None)
        if report_file_paths:
            data["report_file_paths"] = report_file_paths
        return {
            "type": "tool_result",
            "stream": "tool",
            "data": data,
        }

    def interaction_required(
        self,
        state: RunState,
        interaction: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Pause the run while a user-facing interaction is pending."""
        return {
            "type": "interaction_required",
            "stream": "lifecycle",
            "data": {
                **interaction,
                "session_id": state.session_id,
                "run_id": state.run_id,
                "timestamp": datetime.now().isoformat(),
            },
        }

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

    def interrupted(self, state: RunState, reason: str = "用户已暂停本轮分析") -> Dict[str, Any]:
        return {
            "type": "interrupted",
            "stream": "error",
            "data": {
                "reason": reason,
                "session_id": state.session_id,
                "iteration": state.iteration,
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

    def _extract_file_path(self, value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    def _extract_file_paths(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        file_paths = []
        for item in value:
            file_path = self._extract_file_path(item)
            if file_path:
                file_paths.append(file_path)
        return file_paths
