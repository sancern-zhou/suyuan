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

    def normalize_tool_input(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        mode: str | None = None,
        board_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        normalized = tool_input or {}
        if self.knowledge_base_ids and tool_name in {
            "knowledge_qa_workflow",
            "knowledge_graph_query",
        }:
            normalized = {**normalized, "knowledge_base_ids": self.knowledge_base_ids}
        normalized = self._inject_drawio_board_context(tool_name, normalized, mode, board_context)
        return normalized

    def prepare_tool_input_for_state(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        state: RunState,
    ) -> Tuple[Dict[str, Any], Dict[str, Any] | None]:
        if state.mode == "board":
            from app.agent.prompts.tool_registry import get_tools_by_mode

            allowed_tools = set(get_tools_by_mode("board"))
            if tool_name not in allowed_tools:
                return tool_input or {}, {
                    "status": "error",
                    "success": False,
                    "error": "tool_not_allowed_for_mode",
                    "data": {
                        "error_code": "tool_not_allowed_for_mode",
                        "tool_name": tool_name,
                        "allowed_tools": sorted(allowed_tools),
                        "retryable": True,
                    },
                    "summary": f"工具 {tool_name} 不在画板模式白名单中，请改用画板模式允许的工具。",
                }
        normalized = self.normalize_tool_input(
            tool_name,
            tool_input,
            mode=state.mode,
            board_context=state.board_context,
        )
        if state.mode == "board" and tool_name in {
            "create_drawio_board",
            "render_drawio_board_candidate",
            "accept_drawio_board_candidate",
        }:
            board_context = state.board_context if isinstance(state.board_context, dict) else {}
            normalized = {
                **normalized,
                "_session_id": state.session_id,
                "_agent_run_id": state.run_id,
                "_board_id": board_context.get("board_id") or board_context.get("active_board_id"),
            }
            if tool_name == "create_drawio_board":
                normalized["_base_revision"] = int(board_context.get("revision") or 0)
            elif tool_name == "accept_drawio_board_candidate":
                normalized["_expected_board_revision"] = int(board_context.get("revision") or 0)
        if self._is_drawio_edit_without_current_xml(tool_name, normalized, state.mode):
            return normalized, self._missing_drawio_current_xml_observation()
        return normalized, None

    def _inject_drawio_board_context(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        mode: str | None,
        board_context: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        if mode != "board" or tool_name != "create_drawio_board":
            return tool_input
        operation = str(tool_input.get("operation") or "create").strip().lower()
        if operation != "edit":
            return tool_input
        if not isinstance(board_context, dict):
            return {key: value for key, value in tool_input.items() if key not in {"current_xml", "currentXml"}}

        current_xml = (
            board_context.get("current_xml")
            or board_context.get("currentXml")
            or board_context.get("xml")
            or board_context.get("drawio_xml")
        )
        if not current_xml:
            return {key: value for key, value in tool_input.items() if key not in {"current_xml", "currentXml"}}

        selected_cells = (
            tool_input.get("selected_cells")
            or tool_input.get("selectedCells")
            or board_context.get("selected_cells")
            or board_context.get("selectedCells")
            or []
        )
        clean_input = {key: value for key, value in tool_input.items() if key not in {"current_xml", "currentXml"}}
        return {
            **clean_input,
            "current_xml": current_xml,
            "selected_cells": selected_cells,
        }

    def _is_drawio_edit_without_current_xml(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        mode: str | None,
    ) -> bool:
        if mode != "board" or tool_name != "create_drawio_board":
            return False
        operation = str(tool_input.get("operation") or "create").strip().lower()
        return operation == "edit" and not (tool_input.get("current_xml") or tool_input.get("currentXml"))

    def _missing_drawio_current_xml_observation(self) -> Dict[str, Any]:
        return {
            "status": "error",
            "success": False,
            "error": "missing_current_xml_for_edit",
            "metadata": {"tool_name": "create_drawio_board"},
            "summary": "当前请求没有可编辑画板 current_xml，无法执行局部编辑。",
        }

    def _tag_board_tool_result(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name != "create_drawio_board" or not isinstance(result, dict):
            return result
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        result["metadata"] = {**metadata, "tool_name": "create_drawio_board"}
        return result

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
                tool["args"], preparation_error = self.prepare_tool_input_for_state(
                    tool.get("tool", ""),
                    tool.get("args", {}),
                    state,
                )
                if preparation_error is not None:
                    tool_call_id = tool.get("tool_call_id", f"fallback_{tool.get('tool', '')}")
                    tool_records.append({
                        "tool_name": tool.get("tool", ""),
                        "tool_use_id": tool_call_id,
                        "tool_input": tool.get("args", {}),
                        "result": preparation_error,
                        "is_error": True,
                    })
                    tool_events.append(self.events.tool_result(
                        state, tool_call_id, preparation_error, True, tool.get("tool", "")
                    ))
                    return preparation_error, tool_records, tool_events

            # ⚠️ 方案A：检测并发的 call_sub_agent 调用，强制 session 隔离
            sub_agent_tools = [t for t in tools if t.get("tool") == "call_sub_agent"]
            if len(sub_agent_tools) > 1:
                logger.info(
                    "concurrent_sub_agent_calls_detected",
                    count=len(sub_agent_tools),
                    action="force_isolated_sessions"
                )
                # 为每个 call_sub_agent 添加隔离标记
                for tool in sub_agent_tools:
                    if not tool.get("args"):
                        tool["args"] = {}
                    tool["args"]["_force_isolated_session"] = True

            parallel_result = await self.executor.execute_tools_parallel(tools=tools, iteration=state.iteration)
            parallel_result = self._normalize_parallel_tool_results(parallel_result, tools)
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
        tool_args, preparation_error = self.prepare_tool_input_for_state(tool_name, action.get("args", {}), state)
        if preparation_error is not None:
            tool_call_id = action.get("tool_call_id", f"fallback_{tool_name}")
            tool_records.append({
                "tool_name": tool_name,
                "tool_use_id": tool_call_id,
                "tool_input": tool_args,
                "result": preparation_error,
                "is_error": True,
            })
            tool_events.append(self.events.tool_result(state, tool_call_id, preparation_error, True, tool_name))
            return preparation_error, tool_records, tool_events
        guarded = self.loop_guard.before_call(tool_name, tool_args)
        if guarded and guarded.get("severity") == "block":
            observation = guarded
        elif guarded:
            logger.warning(
                "tool_loop_guard_warning",
                tool_name=tool_name,
                summary=guarded.get("summary") if isinstance(guarded, dict) else None,
            )
            observation = await self.executor.execute_tool_with_retry(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_call_id=action.get("tool_call_id", f"fallback_{tool_name}"),
                iteration=state.iteration,
            ) if action.get("tool_call_id") else await self.executor.execute_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                iteration=state.iteration,
            )
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
        observation = self._tag_board_tool_result(tool_name, observation)
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
        all_report_data_ids: List[Any] = []
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

            result_data = self._tag_board_tool_result(execution.tool_name, result_data)

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
                if result_data.get("report_data_id"):
                    all_report_data_ids.append(result_data["report_data_id"])

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
            "report_data_ids": all_report_data_ids,
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
            "report_data_ids": parallel_result.get("report_data_ids", []),
            "tool_results": parallel_result.get("tool_results", []),
            "summary": parallel_result.get("summary", "并行执行完成"),
            "parallel": True,
            "success_count": parallel_result.get("success_count", 0),
            "total_count": parallel_result.get("total_count", 0),
        }

    def _normalize_parallel_tool_results(
        self,
        parallel_result: Dict[str, Any],
        requested_tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Preserve tool identity for both successful and failed legacy parallel calls."""
        raw_results = list(parallel_result.get("tool_results") or [])
        raw_results.extend(parallel_result.get("failed_tools") or [])
        normalized_results: List[Dict[str, Any]] = []
        unused_indices = list(range(len(requested_tools)))

        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            tool_name = raw.get("tool_name") or raw.get("tool") or ""
            match_index = next(
                (
                    index for index in unused_indices
                    if requested_tools[index].get("tool") == tool_name
                ),
                None,
            )
            requested = requested_tools[match_index] if match_index is not None else {}
            if match_index is not None:
                unused_indices.remove(match_index)

            result = raw.get("result") if isinstance(raw.get("result"), dict) else None
            if result is None:
                result = {
                    "success": bool(raw.get("success", False)),
                    "error": raw.get("error") or "parallel_tool_failed",
                    "summary": raw.get("summary") or f"工具 {tool_name} 执行失败",
                }
            result = self._tag_board_tool_result(tool_name, result)
            normalized_results.append({
                "tool_call_id": raw.get("tool_call_id") or requested.get("tool_call_id", ""),
                "tool_name": tool_name,
                "result": result,
                "metadata": result.get("metadata", {}),
            })

        return {**parallel_result, "tool_results": normalized_results}
