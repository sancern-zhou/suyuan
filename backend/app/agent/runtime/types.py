"""Shared runtime data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4


AgentStream = Literal["lifecycle", "assistant", "tool", "result", "final", "error"]


@dataclass
class ToolCall:
    tool_name: str
    tool_input: Dict[str, Any]
    tool_call_id: str = ""

    def to_action(self) -> Dict[str, Any]:
        return {
            "type": "TOOL_CALL",
            "tool": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "args": self.tool_input,
        }


@dataclass
class PlannerResult:
    thought: Optional[str] = None
    reasoning: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    text: str = ""
    raw_thinking_blocks: Optional[List[Dict[str, Any]]] = None
    yielded_tool_use_count: int = 0
    tool_calls: List[ToolCall] = field(default_factory=list)
    pop_events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def action_type(self) -> str:
        if not self.action:
            return "ERROR"
        return self.action.get("type", "ERROR")


@dataclass
class RunState:
    session_id: str
    user_query: str
    mode: str
    enhance_with_history: bool = True
    run_id: str = field(default_factory=lambda: uuid4().hex)
    iteration: int = 0
    task_completed: bool = False
    response_text: str = ""
    response_streamed: bool = False
    assistant_message_written: bool = False
    has_seen_tool_use: bool = False
    workflow_sources: List[Any] = field(default_factory=list)
    workflow_visuals: List[Any] = field(default_factory=list)
    direct_from_workflow: bool = False
    last_observation: Optional[Dict[str, Any]] = None
    last_single_tool_result: Optional[Dict[str, Any]] = None

    def timestamp(self) -> str:
        return datetime.now().isoformat()


@dataclass
class RuntimeEvent:
    stream: AgentStream
    type: str
    data: Dict[str, Any]
    run_id: str
    session_id: str

    def to_legacy(self) -> Dict[str, Any]:
        return {
            "stream": self.stream,
            "type": self.type,
            "data": self.data,
            "run_id": self.run_id,
            "session_id": self.session_id,
        }
