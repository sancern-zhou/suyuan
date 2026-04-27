"""
事件总线 - WebSocket广播
用于实时推送任务执行事件

Phase 2 扩展：支持工具生命周期追踪（OpenClaw-inspired）
"""
import json
import structlog
from typing import Set, Dict, Any, Callable, List
from collections import defaultdict
from fastapi import WebSocket
from datetime import datetime

logger = structlog.get_logger()


class EventBus:
    """扩展的事件总线（支持工具生命周期追踪）"""

    def __init__(self):
        self.connections: Set[WebSocket] = set()
        # Phase 2 新增：内部订阅者（用于工具追踪、监控、日志、指标收集）
        self._internal_subscribers: Dict[str, Set[Callable]] = defaultdict(set)

    async def connect(self, websocket: WebSocket):
        """连接WebSocket"""
        await websocket.accept()
        self.connections.add(websocket)
        logger.info(f"WebSocket connected, total: {len(self.connections)}")

    def disconnect(self, websocket: WebSocket):
        """断开WebSocket"""
        self.connections.discard(websocket)
        logger.info(f"WebSocket disconnected, total: {len(self.connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """广播事件到所有连接"""
        if not self.connections:
            return

        message = {
            "event": event_type,  # ✅ 修复：前端期望 "event" 字段，不是 "type"
            "data": data
        }

        # 发送到所有连接
        disconnected = set()
        for websocket in self.connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                disconnected.add(websocket)

        # 清理断开的连接
        for websocket in disconnected:
            self.disconnect(websocket)

    # ========================================
    # Phase 2: 内部事件订阅系统（用于监控、日志、指标收集）
    # ========================================

    def subscribe(self, event_type: str, handler: Callable):
        """订阅内部事件（用于监控、日志、指标收集）

        Args:
            event_type: 事件类型
            handler: 事件处理函数（接收 data 参数）
        """
        self._internal_subscribers[event_type].add(handler)
        logger.debug(f"Subscribed to {event_type}: {handler.__name__}")

    def emit_internal(self, event_type: str, data: Dict[str, Any]):
        """发射内部事件（不发送到 WebSocket）

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if event_type in self._internal_subscribers:
            for handler in self._internal_subscribers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(f"Event handler failed: {e}")

    # ========================================
    # Phase 2: 工具生命周期事件
    # ========================================

    async def emit_tool_execution_start(
        self,
        tool_call_id: str,
        tool_name: str,
        args: Dict[str, Any]
    ):
        """工具开始执行事件

        Args:
            tool_call_id: 工具调用 ID（来自 Anthropic content_block.id）
            tool_name: 工具名称
            args: 工具参数
        """
        logger.info(f"Tool execution started: {tool_name} ({tool_call_id})")

        # 内部事件（用于监控）
        self.emit_internal("tool_execution_start", {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "args": args,
            "phase": "start",
            "timestamp": datetime.now().isoformat()
        })

        # 可选：广播到 WebSocket（前端可显示执行进度）
        await self.broadcast("tool_execution_start", {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name
        })

    async def emit_tool_execution_end(
        self,
        tool_call_id: str,
        tool_name: str,
        result: Dict[str, Any],
        duration_ms: float
    ):
        """工具执行完成事件

        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            result: 工具执行结果
            duration_ms: 执行耗时（毫秒）
        """
        logger.info(f"Tool execution completed: {tool_name} in {duration_ms:.2f}ms")

        # 内部事件（用于监控）
        self.emit_internal("tool_execution_end", {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "result": self._sanitize_result(result),
            "isError": False,
            "phase": "end",
            "duration_ms": duration_ms
        })

        # 广播到 WebSocket
        await self.broadcast("tool_execution_end", {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "duration_ms": duration_ms
        })

    async def emit_tool_error(
        self,
        tool_call_id: str,
        tool_name: str,
        error: str
    ):
        """工具执行错误事件

        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            error: 错误消息
        """
        logger.error(f"Tool execution failed: {tool_name} - {error}")

        # 内部事件（用于监控）
        self.emit_internal("tool_error", {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "error": error,
            "isError": True,
            "phase": "error"
        })

        # 广播到 WebSocket
        await self.broadcast("tool_error", {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "error": error
        })

    def _sanitize_result(self, result: Any, max_chars: int = 8000) -> Any:
        """清理工具结果（避免过大的日志）

        Args:
            result: 原始结果
            max_chars: 最大字符数（默认8000，与 OpenClaw 一致）

        Returns:
            清理后的结果
        """
        if isinstance(result, str):
            return result[:max_chars] + "..." if len(result) > max_chars else result
        elif isinstance(result, dict):
            return {k: self._sanitize_result(v, max_chars) for k, v in result.items()}
        elif isinstance(result, list):
            return [self._sanitize_result(item, max_chars) for item in result]
        else:
            return result

    # ========================================
    # 原有任务事件（保持不变）
    # ========================================

    async def emit_task_created(self, task_id: str, task_name: str):
        """任务创建事件"""
        logger.info(f"Emitting task_created event: {task_id} - {task_name}")
        await self.broadcast("task_created", {
            "task_id": task_id,
            "task_name": task_name
        })
        logger.info(f"Task_created event sent to {len(self.connections)} connections")

    async def emit_task_updated(self, task_id: str, task_name: str):
        """任务更新事件"""
        logger.info(f"Emitting task_updated event: {task_id} - {task_name}")
        await self.broadcast("task_updated", {
            "task_id": task_id,
            "task_name": task_name
        })

    async def emit_task_deleted(self, task_id: str):
        """任务删除事件"""
        logger.info(f"Emitting task_deleted event: {task_id}")
        await self.broadcast("task_deleted", {
            "task_id": task_id
        })

    async def emit_execution_started(self, execution_id: str, task_id: str, task_name: str):
        """执行开始事件"""
        await self.broadcast("execution_started", {
            "execution_id": execution_id,
            "task_id": task_id,
            "task_name": task_name
        })

    async def emit_execution_step_completed(
        self,
        execution_id: str,
        step_id: str,
        status: str
    ):
        """步骤完成事件"""
        await self.broadcast("execution_step_completed", {
            "execution_id": execution_id,
            "step_id": step_id,
            "status": status
        })

    async def emit_execution_completed(
        self,
        execution_id: str,
        task_id: str,
        status: str,
        duration_seconds: float
    ):
        """执行完成事件"""
        await self.broadcast("execution_completed", {
            "execution_id": execution_id,
            "task_id": task_id,
            "status": status,
            "duration_seconds": duration_seconds
        })


# 全局事件总线实例
_event_bus: EventBus = EventBus()


def get_event_bus() -> EventBus:
    """获取事件总线实例"""
    return _event_bus
