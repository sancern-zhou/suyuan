"""
会话数据库访问层

提供会话的 CRUD 操作，使用 SQLAlchemy ORM。
完全兼容 Anthropic 原生 content blocks 格式。

数据库 schema 设计：
- role: Anthropic 角色（user/assistant），用于 LLM 对话恢复
- msg_type: 语义类型（user/thought/action/observation/tool_result/final），用于前端展示
- content: JSONB 类型，原生支持 str 和 list（Anthropic content blocks）
"""

import json
import structlog
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timezone
from datetime import time as datetime_time
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, load_only
from sqlalchemy import select, update, delete, func, cast, Text, case

from .models_session import SessionDB, SessionMessageDB
from .database import engine

logger = structlog.get_logger()

# 有效的语义类型集合
VALID_MSG_TYPES = {"user", "thought", "tool_use", "tool_result", "final"}

# These messages are rendered as conversation turns and must never be reduced
# to a preview during lightweight history restoration.
FULL_DISPLAY_CONTENT_MSG_TYPES = {"user", "final"}

MESSAGE_METADATA_EXCLUDED_KEYS = {
    "type",
    "role",
    "content",
    "data",
    "metadata",
    "timestamp",
    "thought",
    "reasoning",
    "id",
    "message_id",
    "visuals",
    "tool_use_id",
    "tool_name",
    "is_error",
}

# type -> role 映射表（确定每条消息的 Anthropic 角色）
TYPE_TO_ROLE = {
    "user": "user",
    "tool_result": "user",
    "thought": "assistant",
    "tool_use": "assistant",
    "final": "assistant",
}


class SessionRepository:
    """
    会话数据库访问层

    提供会话和消息的 CRUD 操作
    """

    def __init__(self):
        self.engine = engine

    def _pool_status(self) -> dict:
        pool = self.engine.pool
        return {
            "pool_status": pool.status(),
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }

    @staticmethod
    def _normalize_json_value(obj: Any) -> Any:
        """Recursively convert runtime values to JSON-compatible primitives."""
        if isinstance(obj, Enum):
            return SessionRepository._normalize_json_value(obj.value)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date, datetime_time)):
            return obj.isoformat()
        if isinstance(obj, (UUID, Path)):
            return str(obj)
        if isinstance(obj, dict):
            return {
                str(SessionRepository._normalize_json_value(key)): (
                    SessionRepository._normalize_json_value(value)
                )
                for key, value in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [SessionRepository._normalize_json_value(item) for item in obj]
        if isinstance(obj, (set, frozenset)):
            return [
                SessionRepository._normalize_json_value(item)
                for item in sorted(obj, key=str)
            ]
        if obj is None or isinstance(obj, (str, bool, int, float)):
            return obj
        return str(obj)

    @staticmethod
    def _convert_json_value(obj: Any) -> Any:
        """Backward-compatible alias for JSON normalization."""
        return SessionRepository._normalize_json_value(obj)

    @staticmethod
    def _resolve_role_and_type(msg: Dict[str, Any]) -> tuple:
        """
        从消息中解析 role 和 msg_type

        支持多种输入格式：
        - Anthropic 原生格式：有 role 字段（user/assistant）
        - 前端简化格式：有 type 字段（user/thought/tool_use/tool_result/final）
        - 旧格式：type 字段为 assistant

        Returns:
            (role: str, msg_type: str)
        """
        # 优先使用显式 role
        explicit_role = msg.get("role")
        msg_type = msg.get("type", "")

        # 规范化 msg_type
        if msg_type == "assistant":
            msg_type = "final"

        if msg_type not in VALID_MSG_TYPES:
            msg_type = "final"  # 兜底

        # 确定角色
        if explicit_role in ("user", "assistant"):
            role = explicit_role
        else:
            role = TYPE_TO_ROLE.get(msg_type, "assistant")

        return role, msg_type

    @staticmethod
    def _serialize_content(content: Any) -> Any:
        """
        序列化 content 为 JSONB 兼容格式

        JSONB 列原生支持 str, list, dict, None，
        只需处理 Decimal 等不可序列化的类型
        """
        if content is None:
            return None
        if isinstance(content, (str, list, dict, bool, int, float)):
            return content
        # 其他类型（Decimal 等）转换为字符串
        return str(content)

    @staticmethod
    def _deserialize_content(content: Any) -> Any:
        """Read content returned by both JSON and JSONB drivers.

        Some deployments return a JSON scalar string with its JSON quoting
        still present (for example ``\"hello\"``). Decode that wrapper while
        leaving ordinary strings and structured content unchanged.
        """
        if not isinstance(content, str):
            return content
        if not content.startswith('"'):
            return content
        try:
            decoded = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return content
        return decoded if isinstance(decoded, str) else content

    @staticmethod
    def _message_metadata(msg: Dict[str, Any]) -> Dict[str, Any]:
        """Return only small custom metadata fields for message persistence."""
        metadata = {
            k: v
            for k, v in msg.items()
            if k not in MESSAGE_METADATA_EXCLUDED_KEYS
        }
        return SessionRepository._convert_json_value(metadata)

    @staticmethod
    def _message_data(msg: Dict[str, Any]) -> Any:
        """Return message data with tool runtime fields preserved in one place."""
        msg_data = SessionRepository._convert_json_value(msg.get("data"))
        tool_fields = {
            key: msg[key]
            for key in ("tool_use_id", "tool_name", "is_error")
            if key in msg
        }
        if not tool_fields:
            return msg_data
        if msg_data is None:
            msg_data = {}
        if isinstance(msg_data, dict):
            for key, value in tool_fields.items():
                msg_data.setdefault(key, value)
        return SessionRepository._convert_json_value(msg_data)

    @staticmethod
    def _message_attachments(metadata: Any) -> List[Dict[str, Any]]:
        """Read only the lightweight attachment contract from message metadata."""
        if not isinstance(metadata, dict):
            return []
        return [
            dict(attachment)
            for attachment in metadata.get("attachments") or []
            if isinstance(attachment, dict)
        ]

    async def create_session(
        self,
        session_id: str,
        query: str,
        mode: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionDB:
        """创建新会话"""
        async with AsyncSession(self.engine) as session:
            db_session = SessionDB(
                session_id=session_id,
                query=query,
                mode=mode,
                session_metadata=metadata or {},
            )
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)

            logger.info(
                "session_created_in_db",
                session_id=session_id,
                mode=mode,
                resource_store="unified"
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
        include_messages: bool = True,
        include_artifacts: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        获取会话及其消息

        返回格式兼容 Session 模型（用于平滑迁移）
        """
        started = time.monotonic()
        metadata_ms = None
        messages_query_ms = None
        messages_convert_ms = None
        async with AsyncSession(self.engine) as session:
            # 获取会话
            stmt = select(SessionDB).where(SessionDB.session_id == session_id)
            if not include_artifacts:
                stmt = stmt.options(
                    load_only(
                        SessionDB.session_id,
                        SessionDB.query,
                        SessionDB.created_at,
                        SessionDB.updated_at,
                        SessionDB.mode,
                        SessionDB.current_step,
                        SessionDB.current_expert,
                        SessionDB.error,
                    )
                )
            metadata_started = time.monotonic()
            result = await session.execute(stmt)
            db_session = result.scalar_one_or_none()
            metadata_ms = round((time.monotonic() - metadata_started) * 1000, 2)

            if not db_session:
                logger.info(
                    "session_load_diagnostics",
                    session_id=session_id,
                    include_messages=include_messages,
                    include_artifacts=include_artifacts,
                    found=False,
                    metadata_ms=metadata_ms,
                    total_ms=round((time.monotonic() - started) * 1000, 2),
                    **self._pool_status(),
                )
                return None

            # 转换为字典格式
            session_dict = {
                "session_id": db_session.session_id,
                "query": db_session.query,
                "created_at": db_session.created_at.isoformat() if db_session.created_at else None,
                "updated_at": db_session.updated_at.isoformat() if db_session.updated_at else None,
                "mode": db_session.mode,
                "current_step": db_session.current_step,
                "current_expert": db_session.current_expert,
                "error": db_session.error,
                "metadata": db_session.session_metadata or {} if include_artifacts else {},
                "conversation_history": []
            }

            # 如果需要加载消息
            if include_messages:
                stmt_msgs = (
                    select(SessionMessageDB)
                    .where(SessionMessageDB.session_id == session_id)
                    .order_by(SessionMessageDB.sequence_number)
                )
                messages_query_started = time.monotonic()
                result_msgs = await session.execute(stmt_msgs)
                messages = result_msgs.scalars().all()
                messages_query_ms = round((time.monotonic() - messages_query_started) * 1000, 2)

                # 转换消息为前端格式
                messages_convert_started = time.monotonic()
                for msg in messages:
                    msg_dict = self._msg_to_dict(msg)
                    session_dict["conversation_history"].append(msg_dict)
                messages_convert_ms = round((time.monotonic() - messages_convert_started) * 1000, 2)

                logger.info(
                    "session_loaded_with_messages",
                    session_id=session_id,
                    message_count=len(messages)
                )

            logger.info(
                "session_load_diagnostics",
                session_id=session_id,
                include_messages=include_messages,
                include_artifacts=include_artifacts,
                found=True,
                message_count=len(session_dict["conversation_history"]),
                metadata_ms=metadata_ms,
                messages_query_ms=messages_query_ms,
                messages_convert_ms=messages_convert_ms,
                total_ms=round((time.monotonic() - started) * 1000, 2),
                **self._pool_status(),
            )
            return session_dict

    async def update_session(
        self,
        session_id: str,
        **kwargs
    ) -> bool:
        """更新会话信息"""
        started = time.monotonic()
        # 处理字段映射：metadata -> session_metadata
        if "metadata" in kwargs:
            kwargs["session_metadata"] = kwargs.pop("metadata")

        # 过滤掉无效的字段名（只保留 SessionDB 模型中定义的字段）
        valid_fields = {
            "query", "mode", "current_step", "current_expert",
            "error", "session_metadata"
        }
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_fields}

        async with AsyncSession(self.engine) as session:
            stmt = (
                update(SessionDB)
                .where(SessionDB.session_id == session_id)
                .values(**filtered_kwargs)
            )
            result = await session.execute(stmt)
            await session.commit()

            success = result.rowcount > 0
            if success:
                logger.info(
                    "session_updated_in_db",
                    session_id=session_id,
                    updated_fields=list(filtered_kwargs.keys()),
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                    **self._pool_status(),
                )

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
        mode: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """列出会话（返回摘要信息）"""
        async with AsyncSession(self.engine) as session:
            stmt = select(
                SessionDB.session_id,
                SessionDB.query,
                SessionDB.created_at,
                SessionDB.updated_at,
                SessionDB.mode,
                SessionDB.error,
                SessionDB.session_metadata,
            )

            # 过滤条件
            if mode:
                stmt = stmt.where(SessionDB.mode == mode)

            # 排序和分页
            stmt = stmt.order_by(SessionDB.created_at.desc())
            stmt = stmt.limit(limit).offset(offset)

            result = await session.execute(stmt)
            sessions = result.all()

            # 转换为摘要格式
            summaries = []
            for s in sessions:
                summaries.append({
                    "session_id": s.session_id,
                    "query": s.query[:100] if s.query else "",
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                    "mode": s.mode,
                    "data_count": 0,
                    "visual_count": 0,
                    "has_error": s.error is not None,
                    "metadata": self._session_summary_metadata(s.session_metadata)
                })

            return summaries

    async def get_session_summary_metadata(
        self,
        session_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Return lightweight list metadata for the requested Web sessions."""
        unique_ids = list(dict.fromkeys(session_ids))
        if not unique_ids:
            return {}

        async with AsyncSession(self.engine) as session:
            stmt = select(
                SessionDB.session_id,
                SessionDB.session_metadata,
            ).where(SessionDB.session_id.in_(unique_ids))
            rows = (await session.execute(stmt)).all()

        return {
            row.session_id: self._session_summary_metadata(row.session_metadata)
            for row in rows
        }

    def _session_summary_metadata(self, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Keep list metadata lightweight while preserving fields used by list features."""
        if not isinstance(metadata, dict):
            return {}

        summary_keys = {
            "mode",
            "is_case",
            "case_marked_at",
            "source",
            "channel",
        }
        return {key: metadata[key] for key in summary_keys if key in metadata}

    async def get_session_stats_summary(self) -> Dict[str, Any]:
        """Return aggregate session stats without loading session rows into Python."""
        async with AsyncSession(self.engine) as session:
            stmt = select(
                func.count().label("total"),
                func.literal(0).label("total_data_count"),
                func.literal(0).label("total_visual_count"),
                func.count(SessionDB.error).label("error_count"),
            )
            result = await session.execute(stmt)
            row = result.one()

            return {
                "total": int(row.total or 0),
                "total_data_count": int(row.total_data_count or 0),
                "total_visual_count": int(row.total_visual_count or 0),
                "error_count": int(row.error_count or 0),
            }

    async def save_conversation_history(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]]
    ) -> bool:
        """
        保存会话的对话历史

        删除旧消息，插入新消息（原子操作）
        """
        import traceback

        try:
            # 使用原始连接（避免 ORM 层的问题）
            async with self.engine.connect() as conn:
                try:
                    # 开始事务
                    async with conn.begin():
                        # 先删除旧消息
                        stmt_delete = delete(SessionMessageDB.__table__).where(
                            SessionMessageDB.__table__.c.session_id == session_id
                        )
                        await conn.execute(stmt_delete)

                        # 批量插入新消息
                        for idx, msg in enumerate(conversation_history):
                            # 解析 role 和 msg_type
                            role, msg_type = self._resolve_role_and_type(msg)

                            timestamp = self._normalize_db_timestamp(
                                msg.get("timestamp"),
                                session_id=session_id,
                            )

                            msg_data = self._message_data(msg)
                            msg_metadata_converted = self._message_metadata(msg)
                            content = self._serialize_content(msg.get("content"))

                            # 使用 Core insert（注意：使用数据库列名）
                            stmt_insert = SessionMessageDB.__table__.insert().values(
                                session_id=session_id,
                                role=role,
                                msg_type=msg_type,
                                content=content,
                                data=msg_data,
                                timestamp=timestamp,
                                metadata=msg_metadata_converted,
                                sequence_number=idx
                            )
                            await conn.execute(stmt_insert)

                        logger.info(
                            "conversation_history_saved",
                            session_id=session_id,
                            message_count=len(conversation_history)
                        )

                        return True
                except Exception as e:
                    logger.error(
                        "failed_to_save_conversation_history",
                        session_id=session_id,
                        error=str(e),
                        error_type=type(e).__name__,
                        traceback=traceback.format_exc()
                    )
                    return False

        except Exception as e:
            logger.error(
                "failed_to_save_conversation_history",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            return False

    async def sync_conversation_history_incremental(
        self,
        session_id: str,
        conversation_history: List[Dict[str, Any]]
    ) -> bool:
        """
        增量同步会话消息。

        只追加数据库中尚不存在的尾部消息，避免每轮对话都执行
        DELETE FROM session_messages WHERE session_id = ... 导致锁等待和
        statement timeout。

        约定：
        - 当前会话历史是 append-only 时走增量路径。
        - 如果传入历史短于数据库已有消息，说明调用方可能做了压缩/截断，
          此方法不删除旧消息，交由显式全量重写接口处理。
        """
        if not conversation_history:
            return True

        started = time.monotonic()
        try:
            async with AsyncSession(self.engine) as session:
                count_started = time.monotonic()
                stmt = (
                    select(func.max(SessionMessageDB.sequence_number))
                    .where(SessionMessageDB.session_id == session_id)
                )
                result = await session.execute(stmt)
                max_seq = result.scalar()
                existing_count = (max_seq + 1) if max_seq is not None else 0
                count_ms = round((time.monotonic() - count_started) * 1000, 2)

                if existing_count >= len(conversation_history):
                    logger.debug(
                        "conversation_history_incremental_noop",
                        session_id=session_id,
                        existing_count=existing_count,
                        incoming_count=len(conversation_history),
                        count_ms=count_ms,
                        total_ms=round((time.monotonic() - started) * 1000, 2),
                        **self._pool_status(),
                    )
                    return True

                new_messages = conversation_history[existing_count:]

                rows_started = time.monotonic()
                rows = []
                for offset, msg in enumerate(new_messages, start=existing_count):
                    role, msg_type = self._resolve_role_and_type(msg)
                    timestamp = self._normalize_db_timestamp(
                        msg.get("timestamp"),
                        session_id=session_id,
                    )

                    msg_data = self._message_data(msg)

                    rows.append(
                        {
                            "session_id": session_id,
                            "role": role,
                            "msg_type": msg_type,
                            "content": self._serialize_content(msg.get("content")),
                            "data": msg_data,
                            "timestamp": timestamp,
                            "metadata": self._message_metadata(msg),
                            "sequence_number": offset,
                        }
                    )
                rows_build_ms = round((time.monotonic() - rows_started) * 1000, 2)

                insert_started = time.monotonic()
                await session.execute(SessionMessageDB.__table__.insert(), rows)
                insert_ms = round((time.monotonic() - insert_started) * 1000, 2)

                commit_started = time.monotonic()
                await session.commit()
                commit_ms = round((time.monotonic() - commit_started) * 1000, 2)

                logger.info(
                    "conversation_history_incremental_saved",
                    session_id=session_id,
                    existing_count=existing_count,
                    appended_count=len(new_messages),
                    incoming_count=len(conversation_history),
                    count_ms=count_ms,
                    rows_build_ms=rows_build_ms,
                    insert_ms=insert_ms,
                    commit_ms=commit_ms,
                    total_ms=round((time.monotonic() - started) * 1000, 2),
                    **self._pool_status(),
                )
                return True

        except Exception as e:
            logger.error(
                "failed_to_sync_conversation_history_incremental",
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__
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

                # 解析 role 和 msg_type
                role, msg_type = self._resolve_role_and_type(message)

                msg_data = self._message_data(message)
                msg_metadata = self._message_metadata(message)
                content = self._serialize_content(message.get("content"))

                db_msg = SessionMessageDB(
                    session_id=session_id,
                    role=role,
                    msg_type=msg_type,
                    content=content,
                    data=msg_data,
                    timestamp=self._normalize_db_timestamp(
                        message.get("timestamp"),
                        session_id=session_id,
                    ),
                    msg_metadata=msg_metadata,
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

    def _normalize_db_timestamp(self, value: Any, session_id: Optional[str] = None) -> datetime:
        """Return a naive UTC datetime for TIMESTAMP WITHOUT TIME ZONE columns."""
        if not value:
            return datetime.utcnow()

        try:
            if isinstance(value, datetime):
                parsed = value
            elif isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                raise TypeError(f"unsupported timestamp type: {type(value).__name__}")

            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (ValueError, TypeError) as exc:
            logger.warning(
                "invalid_timestamp_format",
                session_id=session_id,
                timestamp=value,
                error=str(exc),
            )
            return datetime.utcnow()

    async def get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量"""
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(func.count())
                .where(SessionMessageDB.session_id == session_id)
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    def _msg_to_dict(self, msg: SessionMessageDB, include_data: bool = True) -> Dict[str, Any]:
        """
        将数据库消息转换为前端字典格式

        同时包含 role（LLM 恢复用）和 type（前端展示用）
        content 直接从 JSONB 读取，无需反序列化

        ✅ 修复：始终使用数据库生成的唯一id，防止metadata中的旧id覆盖
        """
        msg_dict: Dict[str, Any] = {
            "role": msg.role,
            "type": msg.msg_type,
            "content": self._deserialize_content(msg.content),
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "id": f"msg_{msg.id}",  # ✅ 始终使用DB生成的唯一id
            "sequence_number": msg.sequence_number
        }
        if include_data and msg.data:
            msg_dict["data"] = msg.data
        if include_data and msg.msg_metadata:
            # ✅ 从metadata中排除id字段，避免覆盖DB生成的唯一id
            metadata_without_id = {k: v for k, v in msg.msg_metadata.items() if k != "id"}
            if metadata_without_id:  # 只有在有内容时才update
                msg_dict.update(metadata_without_id)
        return msg_dict

    def _message_row_to_context_dict(self, row: Any, include_data: bool = True) -> Dict[str, Any]:
        message = {
            "role": row.role,
            "type": row.msg_type,
            "content": self._deserialize_content(row.content),
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "id": f"msg_{row.id}",
            "sequence_number": row.sequence_number,
        }
        if include_data and getattr(row, "data", None):
            message["data"] = row.data
        attachments = self._message_attachments(getattr(row, "msg_metadata", None))
        if attachments:
            message["attachments"] = attachments
        return message

    async def get_llm_history_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Load transcript fields needed to rebuild LLM continuation context."""
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(
                    SessionMessageDB.id,
                    SessionMessageDB.role,
                    SessionMessageDB.msg_type,
                    SessionMessageDB.content,
                    SessionMessageDB.data,
                    SessionMessageDB.timestamp,
                    SessionMessageDB.sequence_number,
                )
                .where(SessionMessageDB.session_id == session_id)
                .order_by(SessionMessageDB.sequence_number)
            )
            result = await session.execute(stmt)
            return [
                self._message_row_to_context_dict(row)
                for row in result.all()
            ]

    async def get_llm_history_messages_after(
        self,
        session_id: str,
        after_sequence: int,
    ) -> List[Dict[str, Any]]:
        """Load LLM transcript rows appended after a compacted-history boundary."""
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(
                    SessionMessageDB.id,
                    SessionMessageDB.role,
                    SessionMessageDB.msg_type,
                    SessionMessageDB.content,
                    SessionMessageDB.data,
                    SessionMessageDB.timestamp,
                    SessionMessageDB.sequence_number,
                )
                .where(SessionMessageDB.session_id == session_id)
                .where(SessionMessageDB.sequence_number > after_sequence)
                .order_by(SessionMessageDB.sequence_number)
            )
            result = await session.execute(stmt)
            return [
                self._message_row_to_context_dict(row)
                for row in result.all()
            ]

    async def get_active_llm_compact_state(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Return persisted compact LLM state stored separately from display transcript."""
        metadata = await self.get_session_metadata(session_id)
        if not isinstance(metadata, dict):
            return None

        compact_state = metadata.get("llm_compact_state")
        if not isinstance(compact_state, dict):
            return None
        if compact_state.get("active") is False:
            return None
        if not isinstance(compact_state.get("messages"), list):
            return None
        if not isinstance(compact_state.get("source_until_sequence"), int):
            return None

        return compact_state

    async def get_session_metadata(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Return session metadata without loading messages or artifact columns."""
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(SessionDB.session_metadata)
                .where(SessionDB.session_id == session_id)
            )
            result = await session.execute(stmt)
            metadata = result.scalar_one_or_none()

        if not isinstance(metadata, dict):
            return None
        return metadata

    async def save_llm_compact_state(
        self,
        session_id: str,
        compact_state: Dict[str, Any],
    ) -> bool:
        """Persist compact LLM state in session metadata without touching transcript rows."""
        db_session = await self.get_session(session_id)
        if not db_session:
            return False

        metadata = db_session.session_metadata or {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        metadata["llm_compact_state"] = compact_state

        return await self.update_session(
            session_id,
            metadata=metadata,
        )

    async def get_display_history_messages_light(self, session_id: str) -> List[Dict[str, Any]]:
        """Load display text plus the small attachment contract, without result data."""
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(
                    SessionMessageDB.id,
                    SessionMessageDB.role,
                    SessionMessageDB.msg_type,
                    SessionMessageDB.content,
                    SessionMessageDB.msg_metadata,
                    SessionMessageDB.timestamp,
                    SessionMessageDB.sequence_number,
                )
                .where(SessionMessageDB.session_id == session_id)
                .order_by(SessionMessageDB.sequence_number)
            )
            result = await session.execute(stmt)
            return [
                self._message_row_to_context_dict(row, include_data=False)
                for row in result.all()
            ]

    def _message_row_to_light_dict(self, row: Any) -> Dict[str, Any]:
        """
        将数据库消息行转换为轻量级字典

        ⚠️ 轻量级策略：
        - 不查询 data 字段（避免传输大型 result 数据）
        - content 保持完整，content_preview 只用于工具名称识别
        - 性能优化：首屏恢复速度提升 3-5 倍
        """
        display_content = getattr(row, "display_content", None)
        content_preview = row.content_preview or ""
        has_full_display_content = display_content is not None

        msg_dict: Dict[str, Any] = {
            "role": row.role,
            "type": row.msg_type,
            "content": display_content if has_full_display_content else content_preview,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "id": f"msg_{row.id}",
            "sequence_number": row.sequence_number,
            "is_lightweight": True,
        }
        if not has_full_display_content:
            msg_dict["content_preview"] = content_preview
        attachments = self._message_attachments(getattr(row, "msg_metadata", None))
        if attachments:
            msg_dict["attachments"] = attachments

        # ✅ 从 content_preview 中提取工具名称（用于前端显示）
        # tool_use 消息的 content 通常包含："调用工具：check_order" 等信息
        if row.msg_type == "tool_use" and content_preview:
            content = content_preview
            # 尝试从 content 中提取工具名称（兼容多种格式）
            import re
            # 格式1：调用工具：tool_name
            # 格式2：执行【tool_name】
            # 格式3：Tool Use: tool_name
            tool_match = re.search(r'(?:调用工具|执行【|Tool Use:)\s*([^】:\n]+)', content)
            if tool_match:
                tool_name = tool_match.group(1).strip()
                msg_dict["data"] = {"tool_name": tool_name}

        return msg_dict

    async def get_messages_before(
        self,
        session_id: str,
        before_sequence: Optional[int] = None,
        limit: int = 30,
        include_data: bool = True
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
            if not include_data:
                content_text = cast(SessionMessageDB.content, Text)
                # Keep user/final text complete. Only process messages use a
                # preview; truncating JSON text can split a \uXXXX escape and
                # also cuts long final answers shown in restored sessions.
                stmt = (
                    select(
                        SessionMessageDB.id,
                        SessionMessageDB.role,
                        SessionMessageDB.msg_type,
                        SessionMessageDB.content,
                        SessionMessageDB.msg_metadata,
                        SessionMessageDB.timestamp,
                        SessionMessageDB.sequence_number,
                        case(
                            (
                                SessionMessageDB.msg_type.in_(FULL_DISPLAY_CONTENT_MSG_TYPES),
                                SessionMessageDB.content,
                            ),
                            else_=None,
                        ).label("display_content"),
                        func.substring(content_text, 1, 2000).label("content_preview"),
                    )
                    .where(SessionMessageDB.session_id == session_id)
                )
            else:
                stmt = (
                    select(SessionMessageDB)
                    .where(SessionMessageDB.session_id == session_id)
                )
            if before_sequence is not None:
                stmt = stmt.where(SessionMessageDB.sequence_number < before_sequence)

            stmt = stmt.order_by(SessionMessageDB.sequence_number.desc()).limit(limit)
            result = await session.execute(stmt)
            messages = list(reversed(result.scalars().all() if include_data else result.all()))

            oldest_sequence = messages[0].sequence_number if messages else None
            has_more = oldest_sequence is not None and oldest_sequence > 0

            return {
                "messages": [
                    self._msg_to_dict(msg, include_data=include_data) if include_data
                    else self._message_row_to_light_dict(msg)
                    for msg in messages
                ],
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
