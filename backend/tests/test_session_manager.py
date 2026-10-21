"""
会话管理系统单元测试
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil

from app.agent.session import SessionManager, Session, SessionState


@pytest.fixture
def temp_storage():
    """创建临时存储目录"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def session_manager(temp_storage):
    """创建SessionManager实例"""
    return SessionManager(storage_base_path=temp_storage, retention_days=7)


class TestSessionCreation:
    """测试会话创建"""

    def test_create_simple_session(self):
        """测试创建简单会话"""
        session = Session(
            session_id="session_001",
            query="测试查询"
        )

        assert session.session_id == "session_001"
        assert session.query == "测试查询"
        assert session.state == SessionState.ACTIVE
        assert len(session.data_ids) == 0

    def test_create_session_with_metadata(self):
        """测试创建带元数据的会话"""
        session = Session(
            session_id="session_001",
            query="分析广州O3污染",
            metadata={
                "location": "广州",
                "pollutant": "O3"
            }
        )

        assert session.metadata["location"] == "广州"
        assert session.metadata["pollutant"] == "O3"


class TestSessionSaveLoad:
    """测试会话保存和加载"""

    def test_save_session(self, session_manager):
        """测试保存会话"""
        session = Session(
            session_id="session_001",
            query="测试查询"
        )

        success = session_manager.save_session(session)
        assert success is True

        # 验证文件存在
        session_file = Path(session_manager.storage_path) / "session_001.json"
        assert session_file.exists()

    def test_load_session(self, temp_storage):
        """测试加载会话"""
        # 创建并保存会话
        manager1 = SessionManager(storage_base_path=temp_storage)
        session1 = Session(
            session_id="session_001",
            query="测试查询",
            data_ids=["data_001", "data_002"]
        )
        manager1.save_session(session1)

        # 创建新管理器并加载
        manager2 = SessionManager(storage_base_path=temp_storage)
        session2 = manager2.load_session("session_001")

        assert session2 is not None
        assert session2.session_id == "session_001"
        assert session2.query == "测试查询"
        assert len(session2.data_ids) == 2

    def test_load_nonexistent_session(self, session_manager):
        """测试加载不存在的会话"""
        session = session_manager.load_session("nonexistent_session")
        assert session is None


class TestSessionList:
    """测试会话列表"""

    def test_list_all_sessions(self, session_manager):
        """测试列出所有会话"""
        # 创建多个会话
        for i in range(3):
            session = Session(
                session_id=f"session_00{i+1}",
                query=f"查询{i+1}"
            )
            session_manager.save_session(session)

        sessions = session_manager.list_sessions()
        assert len(sessions) == 3

    def test_list_sessions_by_state(self, session_manager):
        """测试按状态列出会话"""
        # 创建不同状态的会话
        session1 = Session(session_id="session_001", query="查询1")
        session1.state = SessionState.ACTIVE
        session_manager.save_session(session1)

        session2 = Session(session_id="session_002", query="查询2")
        session2.state = SessionState.COMPLETED
        session_manager.save_session(session2)

        session3 = Session(session_id="session_003", query="查询3")
        session3.state = SessionState.FAILED
        session_manager.save_session(session3)

        # 查询活跃会话
        active_sessions = session_manager.list_sessions(state=SessionState.ACTIVE)
        assert len(active_sessions) == 1
        assert active_sessions[0].session_id == "session_001"

        # 查询完成会话
        completed_sessions = session_manager.list_sessions(state=SessionState.COMPLETED)
        assert len(completed_sessions) == 1

    def test_list_sessions_with_limit(self, session_manager):
        """测试限制会话数量"""
        # 创建5个会话
        for i in range(5):
            session = Session(
                session_id=f"session_00{i+1}",
                query=f"查询{i+1}"
            )
            session_manager.save_session(session)

        sessions = session_manager.list_sessions(limit=3)
        assert len(sessions) == 3


class TestSessionDelete:
    """测试会话删除"""

    def test_delete_session(self, session_manager):
        """测试删除会话"""
        # 创建会话
        session = Session(session_id="session_001", query="测试查询")
        session_manager.save_session(session)

        # 验证存在
        assert session_manager.get_session("session_001") is not None

        # 删除
        success = session_manager.delete_session("session_001")
        assert success is True

        # 验证已删除
        assert session_manager.get_session("session_001") is None

        # 验证文件已删除
        session_file = Path(session_manager.storage_path) / "session_001.json"
        assert not session_file.exists()


class TestSessionArchive:
    """测试会话归档"""

    def test_archive_session(self, session_manager):
        """测试归档会话"""
        # 创建会话
        session = Session(session_id="session_001", query="测试查询")
        session.state = SessionState.COMPLETED
        session_manager.save_session(session)

        # 归档
        success = session_manager.archive_session("session_001")
        assert success is True

        # 验证状态已更新
        archived_session = session_manager.get_session("session_001")
        assert archived_session.state == SessionState.ARCHIVED


class TestSessionCleanup:
    """测试会话清理"""

    def test_cleanup_expired_sessions(self, session_manager):
        """测试清理过期会话"""
        # 创建过期会话（修改updated_at）
        session1 = Session(session_id="session_001", query="过期会话")
        session1.state = SessionState.COMPLETED
        session1.updated_at = datetime.now() - timedelta(days=10)
        session_manager.save_session(session1, update_timestamp=False)  # 禁止更新时间戳

        # 创建未过期会话
        session2 = Session(session_id="session_002", query="正常会话")
        session2.state = SessionState.COMPLETED
        session_manager.save_session(session2)

        # 执行清理（retention_days=7）
        deleted_count = session_manager.cleanup_expired_sessions()

        # 验证：过期会话应被删除
        assert deleted_count == 1
        assert session_manager.get_session("session_001") is None
        assert session_manager.get_session("session_002") is not None

    def test_cleanup_does_not_delete_active_sessions(self, session_manager):
        """测试清理不会删除活跃会话"""
        # 创建过期但活跃的会话
        session = Session(session_id="session_001", query="活跃会话")
        session.state = SessionState.ACTIVE
        session.updated_at = datetime.now() - timedelta(days=10)
        session_manager.save_session(session, update_timestamp=False)  # 禁止更新时间戳

        # 执行清理
        deleted_count = session_manager.cleanup_expired_sessions()

        # 验证：活跃会话不应被删除
        assert deleted_count == 0
        assert session_manager.get_session("session_001") is not None


class TestSessionStats:
    """测试会话统计"""

    def test_get_session_stats(self, session_manager):
        """测试获取会话统计"""
        # 创建不同状态的会话
        states = [
            SessionState.ACTIVE,
            SessionState.COMPLETED,
            SessionState.COMPLETED,
            SessionState.FAILED
        ]

        for i, state in enumerate(states):
            session = Session(
                session_id=f"session_00{i+1}",
                query=f"查询{i+1}"
            )
            session.state = state
            session.data_ids = [f"data_{i+1}_1", f"data_{i+1}_2"]
            session_manager.save_session(session)

        stats = session_manager.get_session_stats()

        assert stats["total"] == 4
        assert stats["by_state"]["active"] == 1
        assert stats["by_state"]["completed"] == 2
        assert stats["by_state"]["failed"] == 1
        assert stats["total_data_count"] == 8  # 4 sessions * 2 data_ids


class TestSessionExportImport:
    """测试会话导出导入"""

    def test_export_session(self, session_manager, temp_storage):
        """测试导出会话"""
        # 创建会话
        session = Session(
            session_id="session_001",
            query="测试查询",
            data_ids=["data_001", "data_002"]
        )
        session_manager.save_session(session)

        # 导出
        export_path = f"{temp_storage}/export_001.json"
        success = session_manager.export_session("session_001", export_path)

        assert success is True
        assert Path(export_path).exists()

    def test_import_session(self, temp_storage):
        """测试导入会话"""
        # 创建并导出会话
        manager1 = SessionManager(storage_base_path=temp_storage)
        session1 = Session(
            session_id="session_001",
            query="测试查询",
            data_ids=["data_001"]
        )
        manager1.save_session(session1)

        export_path = f"{temp_storage}/export_001.json"
        manager1.export_session("session_001", export_path)

        # 创建新管理器并导入
        manager2 = SessionManager(storage_base_path=f"{temp_storage}/import")
        imported_session = manager2.import_session(export_path)

        assert imported_session is not None
        assert imported_session.session_id == "session_001"
        assert len(imported_session.data_ids) == 1


class TestSessionDuration:
    """测试会话时长"""

    def test_get_duration(self):
        """测试获取会话时长"""
        # 创建已完成的会话
        session = Session(session_id="session_001", query="测试查询")
        session.created_at = datetime.now() - timedelta(minutes=5)
        session.completed_at = datetime.now()

        duration = session.get_duration()

        # 验证时长约为5分钟（300秒）
        assert duration is not None
        assert 299 <= duration <= 301
