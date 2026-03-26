"""
会话管理器

负责会话的保存、恢复、列表、删除等核心功能。
"""

import json
import structlog
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from .models import Session, SessionInfo, SessionState

logger = structlog.get_logger()


class SessionManager:
    """
    会话管理器

    功能：
    1. 会话保存与加载
    2. 会话列表管理
    3. 自动清理过期会话
    4. 会话状态查询
    """

    def __init__(
        self,
        storage_base_path: str = "backend_data_registry/sessions",
        auto_save: bool = True,
        retention_days: int = 30
    ):
        """
        初始化会话管理器

        Args:
            storage_base_path: 存储基础路径
            auto_save: 是否自动保存
            retention_days: 会话保留天数
        """
        self.storage_path = Path(storage_base_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.auto_save = auto_save
        self.retention_days = retention_days

        # 内存缓存：{session_id: Session}
        self.sessions: Dict[str, Session] = {}

        logger.info(
            f"SessionManager initialized with storage path: {self.storage_path}, "
            f"retention_days: {retention_days}"
        )

    def save_session(self, session: Session, update_timestamp: bool = True) -> bool:
        """
        保存会话到磁盘

        Args:
            session: 会话对象
            update_timestamp: 是否更新时间戳（默认True）

        Returns:
            是否保存成功
        """
        try:
            # 更新时间戳（除非明确禁止）
            if update_timestamp:
                session.updated_at = datetime.now()

            # 保存到内存缓存
            self.sessions[session.session_id] = session

            # 保存到磁盘
            session_file = self._get_session_file_path(session.session_id)
            session_data = session.model_dump(mode='json')

            session_file.write_text(
                json.dumps(session_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info(
                f"Session saved: {session.session_id} "
                f"(state: {session.state.value}, data_count: {len(session.data_ids)})"
            )

            return True

        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[Session]:
        """
        从磁盘加载会话

        Args:
            session_id: 会话ID

        Returns:
            会话对象，如果不存在则返回None
        """
        # 先检查内存缓存
        if session_id in self.sessions:
            return self.sessions[session_id]

        # 从磁盘加载
        session_file = self._get_session_file_path(session_id)

        if not session_file.exists():
            logger.debug(f"Session not found: {session_id}")
            return None

        try:
            session_data = json.loads(session_file.read_text(encoding='utf-8'))
            session = Session(**session_data)

            # 加载到内存缓存
            self.sessions[session_id] = session

            logger.info(f"Session loaded: {session_id} (state: {session.state.value})")

            return session

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话（优先从缓存）

        Args:
            session_id: 会话ID

        Returns:
            会话对象
        """
        if session_id in self.sessions:
            return self.sessions[session_id]
        return self.load_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        try:
            # 从内存删除
            if session_id in self.sessions:
                del self.sessions[session_id]

            # 从磁盘删除
            session_file = self._get_session_file_path(session_id)
            if session_file.exists():
                session_file.unlink()

            logger.info(f"Session deleted: {session_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False

    def list_sessions(
        self,
        state: Optional[SessionState] = None,
        limit: Optional[int] = None
    ) -> List[SessionInfo]:
        """
        列出所有会话

        Args:
            state: 过滤状态
            limit: 限制数量

        Returns:
            会话信息列表
        """
        sessions = []

        # 匹配所有类型的会话文件：session_*, assistant_session_*, query_session_*, report_session_*
        for pattern in ["session_*.json", "assistant_session_*.json", "query_session_*.json", "report_session_*.json"]:
            for file_path in self.storage_path.glob(pattern):
                try:
                    session_data = json.loads(file_path.read_text(encoding='utf-8'))
                    session = Session(**session_data)

                    # 状态过滤
                    if state and session.state != state:
                        continue

                    sessions.append(session.to_summary())

                except Exception as e:
                    logger.error(f"Failed to read session file {file_path}: {e}")

        # 按更新时间降序排序
        sessions.sort(key=lambda x: x.updated_at, reverse=True)

        # 限制数量
        if limit:
            sessions = sessions[:limit]

        return sessions

    def archive_session(self, session_id: str) -> bool:
        """
        归档会话

        Args:
            session_id: 会话ID

        Returns:
            是否归档成功
        """
        session = self.get_session(session_id)

        if not session:
            logger.warning(f"Session not found for archiving: {session_id}")
            return False

        # 更新状态为归档
        session.state = SessionState.ARCHIVED
        session.updated_at = datetime.now()

        return self.save_session(session)

    def cleanup_expired_sessions(self) -> int:
        """
        清理过期会话

        删除超过保留天数且状态为completed/failed/archived的会话。

        Returns:
            删除的会话数量
        """
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        deleted_count = 0

        # 匹配所有类型的会话文件：session_*, assistant_session_*, query_session_*, report_session_*
        for pattern in ["session_*.json", "assistant_session_*.json", "query_session_*.json", "report_session_*.json"]:
            for file_path in self.storage_path.glob(pattern):
                try:
                    session_data = json.loads(file_path.read_text(encoding='utf-8'))
                    session = Session(**session_data)

                    # 检查是否过期
                    if session.updated_at < cutoff_date:
                        # 只删除已完成或失败的会话
                        if session.state in [
                            SessionState.COMPLETED,
                            SessionState.FAILED,
                            SessionState.ARCHIVED
                        ]:
                            self.delete_session(session.session_id)
                            deleted_count += 1

                except Exception as e:
                    logger.error(f"Failed to process session file {file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired sessions")

        return deleted_count

    def get_active_sessions(self) -> List[SessionInfo]:
        """获取所有活跃会话"""
        return self.list_sessions(state=SessionState.ACTIVE)

    def get_session_stats(self) -> Dict:
        """
        获取会话统计信息

        Returns:
            统计信息字典
        """
        all_sessions = self.list_sessions()

        stats = {
            "total": len(all_sessions),
            "by_state": {
                "active": 0,
                "paused": 0,
                "completed": 0,
                "failed": 0,
                "archived": 0
            },
            "total_data_count": 0,
            "total_visual_count": 0
        }

        for session_info in all_sessions:
            stats["by_state"][session_info.state.value] += 1
            stats["total_data_count"] += session_info.data_count
            stats["total_visual_count"] += session_info.visual_count

        return stats

    def _get_session_file_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.storage_path / f"{session_id}.json"

    def export_session(self, session_id: str, output_path: str) -> bool:
        """
        导出会话到指定路径

        Args:
            session_id: 会话ID
            output_path: 导出路径

        Returns:
            是否导出成功
        """
        session = self.get_session(session_id)

        if not session:
            logger.warning(f"Session not found for export: {session_id}")
            return False

        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            session_data = session.model_dump(mode='json')
            output_file.write_text(
                json.dumps(session_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            logger.info(f"Session exported: {session_id} -> {output_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to export session {session_id}: {e}")
            return False

    def import_session(self, input_path: str) -> Optional[Session]:
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
                logger.warning(f"Import file not found: {input_path}")
                return None

            session_data = json.loads(input_file.read_text(encoding='utf-8'))
            session = Session(**session_data)

            # 保存到本地
            self.save_session(session)

            logger.info(f"Session imported: {session.session_id}")

            return session

        except Exception as e:
            logger.error(f"Failed to import session from {input_path}: {e}")
            return None


# 全局会话管理器实例（单例模式）
_global_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例"""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager()
    return _global_session_manager
