"""
会话管理API路由

提供会话保存、恢复、列表、删除等API端点。
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import structlog

from app.agent.session import get_session_manager, SessionState

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/")
@router.get("")  # 同时支持不带斜杠的请求
async def list_sessions(
    state: Optional[str] = None,
    limit: Optional[int] = None
):
    """
    列出所有会话

    Args:
        state: 过滤状态（active/paused/completed/failed/archived）
        limit: 限制数量

    Returns:
        会话列表
    """
    session_manager = get_session_manager()

    # 解析状态过滤
    state_filter = None
    if state:
        try:
            state_filter = SessionState(state)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid state: {state}. Must be one of: active, paused, completed, failed, archived"
            )

    sessions = await session_manager.list_sessions(state=state_filter, limit=limit)

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


@router.post("/{session_id}/restore")
async def restore_session(session_id: str, message_limit: int = 5):
    """
    恢复会话（分段加载：首次只返回最新N条消息）

    Args:
        session_id: 会话ID
        message_limit: 首次加载的最新消息数量，默认5

    Returns:
        会话元数据 + 最新N条消息 + 分页状态
    """
    logger.info("[会话恢复] 开始恢复会话", session_id=session_id, message_limit=message_limit)

    session_manager = get_session_manager()
    session = await session_manager.load_session(session_id)

    if not session:
        logger.error("[会话恢复] 会话未找到", session_id=session_id)
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    # 使用 session 的 conversation_history 做分页
    all_messages = session.conversation_history or []
    total_count = len(all_messages)

    # 取最新 N 条
    latest_messages = all_messages[-message_limit:] if total_count > message_limit else all_messages
    has_more = total_count > message_limit

    # 计算 oldest_sequence（基于列表索引）
    oldest_sequence = None
    if latest_messages:
        oldest_idx = total_count - len(latest_messages)
        oldest_sequence = oldest_idx

    logger.info("[会话恢复] 会话加载成功",
                session_id=session_id,
                total_messages=total_count,
                loaded_messages=len(latest_messages),
                has_more=has_more,
                state=session.state.value if session.state else None)

    # 使用 mode='json' 确保 float 特殊值（inf, -inf, NaN）被正确处理
    session_data = session.model_dump(mode='json')
    # 用分页结果替换 conversation_history
    session_data["conversation_history"] = latest_messages

    # 分页状态
    session_data["has_more_messages"] = has_more
    session_data["total_message_count"] = total_count
    session_data["oldest_sequence"] = oldest_sequence

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

    return {
        "message": f"Session {session_id} restored successfully",
        "session": session_data,
        "can_continue": session.state in [SessionState.ACTIVE, SessionState.PAUSED]
    }


@router.post("/{session_id}/archive")
async def archive_session(session_id: str):
    """
    归档会话

    Args:
        session_id: 会话ID

    Returns:
        归档结果
    """
    session_manager = get_session_manager()
    success = await session_manager.archive_session(session_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session not found or failed to archive: {session_id}"
        )

    return {"message": f"Session {session_id} archived successfully"}


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

    删除超过保留天数的已完成/失败/归档会话。

    Returns:
        清理结果
    """
    session_manager = get_session_manager()
    deleted_count = await session_manager.cleanup_expired_sessions()

    return {
        "message": f"Cleaned up {deleted_count} expired sessions",
        "deleted_count": deleted_count
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
