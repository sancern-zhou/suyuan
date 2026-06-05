"""Decomposed ReAct runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

from .assistant_stream_buffer import AssistantStreamBuffer
from .conversation_writer import ConversationWriter
from .event_bus import RuntimeEventBus
from .finalizer import Finalizer
from .observation_processor import ObservationProcessor
from .session_queue import SessionRunQueue
from .tool_coordinator import ToolCoordinator
from .tool_classification import all_housekeeping_tools
from .transcript_repairer import TranscriptRepairer
from .types import PlannerResult, RunState, ToolCall
from .cancellation import AgentRunCancelled, cancellation_registry
from .steering import steering_registry
from ..context.context_diagnostics import ContextDiagnostics

logger = structlog.get_logger()


@dataclass
class AgentRuntimeConfig:
    memory_manager: Any
    planner: Any
    tool_executor: Any
    context_builder: Any
    task_completion_guard: Any
    max_iterations: int = 60
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
        )

        async with self.session_queue.lock(state.session_id):
            await steering_registry.register(state.session_id, state.run_id, state.mode)
            try:
                async for event in self._run_locked(state, initial_messages):
                    yield event
            finally:
                await steering_registry.unregister(state.session_id, state.run_id)

    async def _run_locked(
        self,
        state: RunState,
        initial_messages: Optional[List[Dict[str, Any]]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
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
                except AgentRunCancelled:
                    self._ensure_user_message_written(state)
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
                    if "fatal" in str(exc).lower():
                        break

            if not state.task_completed:
                self._ensure_user_message_written(state)
                async for event in self.finalizer.timeout(state):
                    yield event

        except Exception as exc:
            if isinstance(exc, AgentRunCancelled):
                self._ensure_user_message_written(state)
                yield self.events.interrupted(state)
                return
            logger.error("agent_runtime_fatal_error", error=str(exc), exc_info=True)
            self._ensure_user_message_written(state)
            async for event in self.finalizer.fatal_error(state, exc):
                yield event

    async def _run_iteration(self, state: RunState) -> AsyncGenerator[Dict[str, Any], None]:
        context_result, conversation_history = await self._build_context(state)
        attachments = self._effective_attachments(state)
        if state.mode == "social" and attachments:
            from .multimodal import build_anthropic_user_content, build_persisted_user_content

            state.user_message_content = build_anthropic_user_content(
                state.user_query,
                attachments,
            )
            state.persisted_user_message_content = build_persisted_user_content(
                state.user_query,
                attachments,
            )
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
            observation, records, tool_events = await self.tool_coordinator.execute_legacy_action(state, action)
            self._capture_multimodal_attachments(state, observation)
            self._apply_housekeeping_policy(state, action, observation)
            self._ensure_user_message_written(state)
            self.writer.add_tool_exchange(records, planner_result)
            self.writer.add_iteration(planner_result.thought, action, observation)
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
        """Current-run image attachments available to social-mode native multimodal calls."""
        attachments: List[Dict[str, Any]] = []
        if self.config.attachments:
            attachments.extend(self.config.attachments)
        if state.pending_attachments:
            attachments.extend(state.pending_attachments)
        return attachments

    def _capture_multimodal_attachments(self, state: RunState, observation: Dict[str, Any]) -> None:
        if state.mode != "social" or not isinstance(observation, dict):
            return

        from .multimodal import extract_multimodal_attachments

        attachments = extract_multimodal_attachments(observation)
        if not attachments:
            return

        state.pending_attachments.extend(attachments)
        logger.info(
            "multimodal_attachments_captured_from_tool",
            session_id=state.session_id,
            run_id=state.run_id,
            iteration=state.iteration,
            count=len(attachments),
            names=[item.get("name") for item in attachments if isinstance(item, dict)],
        )

    async def _apply_steering_inputs(self, state: RunState) -> AsyncGenerator[Dict[str, Any], None]:
        items = await steering_registry.drain(state.session_id, state.run_id)
        if not items:
            return

        self._ensure_user_message_written(state)
        messages = [item.content for item in items]
        for content in messages:
            self.writer.add_user_message(f"【执行中用户补充】{content}")

        logger.info(
            "steering_inputs_applied",
            session_id=state.session_id,
            run_id=state.run_id,
            count=len(messages),
        )
        yield self.events.steering_applied(state, messages)

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
        tool_schemas = get_tool_schemas(mode=state.mode)
        suppressed_tool_names = self._tool_names_to_suppress(state)
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
        if state.mode == "social" and attachments:
            from .multimodal import build_anthropic_user_content

            user_content = build_anthropic_user_content(
                context_result["user_conversation"],
                attachments,
            )

        async for event in self.planner.think_and_action_streaming(
            query=state.user_query,
            system_prompt=context_result["system_prompt"],
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
                elif is_complete and not buffer.suppress_after_tool_use:
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
                tool_input = self.tool_coordinator.normalize_tool_input(
                    tool_name,
                    tool_data.get("input", {}),
                    mode=state.mode,
                )
                state.has_seen_tool_use = True
                buffer.note_tool_use()
                planner_result.tool_calls.append(ToolCall(tool_name, tool_input, tool_use_id))
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

        if planner_result.action and planner_result.action.get("type") in ("TOOL_CALL", "TOOL_CALLS"):
            planner_result.tool_calls = self.tool_coordinator.tool_calls_from_action(planner_result.action)

        yield {
            "type": "_planner_done",
            "planner_result": planner_result,
            "streaming_tool_executor": streaming_tool_executor,
        }

    def _tool_names_to_suppress(self, state: RunState) -> set[str]:
        """Hide housekeeping tools after terminal/no-progress state updates."""
        # ✅ 修复：删除 TodoWrite 抑制策略
        # 原因：抑制会导致 LLM 无法正常调用 TodoWrite，反而输出文本格式的伪调用
        suppressed = set(state.suppress_tool_names_next_turn)
        state.suppress_tool_names_next_turn.clear()
        return suppressed

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

        should_suppress_todo = False
        if action.get("type") == "TOOL_CALL" and action.get("tool") == "TodoWrite":
            should_suppress_todo = bool(
                isinstance(observation, dict)
                and (observation.get("no_op") or observation.get("all_completed"))
            )
        elif action.get("type") == "TOOL_CALLS" and isinstance(observation, dict):
            for item in observation.get("tool_results", []):
                if item.get("tool_name") != "TodoWrite":
                    continue
                result = item.get("result", {})
                if isinstance(result, dict) and (result.get("no_op") or result.get("all_completed")):
                    should_suppress_todo = True
                    break

        if should_suppress_todo:
            state.suppress_tool_names_next_turn.add("TodoWrite")
            logger.info(
                "housekeeping_tool_suppressed_next_turn",
                tool_name="TodoWrite",
                iteration=state.iteration,
                reason="no_op_or_all_completed",
            )

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
        if state.mode == "social" and attachments:
            from .multimodal import build_anthropic_user_content

            user_content = build_anthropic_user_content(
                context_result["user_conversation"],
                attachments,
            )
        result = await self.planner.think_and_action(
            query=state.user_query,
            system_prompt=context_result["system_prompt"],
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
        self._apply_housekeeping_policy(state, action, observation)
        self._ensure_user_message_written(state)
        self.writer.add_tool_exchange(records, planner_result)
        self.writer.add_iteration(planner_result.thought, action, observation)

        async for event in self.observation_processor.process(state, planner_result, action, observation):
            yield event

    async def _complete_response(
        self,
        state: RunState,
        planner_result: PlannerResult,
        answer: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        guard_result = await self.config.task_completion_guard.check(state.session_id)
        if guard_result.get("has_incomplete"):
            observation = {
                "success": False,
                "warning": True,
                "incomplete_tasks": guard_result["incomplete_tasks"],
                "summary": f"有 {guard_result['incomplete_count']} 个任务尚未完成，不能结束任务。请先完成所有任务。",
                "guard_warning": guard_result["warning_message"],
            }
            action = {"type": "PLAIN_TEXT_REPLY", "answer": answer}
            self._ensure_user_message_written(state)
            self.writer.add_iteration(planner_result.thought, action, observation)
            yield self.events.tool_result(state, "task_guard", observation, True, "task_guard")
            return

        self.observation_processor.capture_last_knowledge_sources(state)
        self._ensure_user_message_written(state)
        self.writer.add_iteration(
            planner_result.thought,
            {"type": "PLAIN_TEXT_REPLY", "answer": answer},
            {"success": True, "summary": "任务完成"},
        )
        async for event in self.finalizer.complete(
            state,
            answer,
            planner_result=planner_result,
            thought=planner_result.thought,
        ):
            yield event

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
