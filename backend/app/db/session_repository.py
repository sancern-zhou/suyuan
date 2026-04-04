"""
会话数据库访问层

提供会话的 CRUD 操作，使用 SQLAlchemy ORM。
"""

import json
import structlog
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, delete, func

from .models_session import SessionDB, SessionMessageDB, SessionState, MessageType
from .database import engine

logger = structlog.get_logger()


class SessionRepository:
    """
    会话数据库访问层

    提供会话和消息的 CRUD 操作
    """

    def __init__(self):
        self.engine = engine

    async def create_session(
        self,
        session_id: str,
        query: str,
        state: SessionState = SessionState.ACTIVE,
        mode: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionDB:
        """创建新会话"""
        async with AsyncSession(self.engine) as session:
            db_session = SessionDB(
                session_id=session_id,
                query=query,
                state=state,
                mode=mode,
                metadata=metadata or {}
            )
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)

            logger.info(
                "session_created_in_db",
                session_id=session_id,
                mode=mode,
                state=state.value
            )
            return db_session

    async def get_session(self, session_id: str) -> Optional[SessionDB]:
        """获取会话（不包含消息）"""
        async with AsyncSession(self.engine) as session:
            stmt = select(SessionDB).where(SessionDB.session_id == session_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_session_with_messages(
        self,
        session_id: str,
        include_messages: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        获取会话及其消息

        返回格式兼容 Session 模型（用于平滑迁移）
        """
        async with AsyncSession(self.engine) as session:
            # 获取会话
            stmt = select(SessionDB).where(SessionDB.session_id == session_id)
            result = await session.execute(stmt)
            db_session = result.scalar_one_or_none()

            if not db_session:
                return None

            # 转换为字典格式
            session_dict = {
                "session_id": db_session.session_id,
                "query": db_session.query,
                "state": db_session.state.value,
                "created_at": db_session.created_at.isoformat() if db_session.created_at else None,
                "updated_at": db_session.updated_at.isoformat() if db_session.updated_at else None,
                "completed_at": db_session.completed_at.isoformat() if db_session.completed_at else None,
                "mode": db_session.mode,
                "current_step": db_session.current_step,
                "current_expert": db_session.current_expert,
                "data_ids": db_session.data_ids or [],
                "visual_ids": db_session.visual_ids or [],
                "error": db_session.error,
                "metadata": db_session.session_metadata or {},
                "conversation_history": []
            }

            # 如果需要加载消息
            if include_messages:
                stmt_msgs = (
                    select(SessionMessageDB)
                    .where(SessionMessageDB.session_id == session_id)
                    .order_by(SessionMessageDB.sequence_number)
                )
                result_msgs = await session.execute(stmt_msgs)
                messages = result_msgs.scalars().all()

                # 转换消息为前端格式
                for msg in messages:
                    msg_dict = {
                        "type": msg.message_type.value,
                        "content": msg.content,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "id": f"msg_{msg.id}"
                    }

                    # 添加 data 字段（如果存在）
                    if msg.data:
                        msg_dict["data"] = msg.data

                    # 添加 metadata 字段（如果存在）
                    if msg.msg_metadata:
                        msg_dict.update(msg.msg_metadata)

                    session_dict["conversation_history"].append(msg_dict)

                logger.info(
                    "session_loaded_with_messages",
                    session_id=session_id,
                    message_count=len(messages)
                )

            return session_dict

    async def update_session(
        self,
        session_id: str,
        **kwargs
    ) -> bool:
        """更新会话信息"""
        async with AsyncSession(self.engine) as session:
            stmt = (
                update(SessionDB)
                .where(SessionDB.session_id == session_id)
                .values(**kwargs)
            )
            result = await session.execute(stmt)
            await session.commit()

            success = result.rowcount > 0
            if success:
                logger.info("session_updated_in_db", session_id=session_id, updated_fields=list(kwargs.keys()))

            return success

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（级联删除消息）"""
        async with AsyncSession(self.engine) as session:
            stmt = delete(SessionDB).where(SessionDB.session_id == session_id)
            result = await session.execute(stmt)
            await session.commit()

            success = result.rowcount > 0
            if success:
                logger.info("session_deleted_from_db", session_id=session_id)

            return success

    async def list_sessions(
        self,
        state: Optional[SessionState] = None,
        mode: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出会话（返回摘要信息）"""
        async with AsyncSession(self.engine) as session:
            stmt = select(SessionDB)

            # 过滤条件
            if state:
                stmt = stmt.where(SessionDB.state == state)
            if mode:
                stmt = stmt.where(SessionDB.mode == mode)

            # 排序和分页
            stmt = stmt.order_by(SessionDB.created_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            sessions = result.scalars().all()

            # 转换为摘要格式
            summaries = []
            for s in sessions:
                summaries.append({
                    "session_id": s.session_id,
                    "query": s.query[:100] if s.query else "",
                    "state": s.state.value,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                    "mode": s.mode,
                    "data_count": len(s.data_ids) if s.data_ids else 0,
                    "visual_count": len(s.visual_ids) if s.visual_ids else 0,
                    "has_error": s.error is not None
                })

            return summaries

    async def save_conversation_history(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]]
    ) -> bool:
        """
        保存会话的对话历史

        删除旧消息，插入新消息（原子操作）
        """
        async with AsyncSession(self.engine) as session:
            try:
                # 先删除旧消息
                stmt_delete = delete(SessionMessageDB).where(SessionMessageDB.session_id == session_id)
                await session.execute(stmt_delete)

                # 批量插入新消息
                for idx, msg in enumerate(conversation_history):
                    # 提取消息类型
                    msg_type_str = msg.get("type") or (msg.get("role") if msg.get("role") == "user" else "final")

                    # 映射消息类型枚举
                    try:
                        msg_type = MessageType(msg_type_str)
                    except ValueError:
                        # 如果是 "assistant"，映射为 "final"
                        msg_type = MessageType.FINAL if msg_type_str == "assistant" else MessageType(msg_type_str)

                    db_msg = SessionMessageDB(
                        session_id=session_id,
                        message_type=msg_type,
                        content=msg.get("content"),
                        data=msg.get("data"),
                        timestamp=datetime.fromisoformat(msg["timestamp"]) if msg.get("timestamp") else datetime.utcnow(),
                        msg_metadata={k: v for k, v in msg.items() if k not in ["type", "content", "data", "timestamp"]},
                        sequence_number=idx
                    )
                    session.add(db_msg)

                await session.commit()

                logger.info(
                    "conversation_history_saved",
                    session_id=session_id,
                    message_count=len(conversation_history)
                )

                return True

            except Exception as e:
                await session.rollback()
                logger.error(
                    "failed_to_save_conversation_history",
                    session_id=session_id,
                    error=str(e)
                )
                return False

    async def add_message(
        self,
        session_id: str,
        message: Dict[str, Any],
        sequence_number: Optional[int] = None
    ) -> bool:
        """添加单条消息"""
        async with AsyncSession(self.engine) as session:
            try:
                # 获取当前最大序号
                if sequence_number is None:
                    stmt = (
                        select(func.max(SessionMessageDB.sequence_number))
                        .where(SessionMessageDB.session_id == session_id)
                    )
                    result = await session.execute(stmt)
                    max_seq = result.scalar() or 0
                    sequence_number = max_seq + 1

                # 提取消息类型
                msg_type_str = message.get("type") or (message.get("role") if message.get("role") == "user" else "final")

                try:
                    msg_type = MessageType(msg_type_str)
                except ValueError:
                    msg_type = MessageType.FINAL if msg_type_str == "assistant" else MessageType(msg_type_str)

                db_msg = SessionMessageDB(
                    session_id=session_id,
                    message_type=msg_type,
                    content=message.get("content"),
                    data=message.get("data"),
                    timestamp=datetime.fromisoformat(message["timestamp"]) if message.get("timestamp") else datetime.utcnow(),
                    msg_metadata={k: v for k, v in message.items() if k not in ["type", "content", "data", "timestamp"]},
                    sequence_number=sequence_number
                )
                session.add(db_msg)
                await session.commit()

                return True

            except Exception as e:
                await session.rollback()
                logger.error(
                    "failed_to_add_message",
                    session_id=session_id,
                    error=str(e)
                )
                return False

    async def get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量"""
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(func.count())
                .where(SessionMessageDB.session_id == session_id)
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    def _msg_to_dict(self, msg: SessionMessageDB) -> Dict[str, Any]:
        """将数据库消息转换为前端字典格式"""
        msg_dict: Dict[str, Any] = {
            "type": msg.message_type.value,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "id": f"msg_{msg.id}",
            "sequence_number": msg.sequence_number
        }
        if msg.data:
            msg_dict["data"] = msg.data
        if msg.msg_metadata:
            msg_dict.update(msg.msg_metadata)
        return msg_dict

    async def get_messages_before(
        self,
        session_id: str,
        before_sequence: Optional[int] = None,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        游标分页获取消息

        Args:
            session_id: 会话ID
            before_sequence: 游标，加载 sequence_number < before 的消息
            limit: 每次加载数量

        Returns:
            {
                "messages": [...],       # 按 sequence_number 升序排列
                "has_more": bool,
                "oldest_sequence": int | None,
                "total_count": int
            }
        """
        async with AsyncSession(self.engine) as session:
            # 先获取总数
            total_count_stmt = (
                select(func.count())
                .where(SessionMessageDB.session_id == session_id)
            )
            total_result = await session.execute(total_count_stmt)
            total_count = total_result.scalar() or 0

            # 查询消息（降序取 limit 条，再升序返回）
            stmt = (
                select(SessionMessageDB)
                .where(SessionMessageDB.session_id == session_id)
            )
            if before_sequence is not None:
                stmt = stmt.where(SessionMessageDB.sequence_number < before_sequence)

            stmt = stmt.order_by(SessionMessageDB.sequence_number.desc()).limit(limit)
            result = await session.execute(stmt)
            messages = list(reversed(result.scalars().all()))

            oldest_sequence = messages[0].sequence_number if messages else None
            # 还有更早的消息：最小 sequence_number > 0
            has_more = oldest_sequence is not None and oldest_sequence > 0

            return {
                "messages": [self._msg_to_dict(msg) for msg in messages],
                "has_more": has_more,
                "oldest_sequence": oldest_sequence,
                "total_count": total_count
            }


# 全局单例
_session_repository: Optional[SessionRepository] = None


def get_session_repository() -> SessionRepository:
    """获取会话仓库单例"""
    global _session_repository
    if _session_repository is None:
        _session_repository = SessionRepository()
    return _session_repository
