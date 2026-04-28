"""Tool execution coordination for the runtime path."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import structlog

from .event_bus import RuntimeEventBus
from .tool_loop_guard import ToolLoopGuard
from .types import PlannerResult, RunState, ToolCall

logger = structlog.get_logger()


class ToolCoordinator:
    def __init__(
        self,
        tool_executor,
        knowledge_base_ids: list | None = None,
        loop_guard: ToolLoopGuard | None = None,
        schema_injector=None,
    ) -> None:
        self.executor = tool_executor
        self.knowledge_base_ids = knowledge_base_ids
        self.loop_guard = loop_guard or ToolLoopGuard()
        self.schema_injector = schema_injector
        self.events = RuntimeEventBus()

    def normalize_tool_input(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        if self.knowledge_base_ids and tool_name == "knowledge_qa_workflow":
            return {**(tool_input or {}), "knowledge_base_ids": self.knowledge_base_ids}
        return tool_input or {}

    async def execute_legacy_action(
        self,
        state: RunState,
        action: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Execute TOOL_CALL or TOOL_CALLS when no streaming executor was used."""
        action_type = action.get("type")
        tool_events: List[Dict[str, Any]] = []
        tool_records: List[Dict[str, Any]] = []

        if action_type == "TOOL_CALLS":
            tools = action.get("tools", [])
            for tool in tools:
                if tool.get("tool") == "knowledge_qa_workflow":
                    tool["args"] = self.normalize_tool_input(tool.get("tool", ""), tool.get("args", {}))
            parallel_result = await self.executor.execute_tools_parallel(tools=tools, iteration=state.iteration)
            observation = self._observation_from_parallel_result(parallel_result)
            for tool_result in observation.get("tool_results", []):
                result = tool_result.get("result", {})
                tool_events.append(self.events.tool_result(
                    state,
                    tool_result.get("tool_call_id", ""),
                    result,
                    not result.get("success", False) if isinstance(result, dict) else True,
                    tool_result.get("tool_name"),
                ))
            for tool in tools:
                result = {}
                is_error = False
                for item in observation.get("tool_results", []):
                    if item.get("tool_call_id") == tool.get("tool_call_id"):
                        result = item.get("result", {})
                        is_error = not result.get("success", False) if isinstance(result, dict) else True
                        break
                tool_records.append({
                    "tool_name": tool.get("tool", ""),
                    "tool_use_id": tool.get("tool_call_id", ""),
                    "tool_input": tool.get("args", {}),
                    "result": result,
                    "is_error": is_error,
                })
            return observation, tool_records, tool_events

        if action_type != "TOOL_CALL":
            return {"success": True, "summary": f"无需工具执行: {action_type}"}, [], []

        tool_name = action.get("tool", "")
        tool_args = self.normalize_tool_input(tool_name, action.get("args", {}))
        guarded = self.loop_guard.before_call(tool_name, tool_args)
        if guarded:
            observation = guarded
        elif action.get("tool_call_id"):
            observation = await self.executor.execute_tool_with_retry(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_call_id=action["tool_call_id"],
                iteration=state.iteration,
            )
        else:
            observation = await self.executor.execute_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                iteration=state.iteration,
            )
        self._inject_schema_if_needed(tool_name, observation)
        is_error = not observation.get("success", False)
        tool_call_id = action.get("tool_call_id", f"fallback_{tool_name}")
        tool_records.append({
            "tool_name": tool_name,
            "tool_use_id": tool_call_id,
            "tool_input": tool_args,
            "result": observation,
            "is_error": is_error,
        })
        tool_events.append(self.events.tool_result(state, tool_call_id, observation, is_error, tool_name))
        return observation, tool_records, tool_events

    def collect_streaming_results(self, state: RunState, streaming_tool_executor) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
        from ..core.streaming_tool_executor import ToolStatus

        all_results: List[Dict[str, Any]] = []
        all_visuals: List[Any] = []
        all_data_ids: List[Any] = []
        all_tool_results: List[Dict[str, Any]] = []
        tool_records: List[Dict[str, Any]] = []

        for execution in streaming_tool_executor._executions:
            if execution.status == ToolStatus.COMPLETED:
                result_data = execution.result or {}
            else:
                result_data = {
                    "success": False,
                    "error": execution.error or "工具执行被取消",
                    "summary": f"工具 {execution.tool_name} 执行失败",
                }

            guarded = self.loop_guard.before_call(execution.tool_name, execution.tool_input)
            if guarded and execution.status != ToolStatus.COMPLETED:
                result_data = guarded
            self._inject_schema_if_needed(execution.tool_name, result_data)

            is_error = execution.status in (ToolStatus.FAILED, ToolStatus.CANCELLED) or not result_data.get("success", False)
            tool_records.append({
                "tool_name": execution.tool_name,
                "tool_use_id": execution.tool_use_id,
                "tool_input": execution.tool_input,
                "result": result_data,
                "is_error": is_error,
            })
            all_results.append(result_data)
            all_tool_results.append({
                "tool_call_id": execution.tool_use_id,
                "tool_name": execution.tool_name,
                "result": result_data,
                "metadata": result_data.get("metadata", {}) if isinstance(result_data, dict) else {},
            })
            if isinstance(result_data, dict):
                if result_data.get("visuals"):
                    all_visuals.extend(result_data["visuals"])
                if result_data.get("data_id"):
                    all_data_ids.append(result_data["data_id"])

        if len(streaming_tool_executor._executions) == 1:
            execution = streaming_tool_executor._executions[0]
            observation = all_results[0] if all_results else {"success": False, "error": "无工具结果"}
            action = {
                "type": "TOOL_CALL",
                "tool": execution.tool_name,
                "tool_call_id": execution.tool_use_id,
                "args": execution.tool_input,
            }
            state.last_single_tool_result = {
                "observation": observation,
                "tool_name": execution.tool_name,
            }
            return observation, action, tool_records

        observation = {
            "success": any(r.get("success", False) for r in all_results if isinstance(r, dict)),
            "partial_success": any(r.get("success", False) for r in all_results if isinstance(r, dict))
            and not all(r.get("success", False) for r in all_results if isinstance(r, dict)),
            "data": [r.get("data") for r in all_results if isinstance(r, dict) and r.get("data")],
            "visuals": all_visuals,
            "data_ids": all_data_ids,
            "tool_results": all_tool_results,
            "summary": "; ".join(r.get("summary", "") for r in all_results if isinstance(r, dict) and r.get("summary")),
            "parallel": True,
            "success_count": sum(1 for r in all_results if isinstance(r, dict) and r.get("success", False)),
            "total_count": len(all_results),
        }
        action = {
            "type": "TOOL_CALLS",
            "tools": [
                {"tool": e.tool_name, "args": e.tool_input, "tool_call_id": e.tool_use_id}
                for e in streaming_tool_executor._executions
            ],
        }
        return observation, action, tool_records

    def _inject_schema_if_needed(self, tool_name: str, observation: Dict[str, Any]) -> None:
        if not self.schema_injector or not tool_name or not isinstance(observation, dict):
            return
        self.schema_injector.record_tool_result(tool_name, observation)
        if not self.schema_injector.should_inject_schema(tool_name):
            return
        schema_text = self.schema_injector.get_tool_schema(
            tool_name,
            self.executor.tool_registry if hasattr(self.executor, "tool_registry") else {},
        )
        if not schema_text:
            return
        observation["schema_injection"] = schema_text
        observation["schema_injection_notice"] = (
            f"你连续{self.schema_injector.consecutive_error_threshold}次调用工具{tool_name}失败。"
            "已自动注入该工具的完整schema，请仔细阅读参数要求后再试。"
        )

    def tool_calls_from_action(self, action: Dict[str, Any]) -> List[ToolCall]:
        if action.get("type") == "TOOL_CALLS":
            return [
                ToolCall(
                    tool_name=tool.get("tool", ""),
                    tool_input=tool.get("args", {}),
                    tool_call_id=tool.get("tool_call_id", ""),
                )
                for tool in action.get("tools", [])
            ]
        if action.get("type") == "TOOL_CALL":
            return [
                ToolCall(
                    tool_name=action.get("tool", ""),
                    tool_input=action.get("args", {}),
                    tool_call_id=action.get("tool_call_id", ""),
                )
            ]
        return []

    def _observation_from_parallel_result(self, parallel_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": parallel_result.get("success", False),
            "partial_success": parallel_result.get("partial_success", False),
            "data": parallel_result.get("data", []),
            "visuals": parallel_result.get("visuals", []),
            "data_ids": parallel_result.get("data_ids", []),
            "tool_results": parallel_result.get("tool_results", []),
            "summary": parallel_result.get("summary", "并行执行完成"),
            "parallel": True,
            "success_count": parallel_result.get("success_count", 0),
            "total_count": parallel_result.get("total_count", 0),
        }
