from datetime import datetime

import pytest

from app.agent.session.session_manager_db import SessionManagerDB


class FakeSessionRepository:
    def __init__(self):
        self.session_id = "assistant_session_1"
        self.exists = True
        self.full_messages = [
            {
                "type": "user",
                "role": "user",
                "content": f"message {index}",
                "timestamp": datetime(2026, 1, 1).isoformat(),
                "sequence_number": index,
            }
            for index in range(4)
        ]

    async def get_session(self, session_id):
        assert session_id == self.session_id
        return object() if self.exists else None

    async def update_session(self, session_id, **kwargs):
        assert session_id == self.session_id
        return True

    async def create_session(self, session_id, **kwargs):
        assert session_id == self.session_id
        return True

    async def sync_conversation_history_incremental(self, session_id, messages):
        assert session_id == self.session_id
        return True

    async def save_conversation_history(self, session_id, messages):
        assert session_id == self.session_id
        return True

    def _session_dict(self, include_messages):
        return {
            "session_id": self.session_id,
            "query": "test query",
            "created_at": datetime(2026, 1, 1).isoformat(),
            "updated_at": datetime(2026, 1, 1).isoformat(),
            "data_ids": [],
            "visual_ids": [],
            "office_documents": [],
            "metadata": {"mode": "assistant"},
            "error": None,
            "current_step": None,
            "current_expert": None,
            "conversation_history": self.full_messages[:] if include_messages else [],
        }

    async def get_session_with_messages(
        self,
        session_id,
        include_messages=True,
        include_artifacts=True,
    ):
        assert session_id == self.session_id
        return self._session_dict(include_messages)

    async def get_message_count(self, session_id):
        assert session_id == self.session_id
        return len(self.full_messages)

    async def get_messages_before(
        self,
        session_id,
        before_sequence=None,
        limit=30,
        include_data=True,
    ):
        assert session_id == self.session_id
        messages = self.full_messages[-limit:]
        return {
            "messages": messages,
            "has_more": True,
            "oldest_sequence": messages[0]["sequence_number"],
            "total_count": len(self.full_messages),
        }


def make_session_manager(repository):
    manager = SessionManagerDB.__new__(SessionManagerDB)
    manager.auto_save = True
    manager.retention_days = 30
    manager.enable_cache = True
    manager.sessions = {}
    manager.repository = repository
    return manager


@pytest.mark.asyncio
async def test_paginated_restore_does_not_cache_truncated_session():
    repository = FakeSessionRepository()
    manager = make_session_manager(repository)

    paginated = await manager.load_session_with_pagination(
        repository.session_id,
        message_limit=2,
    )

    assert paginated is not None
    assert len(paginated["session"].conversation_history) == 2

    full_session = await manager.load_session(repository.session_id)

    assert full_session is not None
    assert len(full_session.conversation_history) == 4


# ---------- delete_session 磁盘清理 ----------


class FakeDeletableRepository:
    def __init__(self, delete_result=True):
        self.delete_result = delete_result
        self.deleted_ids = []

    async def delete_session(self, session_id):
        self.deleted_ids.append(session_id)
        return self.delete_result


class _FakeResourceService:
    def __init__(self, result=True):
        self.result = result
        self.deleted = []

    async def delete_session_resources(self, session_id):
        self.deleted.append(session_id)
        return self.result


def _patch_resource_service(monkeypatch, fake):
    monkeypatch.setattr(
        "app.agent.resources.resource_service.SessionResourceService.database",
        lambda: fake,
    )


def _make_disk_layout(tmp_path, session_id="s1"):
    sessions_dir = tmp_path / "sessions"
    work_dir = sessions_dir / f"agent_session_{session_id}"
    content_dir = sessions_dir / "resource_content" / session_id
    (work_dir / "data").mkdir(parents=True)
    (work_dir / "data" / "output.txt").write_text("x", encoding="utf-8")
    content_dir.mkdir(parents=True)
    (content_dir / "publication.txt").write_text("y", encoding="utf-8")
    return sessions_dir, work_dir, content_dir


@pytest.mark.asyncio
async def test_delete_session_removes_disk_dirs(tmp_path, monkeypatch):
    sessions_dir, work_dir, content_dir = _make_disk_layout(tmp_path)
    monkeypatch.setattr("app.utils.path_config.get_sessions_dir", lambda: sessions_dir)
    resource = _FakeResourceService(result=True)
    _patch_resource_service(monkeypatch, resource)
    manager = make_session_manager(FakeDeletableRepository(delete_result=True))

    assert await manager.delete_session("s1") is True
    assert not work_dir.exists()
    assert not content_dir.exists()


@pytest.mark.asyncio
async def test_delete_session_db_failure_keeps_files(tmp_path, monkeypatch):
    sessions_dir, work_dir, content_dir = _make_disk_layout(tmp_path)
    monkeypatch.setattr("app.utils.path_config.get_sessions_dir", lambda: sessions_dir)
    resource = _FakeResourceService(result=False)
    _patch_resource_service(monkeypatch, resource)
    manager = make_session_manager(FakeDeletableRepository(delete_result=False))

    assert await manager.delete_session("s1") is False
    assert work_dir.exists()
    assert content_dir.exists()


@pytest.mark.asyncio
async def test_delete_session_survives_file_errors(tmp_path, monkeypatch):
    sessions_dir, work_dir, content_dir = _make_disk_layout(tmp_path)
    monkeypatch.setattr("app.utils.path_config.get_sessions_dir", lambda: sessions_dir)
    _patch_resource_service(monkeypatch, _FakeResourceService(result=True))

    def _broken_rmtree(path):
        raise OSError("permission denied")

    monkeypatch.setattr(
        "app.agent.session.session_manager_db.shutil.rmtree", _broken_rmtree
    )
    manager = make_session_manager(FakeDeletableRepository(delete_result=True))

    # DB 删除成功即返回 True；文件失败仅告警
    assert await manager.delete_session("s1") is True
    assert work_dir.exists()


@pytest.mark.asyncio
async def test_delete_session_rejects_unsafe_session_id(tmp_path, monkeypatch):
    sessions_dir, work_dir, content_dir = _make_disk_layout(tmp_path)
    sessions_dir.joinpath("outside").mkdir()
    (sessions_dir / "outside" / "keep.txt").write_text("z", encoding="utf-8")
    monkeypatch.setattr("app.utils.path_config.get_sessions_dir", lambda: sessions_dir)
    _patch_resource_service(monkeypatch, _FakeResourceService(result=True))
    manager = make_session_manager(FakeDeletableRepository(delete_result=True))

    # 含路径分隔符/点号的 id 不过白名单，磁盘不动
    assert await manager.delete_session("../outside") is True
    assert work_dir.exists()
    assert content_dir.exists()
    assert (sessions_dir / "outside" / "keep.txt").exists()


@pytest.mark.asyncio
async def test_save_session_refreshes_catalog_recency(monkeypatch):
    from app.agent.session.models import Session

    touched = []

    class FakeCatalogRepository:
        async def touch(self, session_id):
            touched.append(session_id)
            return True

    monkeypatch.setattr(
        "app.conversations.repository.ConversationCatalogRepository",
        FakeCatalogRepository,
    )

    repository = FakeSessionRepository()
    manager = make_session_manager(repository)
    session = Session(session_id=repository.session_id, query="q")
    session.conversation_history = [{"type": "user", "content": "hi", "timestamp": "t"}]

    assert await manager.append_session_transcript(session) is True
    assert touched == [repository.session_id]


@pytest.mark.asyncio
async def test_save_session_skips_catalog_touch_without_timestamp_update(monkeypatch):
    from app.agent.session.models import Session

    touched = []

    class FakeCatalogRepository:
        async def touch(self, session_id):
            touched.append(session_id)
            return True

    monkeypatch.setattr(
        "app.conversations.repository.ConversationCatalogRepository",
        FakeCatalogRepository,
    )

    repository = FakeSessionRepository()
    manager = make_session_manager(repository)
    session = Session(session_id=repository.session_id, query="q")

    assert await manager.save_session_metadata(session, update_timestamp=False) is True
    assert touched == []


@pytest.mark.asyncio
async def test_catalog_touch_failure_does_not_break_save(monkeypatch):
    from app.agent.session.models import Session

    class BrokenCatalogRepository:
        async def touch(self, session_id):
            raise RuntimeError("catalog_unavailable")

    monkeypatch.setattr(
        "app.conversations.repository.ConversationCatalogRepository",
        BrokenCatalogRepository,
    )

    repository = FakeSessionRepository()
    manager = make_session_manager(repository)
    session = Session(session_id=repository.session_id, query="q")

    assert await manager.save_session_metadata(session) is True
