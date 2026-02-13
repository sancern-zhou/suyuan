"""
知识问答对话存储服务

提供对话会话和轮次的CRUD操作，支持：
- 会话管理（创建/获取/归档/删除）
- 轮次管理（添加/查询对话历史）
- RAG上下文构建
- 自动过期清理
"""

import uuid
import structlog
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.knowledge_base.models import (
    ConversationSession,
    ConversationTurn,
    ConversationSessionStatus
)

logger = structlog.get_logger()

# 配置
DEFAULT_SESSION_TTL_HOURS = 12  # 默认会话过期时间（小时）
MAX_TURNS_PER_SESSION = 50      # 每会话最大轮次数


class ConversationStore:
    """对话存储服务"""

    def __init__(
        self,
        db: AsyncSession,
        session_ttl_hours: int = DEFAULT_SESSION_TTL_HOURS,
        max_turns_per_session: int = MAX_TURNS_PER_SESSION
    ):
        """
        初始化对话存储服务

        Args:
            db: 数据库会话
            session_ttl_hours: 会话过期时间（小时）
            max_turns_per_session: 每会话最大轮次数
        """
        self.db = db
        self.session_ttl_hours = session_ttl_hours
        self.max_turns_per_session = max_turns_per_session

    # ========================================
    # 会话管理
    # ========================================

    async def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        first_query: str = ""
    ) -> Tuple[str, List[ConversationTurn], bool]:
        """
        获取或创建会话

        Args:
            session_id: 会话ID（可选）
            user_id: 用户ID（可选）
            knowledge_base_ids: 知识库ID列表（可选）
            first_query: 首轮问题（用于生成标题）

        Returns:
            (session_id, turns, is_new) 元组
            - session_id: 会话ID
            - turns: 历史轮次列表
            - is_new: 是否新建会话
        """
        is_new = False

        if session_id:
            # 尝试获取现有会话
            result = await self.db.execute(
                select(ConversationSession)
                .where(ConversationSession.id == session_id)
                .options(selectinload(ConversationSession.turns))
            )
            existing_session = result.scalar_one_or_none()

            if existing_session:
                # 更新会话状态为活跃
                existing_session.status = ConversationSessionStatus.ACTIVE
                existing_session.updated_at = datetime.utcnow()
                # 刷新过期时间
                existing_session.expires_at = datetime.utcnow() + timedelta(hours=self.session_ttl_hours)
                await self.db.commit()

                # 检查是否过期
                if existing_session.expires_at and existing_session.expires_at < datetime.utcnow():
                    # 已过期，创建新会话
                    return await self._create_new_session(
                        user_id=user_id,
                        knowledge_base_ids=knowledge_base_ids,
                        first_query=first_query
                    )

                # 返回现有会话
                turns = existing_session.turns or []
                return session_id, turns, False
            else:
                # session_id 不存在，创建新会话
                return await self._create_new_session(
                    session_id=session_id,
                    user_id=user_id,
                    knowledge_base_ids=knowledge_base_ids,
                    first_query=first_query
                )
        else:
            # 没有提供session_id，创建新会话
            return await self._create_new_session(
                user_id=user_id,
                knowledge_base_ids=knowledge_base_ids,
                first_query=first_query
            )

    async def _create_new_session(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        knowledge_base_ids: Optional[List[str]] = None,
        first_query: str = ""
    ) -> Tuple[str, List[ConversationTurn], bool]:
        """创建新会话"""
        # 生成会话ID
        if session_id is None:
            session_id = f"kqa_{uuid.uuid4().hex}"

        # 生成标题（取问题前50字）
        title = first_query[:50] + "..." if len(first_query) > 50 else first_query or "新对话"

        # 计算过期时间
        expires_at = datetime.utcnow() + timedelta(hours=self.session_ttl_hours)

        # 创建会话
        session = ConversationSession(
            id=session_id,
            title=title,
            status=ConversationSessionStatus.ACTIVE,
            knowledge_base_ids=knowledge_base_ids or [],
            total_turns=0,
            last_query=first_query,
            user_id=user_id,
            expires_at=expires_at
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        logger.info(
            "conversation_session_created",
            session_id=session_id,
            user_id=user_id,
            knowledge_base_ids=knowledge_base_ids
        )

        return session_id, [], True

    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """获取会话详情"""
        result = await self.db.execute(
            select(ConversationSession)
            .where(ConversationSession.id == session_id)
            .options(selectinload(ConversationSession.turns))
        )
        return result.scalar_one_or_none()

    async def list_user_sessions(
        self,
        user_id: str,
        status: Optional[ConversationSessionStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[ConversationSession]:
        """
        列出用户的会话

        Args:
            user_id: 用户ID
            status: 状态过滤（可选）
            limit: 返回数量
            offset: 偏移量

        Returns:
            会话列表
        """
        query = select(ConversationSession).where(
            ConversationSession.user_id == user_id
        )

        if status:
            query = query.where(ConversationSession.status == status)

        query = query.order_by(ConversationSession.updated_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def archive_session(self, session_id: str) -> bool:
        """归档会话"""
        result = await self.db.execute(
            select(ConversationSession).where(ConversationSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            session.status = ConversationSessionStatus.ARCHIVED
            await self.db.commit()
            logger.info("session_archived", session_id=session_id)
            return True

        return False

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（级联删除轮次）"""
        result = await self.db.execute(
            select(ConversationSession).where(ConversationSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            await self.db.delete(session)
            await self.db.commit()
            logger.info("session_deleted", session_id=session_id)
            return True

        return False

    # ========================================
    # 轮次管理
    # ========================================

    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        sources_count: int = 0,
        query_metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationTurn:
        """
        添加对话轮次

        Args:
            session_id: 会话ID
            role: 角色 ("user" / "assistant")
            content: 内容
            sources: 参考来源（assistant）
            sources_count: 来源数量
            query_metadata: 查询元数据（user）

        Returns:
            创建的轮次对象
        """
        # 获取当前轮次序号
        result = await self.db.execute(
            select(func.max(ConversationTurn.turn_index))
            .where(ConversationTurn.session_id == session_id)
        )
        max_index = result.scalar() or 0

        # 检查是否超过最大轮次限制
        if max_index >= self.max_turns_per_session:
            logger.warning(
                "session_max_turns_reached",
                session_id=session_id,
                max_turns=self.max_turns_per_session
            )
            # 可以选择拒绝添加或自动归档，这里选择拒绝
            raise ValueError(f"会话已达到最大轮次限制 ({self.max_turns_per_session})")

        turn = ConversationTurn(
            id=f"turn_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            turn_index=max_index + 1,
            role=role,
            content=content,
            sources=sources or [],
            sources_count=sources_count,
            query_metadata=query_metadata or {}
        )

        self.db.add(turn)

        # 更新会话统计
        session = await self.get_session(session_id)
        if session:
            session.total_turns = max_index + 1
            session.last_query = content if role == "user" else session.last_query
            session.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(turn)

        logger.debug(
            "conversation_turn_added",
            session_id=session_id,
            turn_index=turn.turn_index,
            role=role
        )

        return turn

    async def get_recent_turns(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[ConversationTurn]:
        """
        获取最近的对话轮次

        Args:
            session_id: 会话ID
            limit: 返回数量

        Returns:
            轮次列表（按时间正序）
        """
        result = await self.db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.session_id == session_id)
            .order_by(ConversationTurn.turn_index)
            .limit(limit)
        )
        turns = list(result.scalars().all())

        # 如果超过limit，返回最后limit条
        if len(turns) > limit:
            turns = turns[-limit:]

        return turns

    async def get_all_turns(self, session_id: str) -> List[ConversationTurn]:
        """获取会话的所有轮次"""
        result = await self.db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.session_id == session_id)
            .order_by(ConversationTurn.turn_index)
        )
        return list(result.scalars().all())

    # ========================================
    # RAG 上下文构建
    # ========================================

    def build_history_for_rag(self, turns: List[ConversationTurn]) -> str:
        """
        构建RAG格式的历史对话文本

        Args:
            turns: 对话轮次列表

        Returns:
            格式化的历史对话文本
        """
        if not turns:
            return ""

        history_parts = []
        for turn in turns:
            role_name = "用户" if turn.role == "user" else "助手"
            history_parts.append(f"{role_name}：{turn.content}")

        return "\n\n".join(history_parts)

    def build_messages_for_llm(self, turns: List[ConversationTurn]) -> List[Dict[str, str]]:
        """
        构建LLM消息格式的历史

        Args:
            turns: 对话轮次列表

        Returns:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        """
        if not turns:
            return []

        messages = []
        for turn in turns:
            messages.append({
                "role": "user" if turn.role == "user" else "assistant",
                "content": turn.content
            })

        return messages

    # ========================================
    # 过期清理
    # ========================================

    async def cleanup_expired_sessions(self) -> int:
        """
        清理过期的会话

        Returns:
            清理的会话数量
        """
        result = await self.db.execute(
            select(ConversationSession).where(
                ConversationSession.expires_at < datetime.utcnow(),
                ConversationSession.status == ConversationSessionStatus.ACTIVE
            )
        )
        expired_sessions = list(result.scalars().all())

        count = 0
        for session in expired_sessions:
            await self.delete_session(session.id)
            count += 1

        if count > 0:
            logger.info(
                "expired_sessions_cleaned",
                count=count,
                ttl_hours=self.session_ttl_hours
            )

        return count


# ========================================
# 单例工厂函数
# ========================================

_conversation_store_instance = None


async def get_conversation_store(
    db: AsyncSession,
    session_ttl_hours: int = DEFAULT_SESSION_TTL_HOURS
) -> ConversationStore:
    """
    获取对话存储服务实例

    Args:
        db: 数据库会话
        session_ttl_hours: 会话过期时间

    Returns:
        ConversationStore实例
    """
    return ConversationStore(
        db=db,
        session_ttl_hours=session_ttl_hours
    )
