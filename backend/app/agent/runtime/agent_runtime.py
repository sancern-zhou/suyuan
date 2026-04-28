"""Decomposed ReAct runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

from ..prompts.react_prompts import format_finish_summary_prompt
from .assistant_stream_buffer import AssistantStreamBuffer
from .conversation_writer import ConversationWriter
from .event_bus import RuntimeEventBus
from .finalizer import Finalizer
from .observation_processor import ObservationProcessor
from .session_queue import SessionRunQueue
from .tool_coordinator import ToolCoordinator
from .transcript_repairer import TranscriptRepairer
from .types import PlannerResult, RunState, ToolCall

logger = structlog.get_logger()


@dataclass
class AgentRuntimeConfig:
    memory_manager: Any
    planner: Any
    tool_executor: Any
    context_builder: Any
    task_completion_guard: Any
    max_iterations: int = 30
    enhance_with_history: bool = True
    enable_reasoning: bool = False
    is_interruption: bool = False
    knowledge_base_ids: Optional[list] = None
    agent_logger: Any = None
    schema_injector: Any = None


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
            async for event in self._run_locked(state, initial_messages):
                yield event

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
                    metadata={"enhance_with_history": state.enhance_with_history, "runtime": "decomposed"},
                )
                logger.info("agent_runtime_run_started", run_id=run_id)

            self.planner.is_interruption = self.config.is_interruption
            self.writer.load_initial_history_if_needed(initial_messages)
            self.writer.add_user_message(state.user_query)

            yield self.events.start(state)

            while state.iteration < self.config.max_iterations and not state.task_completed:
                state.iteration += 1
                try:
                    async for event in self._run_iteration(state):
                        yield event
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
                async for event in self.finalizer.timeout(state):
                    yield event

        except Exception as exc:
            logger.error("agent_runtime_fatal_error", error=str(exc), exc_info=True)
            async for event in self.finalizer.fatal_error(state, exc):
                yield event

    async def _run_iteration(self, state: RunState) -> AsyncGenerator[Dict[str, Any], None]:
        context_result, conversation_history = await self._build_context(state)
        planner_result, streaming_tool_executor = await self._run_planner_stream(
            state,
            context_result,
            conversation_history,
        )

        action = planner_result.action or {"type": "ERROR", "error": "no action"}
        action_type = action.get("type", "ERROR")

        if streaming_tool_executor.total_count > 0 and action_type in ("TOOL_CALL", "TOOL_CALLS"):
            for event in planner_result.pop_events:
                yield event
            async for event in self._handle_streamed_tools(state, planner_result, streaming_tool_executor):
                yield event
            return

        if action_type == "PLAIN_TEXT_REPLY":
            action = {"type": "FINAL_ANSWER", "answer": action.get("answer", "")}
            action_type = "FINAL_ANSWER"

        if action_type == "FINAL_ANSWER" and self._has_streamed_assistant_text(planner_result):
            state.response_streamed = True

        for event in planner_result.pop_events:
            yield event

        if action_type == "FINAL_ANSWER":
            async for event in self._complete_response(state, planner_result, action.get("answer", "")):
                yield event
            return

        if action_type == "FINISH_SUMMARY":
            async for event in self._finish_summary(state, planner_result):
                yield event
            return

        if action_type in ("TOOL_CALL", "TOOL_CALLS"):
            observation, records, tool_events = await self.tool_coordinator.execute_legacy_action(state, action)
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
        self.writer.add_iteration(planner_result.thought, action, observation)

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
            is_interruption=self.config.is_interruption,
        )
        conversation_history = self.memory.session.get_messages_for_llm()
        conversation_history = self.transcript_repairer.repair(conversation_history)
        return context_result, conversation_history

    async def _run_planner_stream(
        self,
        state: RunState,
        context_result: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
    ):
        from app.agent.tool_adapter import get_tool_schemas
        from ..core.streaming_tool_executor import StreamingToolExecutor

        tool_schemas = get_tool_schemas()
        streaming_tool_executor = StreamingToolExecutor(
            tool_executor=self.executor,
            tool_registry=self.executor.tool_registry if hasattr(self.executor, "tool_registry") else {},
        )
        buffer = AssistantStreamBuffer()
        planner_result = PlannerResult()

        async for event in self.planner.think_and_action_streaming(
            query=state.user_query,
            system_prompt=context_result["system_prompt"],
            user_conversation=context_result["user_conversation"],
            tools=tool_schemas,
            iteration=state.iteration,
            mode=state.mode,
            conversation_history=conversation_history,
        ):
            event_type = event["type"]

            if event_type == "streaming_text":
                chunk = event["data"].get("chunk", "")
                is_complete = event["data"].get("is_complete", False)
                visible = buffer.append(chunk)
                if visible:
                    planner_result.pop_events.append(self.events.assistant_delta(state, visible, is_complete=False))
                elif is_complete and not state.has_seen_tool_use:
                    planner_result.pop_events.append(self.events.assistant_delta(state, "", is_complete=True))

            elif event_type == "thought":
                planner_result.thought = event["data"].get("thought")
                planner_result.reasoning = event["data"].get("reasoning")
                planner_result.pop_events.append(
                    self.events.thought(state, planner_result.thought, planner_result.reasoning)
                )

            elif event_type == "tool_use":
                tool_data = event["data"]
                tool_use_id = tool_data.get("tool_use_id", "")
                tool_name = tool_data.get("tool_name", "")
                tool_input = self.tool_coordinator.normalize_tool_input(tool_name, tool_data.get("input", {}))
                state.has_seen_tool_use = True
                buffer.note_tool_use()
                planner_result.tool_calls.append(ToolCall(tool_name, tool_input, tool_use_id))
                streaming_tool_executor.addTool(
                    tool_use_id=tool_use_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    iteration=state.iteration,
                )
                planner_result.pop_events.append(self.events.tool_use(state, tool_use_id, tool_name, tool_input))
                for completed_result in streaming_tool_executor.getCompletedResults():
                    planner_result.pop_events.append(completed_result["message"])

            elif event_type == "action":
                data = event["data"]
                planner_result.thought = data.get("thought", planner_result.thought)
                planner_result.reasoning = data.get("reasoning", planner_result.reasoning)
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

        return planner_result, streaming_tool_executor

    def _has_streamed_assistant_text(self, planner_result: PlannerResult) -> bool:
        for event in planner_result.pop_events:
            if event.get("type") != "streaming_text":
                continue
            data = event.get("data", {})
            if data.get("chunk"):
                return True
        return False

    async def _fallback_non_streaming(
        self,
        state: RunState,
        context_result: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        tool_schemas: List[Dict[str, Any]],
        partial: PlannerResult,
    ) -> PlannerResult:
        result = await self.planner.think_and_action(
            query=state.user_query,
            system_prompt=context_result["system_prompt"],
            user_conversation=context_result["user_conversation"],
            tools=tool_schemas,
            iteration=state.iteration,
            mode=state.mode,
            conversation_history=conversation_history,
        )
        partial.thought = result.get("thought")
        partial.reasoning = result.get("reasoning")
        partial.action = result.get("action")
        partial.raw_thinking_blocks = result.get("raw_thinking_blocks")
        partial.pop_events.append(self.events.thought(state, partial.thought, partial.reasoning))
        return partial

    async def _handle_streamed_tools(
        self,
        state: RunState,
        planner_result: PlannerResult,
        streaming_tool_executor,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        async for remaining_result in streaming_tool_executor.getRemainingResults():
            yield remaining_result["message"]
        for completed_result in streaming_tool_executor.getCompletedResults():
            yield completed_result["message"]

        observation, action, records = self.tool_coordinator.collect_streaming_results(state, streaming_tool_executor)
        self.writer.add_tool_exchange(records, planner_result)
        self.writer.add_iteration(planner_result.thought, action, observation)

        if isinstance(observation, dict) and observation.get("action_type") == "FINISH_SUMMARY":
            async for event in self._finish_summary(state, planner_result):
                yield event
            return

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
            action = {"type": "FINAL_ANSWER", "answer": answer}
            self.writer.add_iteration(planner_result.thought, action, observation)
            yield self.events.tool_result(state, "task_guard", observation, True, "task_guard")
            return

        self.observation_processor.capture_last_knowledge_sources(state)
        self.writer.add_iteration(
            planner_result.thought,
            {"type": "FINAL_ANSWER", "answer": answer},
            {"success": True, "summary": "任务完成"},
        )
        async for event in self.finalizer.complete(
            state,
            answer,
            planner_result=planner_result,
            thought=planner_result.thought,
            reasoning=planner_result.reasoning,
        ):
            yield event

    async def _finish_summary(
        self,
        state: RunState,
        planner_result: PlannerResult,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        guard_result = await self.config.task_completion_guard.check(state.session_id)
        if guard_result.get("has_incomplete"):
            observation = {
                "success": False,
                "warning": True,
                "incomplete_tasks": guard_result["incomplete_tasks"],
                "summary": f"有 {guard_result['incomplete_count']} 个任务尚未完成，不能生成最终答案。请先完成所有任务。",
                "guard_warning": guard_result["warning_message"],
            }
            self.writer.add_iteration(planner_result.thought, {"type": "FINISH_SUMMARY"}, observation)
            yield self.events.tool_result(state, "task_guard", observation, True, "task_guard")
            return

        prompt = format_finish_summary_prompt(
            user_query=state.user_query,
            tool_results=self.memory.session.get_compressed_summary() or "无工具调用数据",
            final_thought=planner_result.thought,
        )
        response_text = ""
        async for chunk in self.planner.stream_user_answer(prompt):
            response_text += chunk
            yield self.events.assistant_delta(state, chunk, is_complete=False)
        yield self.events.assistant_delta(state, "", is_complete=True)
        state.response_streamed = True

        self.writer.add_iteration(
            planner_result.thought,
            {"type": "FINISH_SUMMARY"},
            {"success": True, "summary": "FINISH_SUMMARY: 生成最终答案"},
        )
        yield self.events.tool_result(
            state,
            "finish_summary",
            {"success": True, "summary": "FINISH_SUMMARY: 已生成最终答案"},
            False,
            "finish_summary",
        )
        async for event in self.finalizer.complete(
            state,
            response_text,
            planner_result=planner_result,
            thought=planner_result.thought,
            reasoning=planner_result.reasoning,
        ):
            yield event

    def _format_observation(self, observation: Dict[str, Any]) -> str:
        import json

        if not observation:
            return ""
        return json.dumps(observation, ensure_ascii=False, indent=2, default=str)
