"""Unified run finalization."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from app.agent.markup_sanitizer import (
    DSML_TOOL_CALL_BLOCKED_NOTICE,
    strip_dsml_tool_call_markup,
)
from app.agent.resources.chart_placeholders import normalize_chart_placeholders
from app.agent.runtime.visual_alias import resolve_chart_alias_markers

from .conversation_writer import ConversationWriter
from .event_bus import RuntimeEventBus
from .types import PlannerResult, RunState


class Finalizer:
    def __init__(self, writer: ConversationWriter, event_bus: RuntimeEventBus, agent_logger=None) -> None:
        self.writer = writer
        self.events = event_bus
        self.agent_logger = agent_logger

    async def complete(
        self,
        state: RunState,
        answer: str,
        planner_result: Optional[PlannerResult] = None,
        thought: Any = None,
        stream_answer: bool = True,
    ) -> AsyncGenerator[dict, None]:
        answer = await normalize_chart_placeholders(answer or "", state.session_id)
        sanitized, had_dsml = strip_dsml_tool_call_markup(answer or "")
        if had_dsml:
            sanitized = sanitized or DSML_TOOL_CALL_BLOCKED_NOTICE
        answer = await resolve_chart_alias_markers(sanitized, state.session_id)
        state.response_text = answer or ""
        state.task_completed = True
        self.writer.add_final_assistant_message(state, planner_result, thought=thought)
        if self.agent_logger:
            self.agent_logger.end_run(
                status="completed",
                response=state.response_text,
                metadata={"iterations": state.iteration},
            )
        if stream_answer and not state.response_streamed:
            async for event in self._stream_response(state):
                yield event
        yield self.events.agent_finish(state, thought=thought)
        yield self.events.complete(state)

    async def _stream_response(self, state: RunState) -> AsyncGenerator[dict, None]:
        """Emit the assistant response body through the streaming_text channel."""
        answer = state.response_text or ""
        if answer:
            for chunk in self._chunk_text(answer):
                yield self.events.assistant_delta(state, chunk, is_complete=False)
        yield self.events.assistant_delta(state, "", is_complete=True)
        state.response_streamed = True

    def _chunk_text(self, text: str, size: int = 80):
        for index in range(0, len(text), size):
            yield text[index:index + size]

    async def timeout(self, state: RunState, reason: Optional[str] = None) -> AsyncGenerator[dict, None]:
        # reason 取自时间预算终态（extended_timeout / stalled_no_progress）；
        # 缺省维持历史语义 max_iterations_reached（轮次预算模式）。
        reason = reason or "max_iterations_reached"
        state.response_text = "分析任务较复杂，在限定步骤内未完成，是否继续？"
        state.task_completed = False
        if not state.assistant_message_written:
            self.writer.session.add_assistant_response(state.response_text)
            state.assistant_message_written = True
        if self.agent_logger:
            self.agent_logger.end_run(
                status="timeout",
                metadata={"iterations": state.iteration, "reason": reason},
            )
        async for event in self._stream_response(state):
            yield event
        yield self.events.complete(state, status="incomplete", reason=reason)

    async def no_progress(self, state: RunState) -> AsyncGenerator[dict, None]:
        """无进展熔断：连续多轮无成功工具结果与正文输出，判定任务停摆。

        无步数上限模式下接管原迭代上限的失控保护职能；会话上下文保留，
        用户可补充指示后继续。
        """
        state.response_text = (
            "任务已连续多轮没有新的进展（无成功的工具调用或有效输出），"
            "为避免无效消耗已停止。请补充说明或调整任务后重试。"
        )
        state.task_completed = False
        if not state.assistant_message_written:
            self.writer.session.add_assistant_response(state.response_text)
            state.assistant_message_written = True
        if self.agent_logger:
            self.agent_logger.end_run(
                status="timeout",
                metadata={"iterations": state.iteration, "reason": "no_progress_detected"},
            )
        async for event in self._stream_response(state):
            yield event
        yield self.events.complete(state, status="incomplete", reason="no_progress_detected")

    async def fatal_error(self, state: RunState, error: Exception) -> AsyncGenerator[dict, None]:
        if self.agent_logger:
            self.agent_logger.log_error(error=str(error), error_type="fatal")
            self.agent_logger.end_run(status="failed", metadata={"error": str(error)})
        yield self.events.fatal_error(state, error, user_message=self._user_message(error))

    @staticmethod
    def _user_message(error: Exception) -> str | None:
        """重试链耗尽时给用户友好文案，而不是把网关堆栈直接糊到对话区。"""
        from app.services.llm_failover import (
            TRANSIENT_FAILURE_USER_MESSAGE,
            is_transient_failure,
        )

        return TRANSIENT_FAILURE_USER_MESSAGE if is_transient_failure(error) else None
