"""
WebSocket路由 - 定时任务事件推送
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.scheduled_tasks.event_bus import get_event_bus

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/ws/scheduled-tasks")
async def scheduled_tasks_websocket(websocket: WebSocket):
    """定时任务事件WebSocket"""
    event_bus = get_event_bus()

    try:
        await event_bus.connect(websocket)

        # 保持连接
        while True:
            # 接收客户端消息（心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        event_bus.disconnect(websocket)
        logger.info("WebSocket disconnected normally")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        event_bus.disconnect(websocket)
