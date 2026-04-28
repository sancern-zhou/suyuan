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
        reasoning: Any = None,
    ) -> AsyncGenerator[dict, None]:
        state.final_answer = answer or ""
        state.task_completed = True
        self.writer.add_final_assistant_message(state, planner_result, thought=thought, reasoning=reasoning)
        if self.agent_logger:
            self.agent_logger.end_run(
                status="completed",
                final_answer=state.final_answer,
                metadata={"iterations": state.iteration},
            )
        yield self.events.final_answer(state, thought=thought, reasoning=reasoning)
        yield self.events.agent_finish(state, thought=thought, reasoning=reasoning)
        yield self.events.complete(state)

    async def timeout(self, state: RunState) -> AsyncGenerator[dict, None]:
        state.final_answer = (
            "分析任务较复杂，已尝试多种方法但未能在规定步骤内完成。\n\n"
            "💡 建议：\n"
            "• 将复杂问题拆分成几个简单问题\n"
            "• 提供更具体的背景信息\n"
            "• 直接询问某个特定方面"
        )
        state.task_completed = False
        if not state.assistant_message_written:
            self.writer.session.add_assistant_response(state.final_answer)
            state.assistant_message_written = True
        if self.agent_logger:
            self.agent_logger.end_run(
                status="timeout",
                metadata={"iterations": state.iteration, "reason": "max_iterations_reached"},
            )
        yield self.events.complete(state, status="incomplete", reason="max_iterations_reached")

    async def fatal_error(self, state: RunState, error: Exception) -> AsyncGenerator[dict, None]:
        if self.agent_logger:
            self.agent_logger.log_error(error=str(error), error_type="fatal")
            self.agent_logger.end_run(status="failed", metadata={"error": str(error)})
        yield self.events.fatal_error(state, error)
