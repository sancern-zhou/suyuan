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
    action: Optional[Dict[str, Any]] = None
    text: str = ""
    streamed_assistant_text: bool = False
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
    """运行状态

    ⚠️ 重要变更（模式B实施）：
    - 移除 workflow_visuals 字段（visuals现在从tool_result事件获取）
    - 保留 workflow_sources 字段（用于知识溯源）
    """
    session_id: str
    user_query: str
    mode: str
    enhance_with_history: bool = True
    user_message_content: Any = None
    persisted_user_message_content: Any = None
    run_id: str = field(default_factory=lambda: uuid4().hex)
    iteration: int = 0
    task_completed: bool = False
    response_text: str = ""
    response_streamed: bool = False
    assistant_message_written: bool = False
    user_message_written: bool = False
    has_seen_tool_use: bool = False
    workflow_sources: List[Any] = field(default_factory=list)
    # ❌ 移除：workflow_visuals（不再使用，visuals从tool_result获取）
    # workflow_visuals: List[Any] = field(default_factory=list)
    last_observation: Optional[Dict[str, Any]] = None
    last_single_tool_result: Optional[Dict[str, Any]] = None
    pending_attachments: List[Dict[str, Any]] = field(default_factory=list)
    consumed_attachment_keys: set[str] = field(default_factory=set)
    initial_attachments_consumed: bool = False
    board_context: Optional[Dict[str, Any]] = None
    board_context_updated_in_run: bool = False
    pending_board_candidate_id: Optional[str] = None
    board_quality_repair_count: int = 0
    suppress_tool_names_next_turn: set[str] = field(default_factory=set)
    suppress_tool_names_current_turn: set[str] = field(default_factory=set)
    last_tool_turn_housekeeping_only: bool = False
    last_loop_block_signature: Optional[str] = None
    last_missing_tool_signature: Optional[str] = None
    fixed_workflow_progress: Dict[str, Any] = field(default_factory=dict)
    # 最近一次 LLM 调用的上下文占用快照（planner context_usage 事件数据）
    last_context_usage: Optional[Dict[str, Any]] = None
    # 本轮上下文构建阶段的 token 估算（total + 工具 schema 估算），供网关不回传
    # input_tokens 时（如 scnet anthropic_messages 协议）合成占位快照兜底
    context_estimate_tokens: Optional[int] = None
    # 上下文构成分段估算：{"system_prompt": n, "messages": n, "tools": n}，
    # 随 context_usage 事件下发供前端 hover 面板展示占比
    context_breakdown: Optional[Dict[str, int]] = None
    # 本会话累计 token 用量（planner usage_delta 事件累计；Usage, not budget——
    # 只记账遥测，不参与预算判定）
    tokens_spent: int = 0
    last_turn_usage: Optional[Dict[str, Any]] = None

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
