"""Unified run finalization."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

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

    async def timeout(self, state: RunState) -> AsyncGenerator[dict, None]:
        state.response_text = (
            "分析任务较复杂，已尝试多种方法但未能在规定步骤内完成。\n\n"
            "💡 建议：\n"
            "• 将复杂问题拆分成几个简单问题\n"
            "• 提供更具体的背景信息\n"
            "• 直接询问某个特定方面"
        )
        state.task_completed = False
        if not state.assistant_message_written:
            self.writer.session.add_assistant_response(state.response_text)
            state.assistant_message_written = True
        if self.agent_logger:
            self.agent_logger.end_run(
                status="timeout",
                metadata={"iterations": state.iteration, "reason": "max_iterations_reached"},
            )
        async for event in self._stream_response(state):
            yield event
        yield self.events.complete(state, status="incomplete", reason="max_iterations_reached")

    async def fatal_error(self, state: RunState, error: Exception) -> AsyncGenerator[dict, None]:
        if self.agent_logger:
            self.agent_logger.log_error(error=str(error), error_type="fatal")
            self.agent_logger.end_run(status="failed", metadata={"error": str(error)})
        yield self.events.fatal_error(state, error)
