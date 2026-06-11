"""
会话管理器（数据库版本）

使用 PostgreSQL 存储会话，替代原来的文件系统存储。
保持 API 兼容，方便迁移。
"""

import json
import structlog
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from .models import Session, SessionInfo
from ...db.session_repository import get_session_repository

logger = structlog.get_logger()


class SessionManagerDB:
    """
    会话管理器（数据库版本）

    功能：
    1. 会话保存与加载（使用 PostgreSQL）
    2. 会话列表管理
    3. 自动清理过期会话
    4. 会话状态查询
    5. 内存缓存优化
    """

    def __init__(
        self,
        auto_save: bool = True,
        retention_days: int = 30,
        enable_cache: bool = True
    ):
        """
        初始化会话管理器

        Args:
            auto_save: 是否自动保存
            retention_days: 会话保留天数
            enable_cache: 是否启用内存缓存
        """
        self.auto_save = auto_save
        self.retention_days = retention_days
        self.enable_cache = enable_cache

        # 内存缓存：{session_id: Session}
        self.sessions: Dict[str, Session] = {}

        # 数据库仓库
        self.repository = get_session_repository()

        logger.info(
            "SessionManagerDB initialized",
            retention_days=retention_days,
            enable_cache=enable_cache
        )

    async def save_session(
        self,
        session: Session,
        update_timestamp: bool = True,
        save_messages: bool = True,
        force_full_history_rewrite: bool = False
    ) -> bool:
        """
        保存会话到数据库

        Args:
            session: 会话对象
            update_timestamp: 是否更新时间戳（默认True）
            save_messages: 是否同步 conversation_history
            force_full_history_rewrite: 是否显式全量重写消息历史。默认使用增量追加，
                避免每轮对话都 DELETE + INSERT 整个 session_messages 分区。

        Returns:
            是否保存成功
        """
        import traceback
        started = time.monotonic()
        try:
            # 更新时间戳（除非明确禁止）
            if update_timestamp:
                session.updated_at = datetime.now()

            # 保存到内存缓存
            if self.enable_cache:
                self.sessions[session.session_id] = session

            # 保存到数据库
            # 先尝试更新
            exists = await self.repository.get_session(session.session_id)

            if exists:
                metadata = self._merge_preserved_metadata(
                    getattr(exists, "session_metadata", None),
                    session.metadata,
                )
                # 更新现有会话
                await self.repository.update_session(
                    session.session_id,
                    query=session.query,
                    mode=metadata.get("mode"),
                    current_step=session.current_step,
                    current_expert=session.current_expert,
                    data_ids=session.data_ids,
                    visual_ids=session.visual_ids,
                    office_documents=session.office_documents,
                    error=session.error,
                    metadata=metadata
                )
            else:
                # 创建新会话
                await self.repository.create_session(
                    session_id=session.session_id,
                    query=session.query,
                    mode=session.metadata.get("mode"),
                    metadata=session.metadata,
                    office_documents=session.office_documents
                )

            # 保存对话历史：默认走增量追加，避免全量 DELETE + INSERT 阻塞 SSE 首包。
            if save_messages and session.conversation_history:
                logger.debug(
                    "saving_conversation_history",
                    session_id=session.session_id,
                    message_count=len(session.conversation_history),
                    force_full_history_rewrite=force_full_history_rewrite
                )
                if force_full_history_rewrite:
                    await self.repository.save_conversation_history(
                        session.session_id,
                        session.conversation_history
                    )
                else:
                    await self.repository.sync_conversation_history_incremental(
                        session.session_id,
                        session.conversation_history
                    )

            logger.info(
                "session_saved_to_db",
                session_id=session.session_id,
                message_count=len(session.conversation_history),
                save_messages=save_messages,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )

            return True

        except Exception as e:
            logger.error(
                "failed_to_save_session",
                session_id=session.session_id,
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc()
            )
            return False

    async def save_session_metadata(
        self,
        session: Session,
        update_timestamp: bool = True,
    ) -> bool:
        """Persist only session metadata and artifact references."""
        return await self.save_session(
            session,
            update_timestamp=update_timestamp,
            save_messages=False,
        )

    async def append_session_transcript(
        self,
        session: Session,
        update_timestamp: bool = True,
    ) -> bool:
        """Persist session metadata and append-only display transcript changes."""
        return await self.save_session(
            session,
            update_timestamp=update_timestamp,
            save_messages=True,
            force_full_history_rewrite=False,
        )

    async def replace_session_transcript(
        self,
        session: Session,
        update_timestamp: bool = True,
    ) -> bool:
        """Persist session metadata and explicitly replace the full transcript."""
        return await self.save_session(
            session,
            update_timestamp=update_timestamp,
            save_messages=True,
            force_full_history_rewrite=True,
        )

    @staticmethod
    def _merge_preserved_metadata(
        existing_metadata: Optional[Dict[str, Any]],
        incoming_metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge DB-owned runtime metadata that ordinary session saves must not erase."""
        merged = dict(incoming_metadata or {})
        if not isinstance(existing_metadata, dict):
            return merged

        for key in ("llm_compact_state",):
            if key in existing_metadata and key not in merged:
                merged[key] = existing_metadata[key]

        return merged

    async def load_session(
        self,
        session_id: str,
        include_messages: bool = True,
        use_cache: bool = False,
    ) -> Optional[Session]:
        """
        从数据库加载会话

        Args:
            session_id: 会话ID
            include_messages: 是否加载消息
            use_cache: 是否允许使用本 worker 的进程内缓存。默认 False，
                避免 4 worker 下读取到其他 worker 已更新前的旧历史。

        Returns:
            会话对象，如果不存在则返回None
        """
        started = time.monotonic()
        # 先检查内存缓存
        if use_cache and self.enable_cache and session_id in self.sessions:
            logger.info(
                "session_loaded_from_cache",
                session_id=session_id,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            return self.sessions[session_id]

        # 从数据库加载
        try:
            session_dict = await self.repository.get_session_with_messages(
                session_id,
                include_messages=include_messages
            )

            if not session_dict:
                logger.debug("session_not_found_in_db", session_id=session_id)
                return None

            # 转换为 Session 对象
            session = Session(
                session_id=session_dict["session_id"],
                query=session_dict["query"],
                created_at=datetime.fromisoformat(session_dict["created_at"]) if session_dict["created_at"] else None,
                updated_at=datetime.fromisoformat(session_dict["updated_at"]) if session_dict["updated_at"] else None,
                conversation_history=session_dict["conversation_history"],
                data_ids=session_dict["data_ids"],
                visual_ids=session_dict["visual_ids"],
                office_documents=session_dict.get("office_documents", []),
                metadata=session_dict["metadata"],
                error=session_dict["error"],
                current_step=session_dict.get("current_step"),
                current_expert=session_dict.get("current_expert")
            )

            # 加载到内存缓存
            if self.enable_cache:
                self.sessions[session_id] = session

            logger.info(
                "session_loaded_from_db",
                session_id=session_id,
                message_count=len(session.conversation_history),
                include_messages=include_messages,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )

            return session

        except Exception as e:
            logger.error(
                "failed_to_load_session",
                session_id=session_id,
                error=str(e)
            )
            return None

    def _session_from_dict(
        self,
        session_dict: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        metadata_updates: Optional[Dict[str, Any]] = None,
    ) -> Session:
        metadata = dict(session_dict["metadata"] or {})
        if metadata_updates:
            metadata.update(metadata_updates)

        return Session(
            session_id=session_dict["session_id"],
            query=session_dict["query"],
            created_at=datetime.fromisoformat(session_dict["created_at"]) if session_dict["created_at"] else None,
            updated_at=datetime.fromisoformat(session_dict["updated_at"]) if session_dict["updated_at"] else None,
            conversation_history=(
                conversation_history
                if conversation_history is not None
                else session_dict["conversation_history"]
            ),
            data_ids=session_dict["data_ids"],
            visual_ids=session_dict["visual_ids"],
            office_documents=session_dict.get("office_documents", []),
            metadata=metadata,
            error=session_dict["error"],
            current_step=session_dict.get("current_step"),
            current_expert=session_dict.get("current_expert")
        )

    @staticmethod
    def _max_sequence(messages: List[Dict[str, Any]]) -> Optional[int]:
        sequence_numbers = [
            msg.get("sequence_number")
            for msg in messages
            if isinstance(msg.get("sequence_number"), int)
        ]
        if not sequence_numbers:
            return None
        return max(sequence_numbers)

    @staticmethod
    def _compact_messages_for_restore(
        compact_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        messages = compact_state.get("messages")
        if not isinstance(messages, list):
            return []
        restored: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in {"user", "assistant"} or "content" not in msg:
                continue
            restored.append({
                "role": role,
                "content": msg.get("content"),
            })
        return restored

    async def save_llm_compact_state(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        *,
        source_until_sequence: int,
        token_estimate: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Persist compact LLM-only state without rewriting display transcript rows."""
        compact_state = {
            "active": True,
            "version": 1,
            "source_until_sequence": source_until_sequence,
            "messages": messages,
            "message_count": len(messages),
            "created_at": datetime.utcnow().isoformat(),
        }
        if token_estimate is not None:
            compact_state["token_estimate"] = token_estimate
        if reason:
            compact_state["reason"] = reason

        return await self.repository.save_llm_compact_state(
            session_id,
            compact_state,
        )

    async def load_session_for_llm(self, session_id: str) -> Optional[Session]:
        """Load session metadata plus lightweight transcript for LLM continuation."""
        started = time.monotonic()
        try:
            session_dict = await self.repository.get_session_with_messages(
                session_id,
                include_messages=False,
            )
            if not session_dict:
                logger.debug("session_not_found_in_db", session_id=session_id)
                return None

            from app.agent.memory.session_memory import SessionMemory

            compact_state = await self.repository.get_active_llm_compact_state(session_id)
            compact_source_sequence = None
            if compact_state:
                compact_source_sequence = compact_state.get("source_until_sequence")

            if isinstance(compact_source_sequence, int):
                raw_history = await self.repository.get_llm_history_messages_after(
                    session_id,
                    compact_source_sequence,
                )
                projected_incremental_history = SessionMemory.project_history_messages_for_llm(
                    raw_history,
                    session_id=session_id,
                )
                history = (
                    self._compact_messages_for_restore(compact_state)
                    + projected_incremental_history
                )
                max_incremental_sequence = self._max_sequence(raw_history)
                source_until_sequence = (
                    max_incremental_sequence
                    if max_incremental_sequence is not None
                    else compact_source_sequence
                )
                used_compact_state = True
            else:
                raw_history = await self.repository.get_llm_history_messages(session_id)
                history = SessionMemory.project_history_messages_for_llm(
                    raw_history,
                    session_id=session_id,
                )
                source_until_sequence = self._max_sequence(raw_history)
                used_compact_state = False

            session = self._session_from_dict(
                session_dict,
                history,
                metadata_updates={
                    "llm_source_until_sequence": source_until_sequence,
                    "llm_restored_from_compact_state": used_compact_state,
                },
            )

            logger.info(
                "session_loaded_for_llm",
                session_id=session_id,
                message_count=len(history),
                raw_message_count=len(raw_history),
                compact_state_used=used_compact_state,
                source_until_sequence=source_until_sequence,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            return session

        except Exception as e:
            logger.error(
                "failed_to_load_session_for_llm",
                session_id=session_id,
                error=str(e)
            )
            return None

    async def load_session_light(self, session_id: str) -> Optional[Session]:
        """Load session metadata plus full-length lightweight display transcript."""
        started = time.monotonic()
        try:
            session_dict = await self.repository.get_session_with_messages(
                session_id,
                include_messages=False,
            )
            if not session_dict:
                logger.debug("session_not_found_in_db", session_id=session_id)
                return None

            history = await self.repository.get_display_history_messages_light(session_id)
            session = self._session_from_dict(session_dict, history)

            logger.info(
                "session_loaded_light",
                session_id=session_id,
                message_count=len(history),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            return session

        except Exception as e:
            logger.error(
                "failed_to_load_session_light",
                session_id=session_id,
                error=str(e)
            )
            return None

    async def load_session_with_pagination(
        self,
        session_id: str,
        message_limit: int = 5,
        include_artifacts: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        加载会话（数据库层分页，只加载最新N条消息）

        相比 load_session，这个方法：
        1. 在数据库层进行分页查询，不加载全部消息到内存
        2. 返回分页元数据（has_more, total_count, oldest_sequence）
        3. 适用于大消息会话的快速恢复

        Args:
            session_id: 会话ID
            message_limit: 首次加载的消息数量（默认5）

        Returns:
            {
                "session": Session对象（conversation_history只包含最新N条）,
                "pagination": {
                    "has_more": bool,
                    "total_count": int,
                    "oldest_sequence": int | None
                }
            }
        """
        try:
            # 1. 先获取会话元数据（不加载消息）
            session_dict = await self.repository.get_session_with_messages(
                session_id,
                include_messages=False,  # 不加载消息
                include_artifacts=include_artifacts
            )

            if not session_dict:
                logger.debug("session_not_found_in_db", session_id=session_id)
                return None

            # 2. 获取消息总数
            total_count = await self.repository.get_message_count(session_id)

            # 3. 分页加载最新消息（在数据库层）
            if total_count > 0:
                # 加载最新 message_limit 条消息
                # 使用 get_messages_before 且不传 before，即获取最新消息
                message_result = await self.repository.get_messages_before(
                    session_id=session_id,
                    before_sequence=None,  # None 表示获取最新消息
                    limit=message_limit,
                    include_data=include_artifacts
                )
                session_dict["conversation_history"] = message_result["messages"]

                # 分页元数据
                pagination = {
                    "has_more": message_result["has_more"],
                    "total_count": message_result["total_count"],
                    "oldest_sequence": message_result["oldest_sequence"]
                }
            else:
                session_dict["conversation_history"] = []
                pagination = {
                    "has_more": False,
                    "total_count": 0,
                    "oldest_sequence": None
                }

            # 4. 转换为 Session 对象（只包含最新消息）
            session = Session(
                session_id=session_dict["session_id"],
                query=session_dict["query"],
                created_at=datetime.fromisoformat(session_dict["created_at"]) if session_dict["created_at"] else None,
                updated_at=datetime.fromisoformat(session_dict["updated_at"]) if session_dict["updated_at"] else None,
                conversation_history=session_dict["conversation_history"],  # 只包含最新N条
                data_ids=session_dict["data_ids"],
                visual_ids=session_dict["visual_ids"],
                office_documents=session_dict.get("office_documents", []),
                metadata=session_dict["metadata"],
                error=session_dict["error"],
                current_step=session_dict.get("current_step"),
                current_expert=session_dict.get("current_expert")
            )

            # Do not cache this partial Session. Continuation paths use load_session()
            # and expect cached sessions to contain the complete conversation history.
            logger.info(
                "session_loaded_with_pagination",
                session_id=session_id,
                loaded_messages=len(session_dict["conversation_history"]),
                total_messages=pagination["total_count"],
                has_more=pagination["has_more"]
            )

            return {
                "session": session,
                "pagination": pagination
            }

        except Exception as e:
            logger.error(
                "failed_to_load_session_with_pagination",
                session_id=session_id,
                error=str(e)
            )
            return None

    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话（优先从缓存，缓存未命中则从数据库加载）

        Args:
            session_id: 会话ID

        Returns:
            会话对象
        """
        if self.enable_cache and session_id in self.sessions:
            return self.sessions[session_id]
        return await self.load_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        try:
            # 从内存删除
            if self.enable_cache and session_id in self.sessions:
                del self.sessions[session_id]

            # 从数据库删除
            success = await self.repository.delete_session(session_id)

            if success:
                logger.info("session_deleted_from_db", session_id=session_id)

            return success

        except Exception as e:
            logger.error(
                "failed_to_delete_session",
                session_id=session_id,
                error=str(e)
            )
            return False

    async def list_sessions(
        self,
        mode: Optional[str] = None,
        limit: int = 100
    ) -> List[SessionInfo]:
        """
        列出所有会话

        Args:
            mode: 过滤模式
            limit: 限制数量

        Returns:
            会话信息列表
        """
        try:
            summaries = await self.repository.list_sessions(
                mode=mode,
                limit=limit
            )

            # 转换为 SessionInfo 对象
            session_infos = []
            for summary in summaries:
                session_infos.append(SessionInfo(
                    session_id=summary["session_id"],
                    query=summary["query"],
                    created_at=datetime.fromisoformat(summary["created_at"]) if summary["created_at"] else None,
                    updated_at=datetime.fromisoformat(summary["updated_at"]) if summary["updated_at"] else None,
                    data_count=summary["data_count"],
                    visual_count=summary["visual_count"],
                    has_error=summary["has_error"],
                    metadata=summary["metadata"]
                ))

            return session_infos

        except Exception as e:
            logger.error("failed_to_list_sessions", error=str(e))
            return []

    async def get_session_stats(self) -> Dict[str, Any]:
        """
        获取会话统计信息

        Returns:
            统计信息字典
        """
        return await self.repository.get_session_stats_summary()

    async def export_session(self, session_id: str, output_path: str) -> bool:
        """
        导出会话到指定路径

        Args:
            session_id: 会话ID
            output_path: 导出路径

        Returns:
            是否导出成功
        """
        session = await self.get_session(session_id)
        if not session:
            logger.warning("session_not_found_for_export", session_id=session_id)
            return False

        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            session_data = session.model_dump(mode='json')
            output_file.write_text(
                json.dumps(session_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info("session_exported", session_id=session_id, output_path=output_path)
            return True

        except Exception as e:
            logger.error("failed_to_export_session", session_id=session_id, error=str(e))
            return False

    async def import_session(self, input_path: str) -> Optional[Session]:
        """
        从文件导入会话

        Args:
            input_path: 导入路径

        Returns:
            会话对象，如果导入失败则返回None
        """
        try:
            input_file = Path(input_path)
            if not input_file.exists():
                logger.warning("import_file_not_found", input_path=input_path)
                return None

            session_data = json.loads(input_file.read_text(encoding='utf-8'))
            session = Session(**session_data)

            # Imported sessions are complete snapshots.
            await self.replace_session_transcript(session)

            logger.info("session_imported", session_id=session.session_id)
            return session

        except Exception as e:
            logger.error("failed_to_import_session", input_path=input_path, error=str(e))
            return None

    async def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话

        删除超过保留天数的会话。

        Returns:
            清理的会话数量
        """
        try:
            # 列出所有会话
            all_sessions = await self.repository.list_sessions(limit=10000)
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            deleted_count = 0

            for summary in all_sessions:
                updated_at = summary.get("updated_at")
                if not updated_at:
                    continue

                if isinstance(updated_at, str):
                    updated_at = datetime.fromisoformat(updated_at)

                if updated_at < cutoff_date:
                    success = await self.delete_session(summary["session_id"])
                    if success:
                        deleted_count += 1

            if deleted_count > 0:
                logger.info("cleaned_up_expired_sessions", count=deleted_count)

            return deleted_count

        except Exception as e:
            logger.error("failed_to_cleanup_expired_sessions", error=str(e))
            return 0

    def clear_cache(self):
        """清空内存缓存"""
        self.sessions.clear()
        logger.info("session_cache_cleared")


# 全局单例
_session_manager_db: Optional[SessionManagerDB] = None


def get_session_manager_db() -> SessionManagerDB:
    """获取数据库会话管理器单例"""
    global _session_manager_db
    if _session_manager_db is None:
        _session_manager_db = SessionManagerDB()
    return _session_manager_db
