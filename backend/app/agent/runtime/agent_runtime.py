"""Decomposed ReAct runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

from .assistant_stream_buffer import AssistantStreamBuffer
from .conversation_writer import ConversationWriter
from .event_bus import RuntimeEventBus
from .finalizer import Finalizer
from .observation_processor import ObservationProcessor
from .session_queue import SessionRunQueue
from .tool_coordinator import ToolCoordinator
from .tool_classification import HOUSEKEEPING_TOOL_NAMES, all_housekeeping_tools
from .transcript_repairer import TranscriptRepairer
from .types import PlannerResult, RunState, ToolCall
from .cancellation import AgentRunCancelled, cancellation_registry
from .mode_capabilities import supports_native_multimodal
from .ownership import run_ownership_registry
from .steering import steering_registry
from ..context.context_diagnostics import ContextDiagnostics

logger = structlog.get_logger()


class CustomAgentTerminalError(RuntimeError):
    """A custom scheduled Agent reached a non-retryable terminal failure."""


@dataclass
class AgentRuntimeConfig:
    memory_manager: Any
    planner: Any
    tool_executor: Any
    context_builder: Any
    max_iterations: int = 120
    enhance_with_history: bool = True
    enable_reasoning: bool = False
    is_interruption: bool = False
    knowledge_base_ids: Optional[list] = None
    agent_logger: Any = None
    schema_injector: Any = None
    cancel_event: Optional[asyncio.Event] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    auto_profile: Optional[str] = None
    runtime_mode: Optional[str] = None
    user_identifier: Optional[str] = None
    board_context: Optional[Dict[str, Any]] = None


class AgentRuntime:
    """Runtime implementation with explicit finalization and transcript writes."""

    def __init__(self, config: AgentRuntimeConfig) -> None:
        self.config = config
        self.memory = config.memory_manager
        self.planner = config.planner
        self.executor = config.tool_executor
        self.context_builder = config.context_builder
        self.events = RuntimeEventBus()
        self.writer = ConversationWriter(self.memory)
        self.finalizer = Finalizer(self.writer, self.events, agent_logger=config.agent_logger)
        self.tool_coordinator = ToolCoordinator(
            self.executor,
            knowledge_base_ids=config.knowledge_base_ids,
            schema_injector=config.schema_injector,
        )
        self.observation_processor = ObservationProcessor(self.finalizer, self.events, memory_manager=self.memory)
        self.transcript_repairer = TranscriptRepairer()
        self.session_queue = SessionRunQueue()
        self.context_diagnostics = ContextDiagnostics()

    async def run(
        self,
        user_query: str,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
        mode: str = "expert",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        state = RunState(
            session_id=self.memory.session_id,
            user_query=user_query,
            mode=mode,
            enhance_with_history=self.config.enhance_with_history,
            board_context=self.config.board_context,
        )
        self.executor.resource_run_id = state.run_id

        await run_ownership_registry.register(state.session_id, state.run_id)
        await steering_registry.register(state.session_id, state.run_id, state.mode)
        try:
            async for event in self._run_locked(state, initial_messages):
                yield self._with_run_identity(state, event)
        finally:
            await steering_registry.unregister(state.session_id, state.run_id)

    def _with_run_identity(self, state: RunState, event: Dict[str, Any]) -> Dict[str, Any]:
        event.setdefault("session_id", state.session_id)
        event.setdefault("run_id", state.run_id)
        data = event.setdefault("data", {})
        if isinstance(data, dict):
            data.setdefault("session_id", state.session_id)
            data.setdefault("run_id", state.run_id)
        return event

    async def _run_locked(
        self,
        state: RunState,
        initial_messages: Optional[List[Dict[str, Any]]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        deterministic_error_count = 0
        try:
            if self.config.agent_logger:
                run_id = self.config.agent_logger.start_new_run(
                    session_id=state.session_id,
                    query=state.user_query,
                    metadata={
                        "enhance_with_history": state.enhance_with_history,
                        "runtime": "decomposed",
                        "runtime_mode": self.config.runtime_mode or state.mode,
                        "user_identifier": self.config.user_identifier,
                    },
                )
                logger.info("agent_runtime_run_started", run_id=run_id)

            self.planner.is_interruption = self.config.is_interruption
            self.writer.load_initial_history_if_needed(initial_messages)

            yield self.events.start(state)

            while state.iteration < self.config.max_iterations and not state.task_completed:
                self._raise_if_cancelled()
                state.iteration += 1
                try:
                    async for event in self._apply_steering_inputs(state):
                        yield event
                    async for event in self._run_iteration(state):
                        self._raise_if_cancelled()
                        yield event
                    deterministic_error_count = 0
                except AgentRunCancelled:
                    self._ensure_user_message_written(state)
                    deferred_event = await self._close_steering_event(state)
                    if deferred_event:
                        yield deferred_event
                    yield self.events.interrupted(state)
                    return
                except Exception as exc:
                    logger.error(
                        "agent_runtime_iteration_failed",
                        iteration=state.iteration,
                        error=str(exc),
                        error_type=type(exc).__name__,
                        exc_info=True,
                    )
                    yield self.events.error(state, exc)
                    if self._is_terminal_quota_error(exc):
                        terminal_error = RuntimeError(f"模型额度已耗尽，运行已停止，避免无效重试：{exc}")
                        self._ensure_user_message_written(state)
                        deferred_event = await self._close_steering_event(state)
                        if deferred_event:
                            yield deferred_event
                        async for event in self.finalizer.fatal_error(state, terminal_error):
                            yield event
                        return
                    if state.mode == "custom" and isinstance(exc, CustomAgentTerminalError):
                        self._ensure_user_message_written(state)
                        deferred_event = await self._close_steering_event(state)
                        if deferred_event:
                            yield deferred_event
                        async for event in self.finalizer.fatal_error(state, exc):
                            yield event
                        return
                    if self._is_deterministic_model_error(exc):
                        deterministic_error_count += 1
                        if deterministic_error_count >= 2:
                            prefix = "custom Agent" if state.mode == "custom" else f"{state.mode} Agent"
                            error_type = CustomAgentTerminalError if state.mode == "custom" else RuntimeError
                            terminal_error = error_type(f"{prefix} 模型请求连续失败，已熔断: {exc}")
                            self._ensure_user_message_written(state)
                            deferred_event = await self._close_steering_event(state)
                            if deferred_event:
                                yield deferred_event
                            async for event in self.finalizer.fatal_error(state, terminal_error):
                                yield event
                            return
                    else:
                        deterministic_error_count = 0
                    if "fatal" in str(exc).lower():
                        break

            if not state.task_completed:
                self._ensure_user_message_written(state)
                deferred_event = await self._close_steering_event(state)
                if deferred_event:
                    yield deferred_event
                if state.mode == "custom":
                    error = CustomAgentTerminalError(
                        f"custom Agent 在 {state.iteration} 次迭代内未形成成功或失败终态"
                    )
                    async for event in self.finalizer.fatal_error(state, error):
                        yield event
                else:
                    async for event in self.finalizer.timeout(state):
                        yield event

        except Exception as exc:
            if isinstance(exc, AgentRunCancelled):
                self._ensure_user_message_written(state)
                deferred_event = await self._close_steering_event(state)
                if deferred_event:
                    yield deferred_event
                yield self.events.interrupted(state)
                return
            logger.error("agent_runtime_fatal_error", error=str(exc), exc_info=True)
            self._ensure_user_message_written(state)
            deferred_event = await self._close_steering_event(state)
            if deferred_event:
                yield deferred_event
            async for event in self.finalizer.fatal_error(state, exc):
                yield event

    async def _run_iteration(self, state: RunState) -> AsyncGenerator[Dict[str, Any], None]:
        context_result, conversation_history = await self._build_context(state)
        attachments = self._effective_attachments(state)
        if supports_native_multimodal(state.mode) and attachments:
            from .multimodal import build_anthropic_user_content, build_persisted_user_content

            state.user_message_content = build_anthropic_user_content(
                state.user_query,
                attachments,
            )
            state.persisted_user_message_content = build_persisted_user_content(
                state.user_query,
                attachments,
            )
        elif supports_native_multimodal(state.mode):
            state.user_message_content = None
        self._raise_if_cancelled()
        planner_result = None
        streaming_tool_executor = None
        async for event in self._run_planner_stream(state, context_result, conversation_history):
            self._raise_if_cancelled()
            if event.get("type") == "_planner_done":
                planner_result = event["planner_result"]
                streaming_tool_executor = event["streaming_tool_executor"]
            else:
                yield event

        if planner_result is None or streaming_tool_executor is None:
            raise RuntimeError("Planner stream ended without a result")

        action = planner_result.action or {"type": "ERROR", "error": "no action"}
        action_type = action.get("type", "ERROR")

        if streaming_tool_executor.total_count > 0 and action_type in ("TOOL_CALL", "TOOL_CALLS"):
            async for event in self._handle_streamed_tools(state, planner_result, streaming_tool_executor):
                self._raise_if_cancelled()
                yield event
            return

        if action_type == "PLAIN_TEXT_REPLY" and planner_result.streamed_assistant_text:
            state.response_streamed = True

        for event in planner_result.pop_events:
            yield event

        if action_type == "PLAIN_TEXT_REPLY":
            async for event in self._complete_response(state, planner_result, action.get("answer", "")):
                yield event
            return

        if action_type in ("TOOL_CALL", "TOOL_CALLS"):
            self._raise_if_cancelled()
            suppressed_observation = self._suppressed_housekeeping_observation(state, action)
            if suppressed_observation is not None:
                tool_call_id = action.get("tool_call_id", f"fallback_{action.get('tool', '')}")
                tool_name = action.get("tool", "")
                observation = suppressed_observation
                records = [{
                    "tool_name": tool_name,
                    "tool_use_id": tool_call_id,
                    "tool_input": action.get("args", {}),
                    "result": observation,
                    "is_error": False,
                }]
                tool_events = [self.events.tool_result(state, tool_call_id, observation, False, tool_name)]
            else:
                observation, records, tool_events = await self.tool_coordinator.execute_legacy_action(state, action)
            self._capture_multimodal_attachments(state, observation)
            self._capture_drawio_board_context(state, observation)
            self._apply_housekeeping_policy(state, action, observation)
            self._ensure_user_message_written(state)
            self.writer.add_tool_exchange(records, planner_result)
            self.writer.add_iteration(planner_result.thought, action, observation)
            self._enforce_custom_tool_terminal_rules(state, action, records)
            for event in tool_events:
                yield event
            async for event in self.observation_processor.process(state, planner_result, action, observation):
                yield event
            return

        observation = {
            "success": False,
            "error": f"Unknown action type: {action_type}",
            "summary": "任务失败：未知的 action type",
        }
        self._ensure_user_message_written(state)
        self.writer.add_iteration(planner_result.thought, action, observation)

    def _effective_attachments(self, state: RunState) -> List[Dict[str, Any]]:
        """Current-run image attachments available to native multimodal calls."""
        attachments: List[Dict[str, Any]] = []
        if (
            self.config.attachments
            and not state.initial_attachments_consumed
            and not self._should_suppress_initial_attachments(state)
        ):
            attachments.extend(self.config.attachments)
        if state.pending_attachments:
            attachments.extend(state.pending_attachments)
        return attachments

    def _consume_effective_attachments(self, state: RunState) -> None:
        for attachment in self._effective_attachments(state):
            key = self._attachment_key(attachment)
            if key:
                state.consumed_attachment_keys.add(key)
        if (
            self.config.attachments
            and not state.initial_attachments_consumed
            and not self._should_suppress_initial_attachments(state)
        ):
            state.initial_attachments_consumed = True
        if state.pending_attachments:
            state.pending_attachments.clear()

    def _consume_pending_attachments(self, state: RunState) -> None:
        for attachment in state.pending_attachments:
            key = self._attachment_key(attachment)
            if key:
                state.consumed_attachment_keys.add(key)
        state.pending_attachments.clear()

    def _should_consume_initial_attachments_after_planner(self, state: RunState) -> bool:
        if state.mode == "board":
            return False
        return True

    @staticmethod
    def _planner_action_tool_calls(action: Optional[Dict[str, Any]]) -> List[tuple[str, Dict[str, Any]]]:
        """Return normalized tool calls from either planner action shape."""
        if not isinstance(action, dict):
            return []
        if action.get("type") == "TOOL_CALL":
            return [(str(action.get("tool") or ""), action.get("args") or {})]
        if action.get("type") == "TOOL_CALLS":
            return [
                (str(item.get("tool") or ""), item.get("args") or {})
                for item in action.get("tools") or []
                if isinstance(item, dict)
            ]
        return []

    @classmethod
    def _action_materializes_visual_output(cls, action: Optional[Dict[str, Any]]) -> bool:
        """Whether the planner has reached a visual generation/edit checkpoint.

        Reference images remain attached while the Agent is only reading
        instructions or inspecting files.  Consuming them at those calls caused
        later PPT/chart generation to run from memory instead of pixels.
        """
        visual_tools = {
            "create_pptx_with_ppt_master",
            "create_report_chart",
            "create_drawio_board",
            "render_drawio_board_candidate",
            "edit_file",
            "write_file",
        }
        visual_ppt_operations = {
            "edit_source",
            "edit_sources",
        }
        for tool_name, args in cls._planner_action_tool_calls(action):
            if tool_name in visual_tools:
                return True
            if tool_name == "manage_editable_ppt" and str(args.get("operation") or "") in visual_ppt_operations:
                return True
        return False

    def _consume_initial_attachments_after_drawio_board_created(self, state: RunState) -> None:
        attachments = getattr(getattr(self, "config", None), "attachments", None)
        if not attachments or state.initial_attachments_consumed:
            return
        for attachment in attachments:
            key = self._attachment_key(attachment)
            if key:
                state.consumed_attachment_keys.add(key)
        state.initial_attachments_consumed = True

    def _consume_sent_attachments_after_planner(
        self,
        state: RunState,
        action: Optional[Dict[str, Any]] = None,
    ) -> None:
        if state.mode in {"ppt", "chart"} and not self._action_materializes_visual_output(action):
            logger.info(
                "multimodal_attachments_retained_for_visual_materialization",
                session_id=state.session_id,
                run_id=state.run_id,
                iteration=state.iteration,
                mode=state.mode,
                attachment_count=len(self._effective_attachments(state)),
                planner_tools=[name for name, _ in self._planner_action_tool_calls(action)],
            )
            return
        logger.info(
            "multimodal_attachments_consumed_at_planner_checkpoint",
            session_id=state.session_id,
            run_id=state.run_id,
            iteration=state.iteration,
            mode=state.mode,
            attachment_count=len(self._effective_attachments(state)),
            planner_tools=[name for name, _ in self._planner_action_tool_calls(action)],
        )
        if state.pending_attachments:
            self._consume_pending_attachments(state)
        if self._should_consume_initial_attachments_after_planner(state):
            self._consume_effective_attachments(state)

    def _should_suppress_initial_attachments(self, state: RunState) -> bool:
        # Explicit current-turn uploads are never filtered because of restored
        # state. Images are consumed only after they have actually been sent.
        return False

    def _capture_multimodal_attachments(self, state: RunState, observation: Dict[str, Any]) -> None:
        if not supports_native_multimodal(state.mode) or not isinstance(observation, dict):
            return

        from .multimodal import extract_multimodal_attachments

        attachments = extract_multimodal_attachments(observation)
        if not attachments:
            return

        known_keys = {
            key
            for key in (self._attachment_key(item) for item in state.pending_attachments)
            if key
        }
        filtered_attachments: List[Dict[str, Any]] = []
        for attachment in attachments:
            key = self._attachment_key(attachment)
            # A new explicit read_file(..., as_multimodal_attachment=true)
            # request is allowed to re-open a previously consumed image.  Only
            # suppress duplicates already waiting for the next planner call.
            if key and key in known_keys:
                continue
            filtered_attachments.append(attachment)
            if key:
                known_keys.add(key)

        if not filtered_attachments:
            return

        state.pending_attachments.extend(filtered_attachments)
        logger.info(
            "multimodal_attachments_captured_from_tool",
            session_id=state.session_id,
            run_id=state.run_id,
            iteration=state.iteration,
            count=len(filtered_attachments),
            names=[item.get("name") for item in filtered_attachments if isinstance(item, dict)],
        )

    @staticmethod
    def _attachment_key(attachment: Dict[str, Any]) -> Optional[str]:
        if not isinstance(attachment, dict):
            return None
        for field in ("local_path", "path", "url"):
            value = attachment.get(field)
            if isinstance(value, str) and value:
                return f"{field}:{value}"
        name = attachment.get("name")
        if isinstance(name, str) and name:
            return f"name:{name}"
        return None

    def _capture_drawio_board_context(self, state: RunState, observation: Dict[str, Any]) -> None:
        if state.mode != "board" or not isinstance(observation, dict):
            return

        for result in self._iter_drawio_observation_results(observation):
            data = result.get("data")
            if not isinstance(data, dict):
                continue
            xml = self._drawio_xml_from_result(result)
            if not xml:
                continue
            if data.get("artifact_kind") != "drawio_board":
                metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
                if metadata.get("tool_name") != "create_drawio_board":
                    continue

            previous = state.board_context if isinstance(state.board_context, dict) else {}
            candidate_version_id = data.get("candidate_version_id")
            candidate_accepted = bool(data.get("candidate_accepted"))
            previous_candidate_id = previous.get("candidate_version_id")
            if candidate_version_id and previous_candidate_id and candidate_version_id != previous_candidate_id:
                state.board_quality_repair_count += 1
            if data.get("requires_visual_review") and candidate_version_id:
                state.pending_board_candidate_id = str(candidate_version_id)
            elif candidate_accepted or data.get("lifecycle_status") == "rejected":
                state.pending_board_candidate_id = None
            state.board_context = {
                **previous,
                "current_xml": xml,
                "xml": xml,
                "artifact_id": data.get("artifact_id") or previous.get("artifact_id"),
                "board_id": data.get("board_id") or previous.get("board_id"),
                "title": data.get("title") or previous.get("title"),
                "revision": data.get("revision", previous.get("revision", 0)),
                "candidate_version_id": candidate_version_id or previous.get("candidate_version_id"),
                "current_version_id": data.get("current_version_id") or previous.get("current_version_id"),
                "version_id": data.get("version_id") or previous.get("version_id"),
                "quality_status": data.get("quality_status") or previous.get("quality_status"),
                "quality_report": data.get("quality_report") or previous.get("quality_report"),
                "design_spec": data.get("design_spec") or previous.get("design_spec"),
                "theme_tokens": data.get("theme_tokens") or previous.get("theme_tokens"),
                "structural_digest": data.get("structural_digest") or previous.get("structural_digest"),
                "render_status": data.get("render_status") or previous.get("render_status"),
                "lifecycle_status": data.get("lifecycle_status") or previous.get("lifecycle_status"),
                "screenshot_ref": data.get("screenshot_ref") or previous.get("screenshot_ref"),
                "requires_visual_review": bool(data.get("requires_visual_review", False)),
            }
            state.board_context_updated_in_run = True
            self._consume_initial_attachments_after_drawio_board_created(state)
            context_builder = getattr(getattr(self, "config", None), "context_builder", None)
            if context_builder is not None:
                context_builder.board_context = state.board_context
            logger.info(
                "drawio_board_context_captured_from_tool_result",
                session_id=state.session_id,
                run_id=state.run_id,
                iteration=state.iteration,
                artifact_id=state.board_context.get("artifact_id"),
                title=state.board_context.get("title"),
                xml_chars=len(str(xml)),
            )

    @staticmethod
    def _drawio_xml_from_result(result: Dict[str, Any]) -> str:
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        for field in ("current_xml", "currentXml", "xml", "drawio_xml", "mxfile"):
            value = data.get(field)
            if isinstance(value, str) and value:
                return value

        candidate_refs: List[Dict[str, Any]] = []
        xml_ref = data.get("xml_ref")
        if isinstance(xml_ref, dict):
            candidate_refs.append(xml_ref)
        refs = result.get("refs") if isinstance(result.get("refs"), dict) else {}
        artifacts = refs.get("artifacts") if isinstance(refs.get("artifacts"), list) else []
        candidate_refs.extend(item for item in artifacts if isinstance(item, dict))

        for ref in candidate_refs:
            path_value = ref.get("local_path") or ref.get("path") or ref.get("file_path")
            if not isinstance(path_value, str) or not path_value:
                continue
            try:
                path = Path(path_value).expanduser().resolve()
                if path.is_file():
                    return path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning(
                    "drawio_board_xml_ref_read_failed",
                    path=path_value,
                    error=str(exc),
                )
        return ""

    def _iter_drawio_observation_results(self, observation: Dict[str, Any]):
        yield observation
        tool_results = observation.get("tool_results")
        if not isinstance(tool_results, list):
            return
        for item in tool_results:
            if not isinstance(item, dict):
                continue
            result = item.get("result", item)
            if isinstance(result, dict):
                yield result

    async def _apply_steering_inputs(
        self,
        state: RunState,
        *,
        completion_boundary: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if completion_boundary:
            items = await steering_registry.begin_completion(state.session_id, state.run_id)
        else:
            items = await steering_registry.drain(state.session_id, state.run_id)
        if not items:
            return

        self._ensure_user_message_written(state)
        messages: List[str] = []
        input_ids: List[str] = []
        applied_inputs: List[Dict[str, Any]] = []
        attachment_count = 0
        for item in items:
            content = item.content
            safe_attachments: List[Dict[str, str]] = []
            if item.attachments:
                state.pending_attachments.extend(item.attachments)
                attachment_count += len(item.attachments)
                safe_attachments = self._resource_attachment_refs(item.attachments)
                content = self._append_attachment_summary(content, item.attachments)
            messages.append(content)
            input_ids.append(item.input_id)
            applied_inputs.append({
                "message": item.content,
                "input_id": item.input_id,
                "attachments": safe_attachments,
            })
            self.writer.add_user_message(f"【执行中用户补充】{content}")

        logger.info(
            "steering_inputs_applied",
            session_id=state.session_id,
            run_id=state.run_id,
            count=len(messages),
            attachment_count=attachment_count,
        )
        yield self.events.steering_applied(state, messages, input_ids, applied_inputs)

    async def _close_steering(self, state: RunState) -> List[Any]:
        deferred = await steering_registry.close_and_drain(state.session_id, state.run_id)
        if deferred:
            logger.info(
                "steering_inputs_deferred_by_terminal_event",
                session_id=state.session_id,
                run_id=state.run_id,
                count=len(deferred),
                input_ids=[item.input_id for item in deferred],
            )
        return deferred

    async def _close_steering_event(
        self,
        state: RunState,
    ) -> Dict[str, Any] | None:
        deferred = await self._close_steering(state)
        if not deferred:
            return None
        inputs = [
            {
                "message": item.content,
                "input_id": item.input_id,
                "attachments": self._resource_attachment_refs(item.attachments),
            }
            for item in deferred
        ]
        return self.events.steering_deferred(state, inputs)

    @staticmethod
    def _append_attachment_summary(content: str, attachments: List[Dict[str, Any]]) -> str:
        if not attachments:
            return content

        lines = ["", "", "**用户上传的附件**："]
        for index, attachment in enumerate(attachments, 1):
            att_type = attachment.get("type") or "file"
            att_name = attachment.get("name") or "attachment"
            resource_id = attachment.get("resource_id") or attachment.get("ref_id")
            att_mime_type = attachment.get("mime_type") or attachment.get("content_type")
            label = "图片" if att_type == "image" else "文件"
            lines.append(f"{index}. {label}: {att_name}")
            if resource_id:
                lines.append(f"   会话资源: {resource_id}")
            if att_mime_type:
                lines.append(f"   类型: {att_mime_type}")

        return f"{content}{chr(10).join(lines)}"

    @staticmethod
    def _resource_attachment_refs(
        attachments: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        refs: List[Dict[str, str]] = []
        for attachment in attachments:
            resource_id = str(
                attachment.get("resource_id") or attachment.get("ref_id") or ""
            )
            if not resource_id:
                continue
            refs.append({
                "type": str(attachment.get("type") or "file"),
                "name": str(attachment.get("name") or "attachment"),
                "mime_type": str(
                    attachment.get("mime_type")
                    or attachment.get("content_type")
                    or "application/octet-stream"
                ),
                "resource_id": resource_id,
                "ref_id": resource_id,
            })
        return refs

    async def _build_context(self, state: RunState) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        latest_observation = ""
        if state.last_observation:
            latest_observation = self._format_observation(state.last_observation)

        conversation_history = self.memory.session.get_messages_for_llm()
        context_result = await self.context_builder.build_for_thought_action(
            query=state.user_query,
            iteration=state.iteration,
            latest_observation=latest_observation,
            conversation_history=conversation_history,
            mode=state.mode,
            is_interruption=self.config.is_interruption if state.iteration == 1 else False,
        )
        conversation_history = self.memory.session.get_messages_for_llm()
        conversation_history = self.transcript_repairer.repair(conversation_history)
        return context_result, conversation_history

    async def _run_planner_stream(
        self,
        state: RunState,
        context_result: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        from app.agent.tool_adapter import get_tool_schemas
        from ..core.streaming_tool_executor import StreamingToolExecutor

        # 按模式过滤工具 schema（节省 token）
        tool_schemas = get_tool_schemas(
            mode=state.mode,
            allowed_tool_names=(
                list(self.executor.tool_registry.keys())
                if state.mode == "custom" and hasattr(self.executor, "tool_registry")
                else None
            ),
        )
        suppressed_tool_names = self._tool_names_to_suppress(state)
        state.suppress_tool_names_current_turn = suppressed_tool_names
        if suppressed_tool_names:
            original_count = len(tool_schemas)
            tool_schemas = [
                tool for tool in tool_schemas
                if (tool.get("name") or tool.get("function", {}).get("name")) not in suppressed_tool_names
            ]
            logger.info(
                "tool_schemas_suppressed_by_runtime_policy",
                iteration=state.iteration,
                suppressed_tools=sorted(suppressed_tool_names),
                original_tool_count=original_count,
                filtered_tool_count=len(tool_schemas),
            )
        tool_schema_chars = len(json.dumps(tool_schemas, ensure_ascii=False, default=str))
        tool_schema_tokens_est = int(tool_schema_chars / 1.5)
        context_tokens = context_result.get("tokens", {})
        logger.info(
            "planner_context_with_tools",
            mode=state.mode,
            iteration=state.iteration,
            tool_count=len(tool_schemas),
            tool_schema_chars=tool_schema_chars,
            tool_schema_tokens_est=tool_schema_tokens_est,
            system_tokens=context_tokens.get("system"),
            user_tokens=context_tokens.get("user"),
            history_tokens=context_tokens.get("history"),
            total_without_tools=context_tokens.get("total"),
            total_with_tools_est=(context_tokens.get("total") or 0) + tool_schema_tokens_est,
        )
        self.context_diagnostics.log_report(
            mode=state.mode,
            iteration=state.iteration,
            context_tokens=context_tokens,
            tool_schemas=tool_schemas,
            conversation_history=conversation_history,
            context_layers=context_result.get("context_layers"),
        )
        streaming_tool_executor = StreamingToolExecutor(
            tool_executor=self.executor,
            tool_registry=self.executor.tool_registry if hasattr(self.executor, "tool_registry") else {},
            loop_guard=self.tool_coordinator.loop_guard,
        )
        await cancellation_registry.attach_streaming_executor(state.session_id, streaming_tool_executor)
        buffer = AssistantStreamBuffer()
        planner_result = PlannerResult()
        user_content = None
        attachments = self._effective_attachments(state)
        if supports_native_multimodal(state.mode) and attachments:
            from .multimodal import build_anthropic_user_content

            user_content = build_anthropic_user_content(
                context_result["user_conversation"],
                attachments,
            )

        async for event in self.planner.think_and_action_streaming(
            query=state.user_query,
            system_prompt=context_result.get("system_prompt_blocks") or context_result["system_prompt"],
            user_conversation=context_result["user_conversation"],
            tools=tool_schemas,
            iteration=state.iteration,
            mode=state.mode,
            conversation_history=conversation_history,
            user_content=user_content,
            attachments=attachments,
            llm_provider=self.config.llm_provider,
            llm_model=self.config.llm_model,
            auto_profile=self.config.auto_profile,
        ):
            self._raise_if_cancelled()
            event_type = event["type"]

            if event_type == "streaming_text":
                chunk = event["data"].get("chunk", "")
                is_complete = event["data"].get("is_complete", False)
                visible = buffer.append(chunk)
                if visible:
                    planner_result.streamed_assistant_text = True
                    yield self.events.assistant_delta(state, visible, is_complete=False)
                if is_complete and not buffer.suppress_after_tool_use:
                    flushed = buffer.flush()
                    if flushed:
                        planner_result.streamed_assistant_text = True
                        yield self.events.assistant_delta(state, flushed, is_complete=False)
                    yield self.events.assistant_delta(state, "", is_complete=True)

            elif event_type == "thought":
                thought_data = event["data"]
                planner_result.thought = thought_data.get("thought")
                yield self.events.thought(
                    state,
                    planner_result.thought,
                    text_content=thought_data.get("text_content"),
                    will_use_tool=bool(planner_result.tool_calls),
                )

            elif event_type == "thinking_content":
                content = event["data"].get("content", "")
                if content:
                    yield self.events.thinking_content(state, content)

            elif event_type == "tool_use":
                tool_data = event["data"]
                tool_use_id = tool_data.get("tool_use_id", "")
                tool_name = tool_data.get("tool_name", "")
                tool_input, preparation_error = self.tool_coordinator.prepare_tool_input_for_state(
                    tool_name,
                    tool_data.get("input", {}),
                    state,
                )
                state.has_seen_tool_use = True
                buffer.note_tool_use()
                planner_result.tool_calls.append(ToolCall(tool_name, tool_input, tool_use_id))
                tool_action = {
                    "type": "TOOL_CALL",
                    "tool": tool_name,
                    "tool_call_id": tool_use_id,
                    "args": tool_input,
                }
                suppressed_observation = self._suppressed_housekeeping_observation(state, tool_action)
                if preparation_error is not None:
                    streaming_tool_executor.addCompletedTool(
                        tool_use_id=tool_use_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        result=preparation_error,
                    )
                elif suppressed_observation is not None:
                    streaming_tool_executor.addCompletedTool(
                        tool_use_id=tool_use_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        result=suppressed_observation,
                    )
                else:
                    streaming_tool_executor.addTool(
                        tool_use_id=tool_use_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        iteration=state.iteration,
                    )
                yield self.events.tool_use(state, tool_use_id, tool_name, tool_input)
                for completed_result in streaming_tool_executor.getCompletedResults():
                    yield completed_result["message"]

            elif event_type == "action":
                data = event["data"]
                planner_result.thought = data.get("thought", planner_result.thought)
                planner_result.action = data.get("action")
                planner_result.raw_thinking_blocks = data.get("raw_thinking_blocks")
                planner_result.yielded_tool_use_count = data.get("yielded_tool_use_count", 0)
                if planner_result.action and planner_result.action.get("type") == "PLAIN_TEXT_REPLY":
                    planner_result.text = planner_result.action.get("answer", "") or buffer.final_text()
                elif not planner_result.action:
                    planner_result.text = buffer.final_text()

        if not planner_result.action:
            planner_result = await self._fallback_non_streaming(
                state,
                context_result,
                conversation_history,
                tool_schemas,
                planner_result,
            )

        if supports_native_multimodal(state.mode) and attachments:
            self._consume_sent_attachments_after_planner(state, planner_result.action)

        if planner_result.action and planner_result.action.get("type") in ("TOOL_CALL", "TOOL_CALLS"):
            planner_result.tool_calls = self.tool_coordinator.tool_calls_from_action(planner_result.action)

        yield {
            "type": "_planner_done",
            "planner_result": planner_result,
            "streaming_tool_executor": streaming_tool_executor,
        }

    def _tool_names_to_suppress(self, state: RunState) -> set[str]:
        """Hide housekeeping tools after terminal/no-progress state updates."""
        suppressed = set(state.suppress_tool_names_next_turn)
        state.suppress_tool_names_next_turn.clear()
        return suppressed

    def _suppressed_housekeeping_observation(
        self,
        state: RunState,
        action: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Short-circuit housekeeping tools that were hidden for the current LLM turn."""
        tool_names: list[str] = []
        if action.get("type") == "TOOL_CALLS":
            tool_names = [
                tool.get("tool", "")
                for tool in action.get("tools", [])
                if isinstance(tool, dict)
            ]
        elif action.get("type") == "TOOL_CALL":
            tool_names = [action.get("tool", "")]

        suppressed = [
            tool_name
            for tool_name in tool_names
            if tool_name in state.suppress_tool_names_current_turn
            and tool_name in HOUSEKEEPING_TOOL_NAMES
        ]
        if not suppressed:
            return None

        return {
            "status": "blocked",
            "success": False,
            "suppressed_tool_call": True,
            "error": "suppressed_housekeeping_tool_call",
            "data": {
                "tool_name": suppressed[0],
                "suppressed_tools": suppressed,
                "iteration": state.iteration,
            },
            "summary": (
                f"状态管理工具 {suppressed[0]} 本轮已被系统抑制，"
                "不要重复更新任务状态；请执行真实业务工具，或直接给出最终回答。"
            ),
        }

    def _apply_housekeeping_policy(
        self,
        state: RunState,
        action: Dict[str, Any],
        observation: Dict[str, Any],
    ) -> None:
        """Classify housekeeping-only turns and suppress repeated state updates."""
        if action.get("type") == "TOOL_CALLS":
            tool_names = [
                tool.get("tool", "")
                for tool in action.get("tools", [])
                if isinstance(tool, dict)
            ]
        elif action.get("type") == "TOOL_CALL":
            tool_names = [action.get("tool", "")]
        else:
            tool_names = []

        housekeeping_only = all_housekeeping_tools(tool_names)
        state.last_tool_turn_housekeeping_only = housekeeping_only
        if not housekeeping_only:
            return

        state.suppress_tool_names_next_turn.update(HOUSEKEEPING_TOOL_NAMES)
        return

    async def _fallback_non_streaming(
        self,
        state: RunState,
        context_result: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        partial: PlannerResult,
    ) -> PlannerResult:
        self._raise_if_cancelled()
        user_content = None
        attachments = self._effective_attachments(state)
        if supports_native_multimodal(state.mode) and attachments:
            from .multimodal import build_anthropic_user_content

            user_content = build_anthropic_user_content(
                context_result["user_conversation"],
                attachments,
            )
        result = await self.planner.think_and_action(
            query=state.user_query,
            system_prompt=context_result.get("system_prompt_blocks") or context_result["system_prompt"],
            user_conversation=context_result["user_conversation"],
            tools=tool_schemas,
            iteration=state.iteration,
            mode=state.mode,
            conversation_history=conversation_history,
            user_content=user_content,
            attachments=attachments,
            llm_provider=self.config.llm_provider,
            llm_model=self.config.llm_model,
            auto_profile=self.config.auto_profile,
        )
        if supports_native_multimodal(state.mode) and attachments:
            self._consume_sent_attachments_after_planner(state, result.get("action"))
        partial.thought = result.get("thought")
        partial.action = result.get("action")
        partial.raw_thinking_blocks = result.get("raw_thinking_blocks")
        partial.pop_events.append(self.events.thought(state, partial.thought))
        return partial

    async def _handle_streamed_tools(
        self,
        state: RunState,
        planner_result: PlannerResult,
        streaming_tool_executor,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        self._raise_if_cancelled()
        async for remaining_result in streaming_tool_executor.getRemainingResults():
            self._raise_if_cancelled()
            yield remaining_result["message"]
        for completed_result in streaming_tool_executor.getCompletedResults():
            yield completed_result["message"]

        observation, action, records = self.tool_coordinator.collect_streaming_results(state, streaming_tool_executor)
        self._capture_multimodal_attachments(state, observation)
        self._capture_drawio_board_context(state, observation)
        self._apply_housekeeping_policy(state, action, observation)
        self._ensure_user_message_written(state)
        self.writer.add_tool_exchange(records, planner_result)
        self.writer.add_iteration(planner_result.thought, action, observation)
        self._enforce_custom_tool_terminal_rules(state, action, records)

        async for event in self.observation_processor.process(state, planner_result, action, observation):
            yield event

    @staticmethod
    def _is_deterministic_model_error(error: Exception) -> bool:
        message = str(error).lower()
        markers = (
            "http 400", "status code: 400", "status_code=400", "error code: 400",
            "400 client error", "bad request",
            "http 401", "http 403", "error code: 401", "error code: 403",
            "unauthorized", "forbidden",
            "authentication", "invalid request", "request format",
        )
        return any(marker in message for marker in markers)

    @staticmethod
    def _is_terminal_quota_error(error: Exception) -> bool:
        """Identify billing/plan exhaustion that cannot recover inside this run."""
        message = str(error).lower()
        markers = (
            "token plan 用量上限",
            "insufficient_quota",
            "billing limit",
            "payment required",
            "http 402",
            "error code: 402",
        )
        return any(marker in message for marker in markers)

    @staticmethod
    def _enforce_custom_tool_terminal_rules(
        state: RunState,
        action: Dict[str, Any],
        records: List[Dict[str, Any]],
    ) -> None:
        if state.mode != "custom":
            return
        unavailable = next((
            record for record in records
            if isinstance(record.get("result"), dict)
            and str(record["result"].get("error", "")).startswith(("工具不可用:", "工具不存在:"))
        ), None)
        if unavailable is not None:
            raise CustomAgentTerminalError(
                f"custom Agent 工具状态已变化: {unavailable['result'].get('error')}"
            )
        blocked = next((
            record for record in records
            if isinstance(record.get("result"), dict)
            and record["result"].get("loop_guard") is True
            and record["result"].get("severity") == "block"
        ), None)
        if blocked is None:
            if records:
                state.last_loop_block_signature = None
            return
        signature = json.dumps(
            {"tool": blocked.get("tool_name"), "args": blocked.get("tool_input", {})},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        if state.last_loop_block_signature == signature:
            raise CustomAgentTerminalError(
                f"工具循环已终止: {blocked.get('tool_name')} 使用相同参数重复请求"
            )
        state.last_loop_block_signature = signature

    async def _complete_response(
        self,
        state: RunState,
        planner_result: PlannerResult,
        answer: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        late_steering_applied = False
        async for event in self._apply_steering_inputs(state, completion_boundary=True):
            late_steering_applied = True
            yield event
        if late_steering_applied:
            return

        self.observation_processor.capture_last_knowledge_sources(state)
        self._ensure_user_message_written(state)
        completion_action = dict(planner_result.action or {"type": "PLAIN_TEXT_REPLY"})
        completion_action["type"] = "PLAIN_TEXT_REPLY"
        completion_action["answer"] = answer
        self.writer.add_iteration(
            planner_result.thought,
            completion_action,
            {"success": True, "summary": "任务完成"},
        )
        async for event in self.finalizer.complete(
            state,
            answer,
            planner_result=planner_result,
            thought=planner_result.thought,
        ):
            yield event

    @staticmethod
    def _board_completion_block_reason(state: RunState) -> Optional[str]:
        return None

    def _ensure_user_message_written(self, state: RunState) -> None:
        """Persist the current user turn exactly once, after planning context is built."""
        if state.user_message_written:
            return
        self.writer.add_user_message(
            state.persisted_user_message_content
            if state.persisted_user_message_content is not None
            else state.user_query
        )
        state.user_message_written = True

    def _raise_if_cancelled(self) -> None:
        if self.config.cancel_event and self.config.cancel_event.is_set():
            raise AgentRunCancelled("用户已暂停本轮分析")

    def _format_observation(self, observation: Dict[str, Any]) -> str:
        import json

        if not observation:
            return ""
        return json.dumps(observation, ensure_ascii=False, indent=2, default=str)
