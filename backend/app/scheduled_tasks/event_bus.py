"""
事件总线 - WebSocket广播
用于实时推送任务执行事件
"""
import json
import structlog
from typing import Set, Dict, Any
from fastapi import WebSocket

logger = structlog.get_logger()


class EventBus:
    """简单的事件总线（WebSocket广播）"""

    def __init__(self):
        self.connections: Set[WebSocket] = set()

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
