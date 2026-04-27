"""
Tool Lifecycle State Machine

Phase 2.2: 工具生命周期状态追踪器（OpenClaw 模式）

用于追踪工具执行的完整生命周期：
QUEUED → RUNNING → COMPLETED/FAILED
"""

from enum import Enum
from dataclasses import dataclass

# 简化导入，避免类型提示问题
try:
    from typing import Any, Optional
except ImportError:
    Any = object
    Optional = object

import structlog

logger = structlog.get_logger()


class ToolState(Enum):
    """工具执行状态"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class ToolExecution:
    """工具执行追踪器（OpenClaw 模式）

    追踪工具执行的完整生命周期，包括状态转换、执行时间、错误信息等。

    Attributes:
        tool_call_id: 工具调用 ID（来自 Anthropic content_block.id）
        tool_name: 工具名称
        args: 工具参数
        state: 当前状态
        result: 执行结果（如果完成）
        error: 错误消息（如果失败）
        retry_count: 重试次数
        start_time: 开始时间戳
        end_time: 结束时间戳
    """
    tool_call_id: str      # 来自 Anthropic content_block.id
    tool_name: str
    args: dict  # Dict[str, Any]
    state: ToolState = ToolState.QUEUED
    result: Any = None
    error: Any = None
    retry_count: int = 0
    start_time: Any = None
    end_time: Any = None

    def transition_to(self, new_state: ToolState):
        """状态转换（带日志记录）

        Args:
            new_state: 新状态
        """
        old_state = self.state
        self.state = new_state
        logger.info(
            "tool_state_transition",
            tool_call_id=self.tool_call_id,
            tool_name=self.tool_name,
            old_state=old_state.value,
            new_state=new_state.value
        )

    @property
    def duration_ms(self):
        """计算执行耗时（毫秒）

        Returns:
            执行耗时（毫秒），如果未完成则返回 None
        """
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None
