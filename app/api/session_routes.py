"""
会话管理API路由

提供会话保存、恢复、列表、删除等API端点。
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import structlog

from app.agent.session import SessionManager, get_session_manager, SessionState

logger = structlog.get_logger()

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/")
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

    sessions = session_manager.list_sessions(state=state_filter, limit=limit)

    return {
        "sessions": [s.model_dump() for s in sessions],
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
    stats = session_manager.get_session_stats()

    return stats


@router.get("/active")
async def get_active_sessions():
    """
    获取所有活跃会话

    Returns:
        活跃会话列表
    """
    session_manager = get_session_manager()
    sessions = session_manager.get_active_sessions()

    return {
        "sessions": [s.model_dump() for s in sessions],
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
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return session.model_dump()


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
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    success = session_manager.save_session(session)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to save session: {session_id}")

    return {"message": f"Session {session_id} saved successfully"}


@router.post("/{session_id}/restore")
async def restore_session(session_id: str):
    """
    恢复会话

    Args:
        session_id: 会话ID

    Returns:
        完整会话数据（包含conversation_history）
    """
    logger.info("[会话恢复] 开始恢复会话", session_id=session_id)

    session_manager = get_session_manager()
    session = session_manager.load_session(session_id)

    if not session:
        logger.error("[会话恢复] 会话未找到", session_id=session_id)
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    logger.info("[会话恢复] 会话加载成功",
                session_id=session_id,
                conversation_history_count=len(session.conversation_history) if session.conversation_history else 0,
                data_ids_count=len(session.data_ids) if session.data_ids else 0,
                visual_ids_count=len(session.visual_ids) if session.visual_ids else 0,
                state=session.state.value if session.state else None)

    # 打印前3条消息示例
    if session.conversation_history:
        logger.info("[会话恢复] 前3条消息示例",
                    messages=session.conversation_history[:3])

    # 返回完整会话数据（包含conversation_history）
    session_data = session.model_dump()

    logger.info("[会话恢复] 返回完整会话数据",
                session_keys=list(session_data.keys()),
                has_conversation_history=bool(session_data.get('conversation_history')),
                conversation_history_length=len(session_data.get('conversation_history', [])))

    return {
        "message": f"Session {session_id} restored successfully",
        "session": session_data,  # 返回完整数据，不是摘要
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
    success = session_manager.archive_session(session_id)

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
    success = session_manager.delete_session(session_id)

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
    deleted_count = session_manager.cleanup_expired_sessions()

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

    success = session_manager.export_session(session_id, output_path)

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
    session = session_manager.import_session(input_path)

    if not session:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to import session from: {input_path}"
        )

    return {
        "message": f"Session imported successfully",
        "session": session.to_summary().model_dump()
    }
