"""
会话管理API路由

提供会话保存、恢复、列表、删除等API端点。
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from datetime import datetime
import structlog

from app.agent.session import get_session_manager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/")
@router.get("")  # 同时支持不带斜杠的请求
async def list_sessions(
    limit: Optional[int] = None
):
    """
    列出所有会话

    Args:
        limit: 限制数量

    Returns:
        会话列表
    """
    session_manager = get_session_manager()
    sessions = await session_manager.list_sessions(limit=limit)

    return {
        "sessions": [s.model_dump(mode='json') for s in sessions],
        "total": len(sessions)
    }


@router.get("/stats")
async def get_session_stats():
    """
    获取会话统计信息

    Returns:
        统计信息
    """
    session_manager = get_session_manager()
    stats = await session_manager.get_session_stats()

    return stats


@router.get("/active")
async def get_active_sessions():
    """
    获取所有活跃会话

    Returns:
        活跃会话列表
    """
    session_manager = get_session_manager()
    sessions = await session_manager.get_active_sessions()

    return {
        "sessions": [s.model_dump(mode='json') for s in sessions],
        "total": len(sessions)
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """
    获取会话详情

    Args:
        session_id: 会话ID

    Returns:
        会话详情
    """
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return session.model_dump(mode='json')


@router.post("/{session_id}/save")
async def save_session(session_id: str):
    """
    手动保存会话

    Args:
        session_id: 会话ID

    Returns:
        保存结果
    """
    session_manager = get_session_manager()
    session = await session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    success = await session_manager.save_session(session)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to save session: {session_id}")

    return {"message": f"Session {session_id} saved successfully"}


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    before: Optional[int] = None,
    limit: int = 30
):
    """
    分页获取会话消息

    Args:
        session_id: 会话ID
        before: 游标，加载 sequence_number < before 的消息（不传则返回最新消息）
        limit: 每次加载数量，默认30

    Returns:
        消息列表、是否还有更多、总消息数
    """
    from app.db.session_repository import get_session_repository

    repo = get_session_repository()

    # 先验证会话是否存在
    session = await repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    result = await repo.get_messages_before(
        session_id=session_id,
        before_sequence=before,
        limit=limit
    )

    return result


def _sanitize_floats(obj):
    """
    清理数据中的特殊浮点值（inf, -inf, nan），转换为 None

    防止 JSON 序列化时出现 "Out of range float values are not JSON compliant" 错误
    """
    import math

    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_floats(item) for item in obj]
    return obj


@router.post("/{session_id}/restore")
async def restore_session(session_id: str, message_limit: int = 5):
    """
    恢复会话（数据库层分页加载：只返回最新N条消息）

    Args:
        session_id: 会话ID
        message_limit: 首次加载的最新消息数量，默认5

    Returns:
        会话元数据 + 最新N条消息 + 分页状态
    """
    logger.info("[会话恢复] 开始恢复会话", session_id=session_id, message_limit=message_limit)

    session_manager = get_session_manager()

    # ✅ 使用数据库层分页方法，不加载全部消息到内存
    result = await session_manager.load_session_with_pagination(
        session_id,
        message_limit
    )

    if not result:
        logger.error("[会话恢复] 会话未找到", session_id=session_id)
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    session = result["session"]
    pagination = result["pagination"]

    logger.info("[会话恢复] 会话加载成功（数据库层分页）",
                session_id=session_id,
                loaded_messages=len(session.conversation_history),
                total_messages=pagination["total_count"],
                has_more=pagination["has_more"])

    # 使用 mode='json' 确保 float 特殊值（inf, -inf, NaN）被正确处理
    session_data = session.model_dump(mode='json')

    # 分页状态（从数据库查询结果获取）
    session_data["has_more_messages"] = pagination["has_more"]
    session_data["total_message_count"] = pagination["total_count"]
    session_data["oldest_sequence"] = pagination["oldest_sequence"]

    # 从react_agent的_session_store中获取office_documents
    try:
        from app.routers.agent import multi_expert_agent_instance
        if multi_expert_agent_instance and session_id in multi_expert_agent_instance._session_store:
            session_store_data = multi_expert_agent_instance._session_store[session_id]
            office_documents = session_store_data.get("office_documents", [])
            if office_documents:
                session_data["office_documents"] = office_documents
                logger.info("[会话恢复] 从react_agent获取office_documents",
                            session_id=session_id,
                            count=len(office_documents))
    except Exception as e:
        logger.warning("[会话恢复] 获取office_documents失败",
                      session_id=session_id,
                      error=str(e))

    # 清理特殊浮点值，防止 JSON 序列化错误
    session_data = _sanitize_floats(session_data)

    return {
        "message": f"Session {session_id} restored successfully",
        "session": session_data
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """
    删除会话

    Args:
        session_id: 会话ID

    Returns:
        删除结果
    """
    session_manager = get_session_manager()
    success = await session_manager.delete_session(session_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or failed to delete: {session_id}"
        )

    logger.info("session_deleted", session_id=session_id)

    return {"message": f"Session {session_id} deleted successfully"}


@router.post("/cleanup")
async def cleanup_expired_sessions():
    """
    清理过期会话

    删除超过保留天数的会话。

    Returns:
        清理结果
    """
    session_manager = get_session_manager()
    deleted_count = await session_manager.cleanup_expired_sessions()

    return {
        "message": f"Cleaned up {deleted_count} expired sessions",
        "deleted_count": deleted_count
    }


@router.post("/auto-save")
async def auto_save_session(request: Request):
    """
    自动保存会话消息（每次AI回复完成时调用）

    Args:
        request: 包含 session_id, messages, state 的请求体

    Returns:
        保存结果
    """
    from app.agent.session import get_session_manager
    from app.agent.session.models import Session

    data = await request.json()
    session_id = data.get("session_id")
    messages = data.get("messages", [])
    state = data.get("state", "active")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    logger.info(
        "[autoSave] 自动保存会话",
        session_id=session_id,
        message_count=len(messages),
        state=state
    )

    session_manager = get_session_manager()

    # 加载现有会话
    session = await session_manager.load_session(session_id)

    if session:
        # 更新对话历史
        session.conversation_history = messages
        session.updated_at = datetime.now()

        # 保存到数据库
        success = await session_manager.save_session(session)

        if success:
            logger.info(
                "[autoSave] 会话保存成功",
                session_id=session_id,
                message_count=len(messages)
            )
            return {
                "status": "ok",
                "message": f"Session {session_id} auto-saved with {len(messages)} messages"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save session")
    else:
        # 会话不存在，创建新会话
        logger.warning("[autoSave] 会话不存在，跳过保存", session_id=session_id)
        return {
            "status": "skipped",
            "message": f"Session {session_id} does not exist"
        }


@router.post("/{session_id}/export")
async def export_session(session_id: str, output_path: Optional[str] = None):
    """
    导出会话

    Args:
        session_id: 会话ID
        output_path: 导出路径（可选）

    Returns:
        导出结果
    """
    session_manager = get_session_manager()

    # 如果未提供路径，使用默认路径
    if not output_path:
        output_path = f"backend_data_registry/exports/{session_id}.json"

    success = await session_manager.export_session(session_id, output_path)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or failed to export: {session_id}"
        )

    return {
        "message": f"Session {session_id} exported successfully",
        "output_path": output_path
    }


@router.post("/import")
async def import_session(input_path: str):
    """
    导入会话

    Args:
        input_path: 导入路径

    Returns:
        导入的会话信息
    """
    session_manager = get_session_manager()
    session = await session_manager.import_session(input_path)

    if not session:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to import session from: {input_path}"
        )

    return {
        "message": "Session imported successfully",
        "session": session.to_summary().model_dump(mode='json')
    }
