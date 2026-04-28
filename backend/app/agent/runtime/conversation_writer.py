"""Single writer for session transcript mutations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import PlannerResult, RunState


class ConversationWriter:
    def __init__(self, memory_manager) -> None:
        self.memory = memory_manager
        self.session = memory_manager.session

    def load_initial_history_if_needed(self, initial_messages: Optional[List[Dict[str, Any]]]) -> None:
        if not initial_messages:
            return
        if self.session.get_messages_for_llm():
            return
        self.session.load_history_messages(initial_messages)

    def add_user_message(self, content: str) -> None:
        self.session.add_user_message(content)

    def add_tool_exchange(
        self,
        tool_executions: List[Dict[str, Any]],
        planner_result: PlannerResult,
    ) -> None:
        if not tool_executions:
            return
        self.session.add_streaming_tool_results(
            tool_executions,
            thinking_blocks=planner_result.raw_thinking_blocks,
        )

    def add_iteration(self, thought: Any, action: Dict[str, Any], observation: Dict[str, Any]) -> None:
        self.memory.add_iteration(thought=thought, action=action, observation=observation)

    def add_final_assistant_message(
        self,
        state: RunState,
        planner_result: Optional[PlannerResult],
        thought: Any = None,
        reasoning: Any = None,
    ) -> None:
        if state.assistant_message_written or not state.final_answer:
            return
        self.session.add_assistant_message(
            state.final_answer,
            thought=thought if thought is not None else (planner_result.thought if planner_result else None),
            reasoning=reasoning if reasoning is not None else (planner_result.reasoning if planner_result else None),
            thinking_blocks=planner_result.raw_thinking_blocks if planner_result else None,
        )
        state.assistant_message_written = True
