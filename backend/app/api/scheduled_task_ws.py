"""
WebSocket路由 - 定时任务事件推送
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from app.scheduled_tasks.event_bus import get_event_bus
from app.auth.ws_tickets import InvalidWebSocketTicket

logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/ws/scheduled-tasks")
async def scheduled_tasks_websocket(websocket: WebSocket):
    """定时任务事件WebSocket"""
    event_bus = get_event_bus()
    ticket = websocket.query_params.get("ticket", "")
    try:
        user = await websocket.app.state.ws_ticket_service.consume(
            ticket, purpose="scheduled-tasks"
        )
    except InvalidWebSocketTicket:
        await websocket.close(code=4401, reason="authentication_required")
        return

    websocket.state.current_user = user
    connected = False

    try:
        await event_bus.connect(websocket)
        connected = True

        # 保持连接
        while True:
            # 接收客户端消息（心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if connected:
            event_bus.disconnect(websocket)
