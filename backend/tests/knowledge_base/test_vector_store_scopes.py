from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxWorker, VectorIndexTarget
from app.knowledge_base.models import KnowledgeBase, KnowledgeBaseStorageScope
from app.knowledge_base.permissions import KnowledgeBasePermissions
from app.knowledge_base.schemas import KnowledgeBaseCreate
from app.knowledge_base.vector_store_router import KnowledgeVectorStoreRouter


def test_vector_store_router_is_lazy_and_keeps_local_isolated(monkeypatch):
    created: list[tuple[str, str | None, int]] = []

    class FakeStore:
        def __init__(self, *, env_prefix, fallback_prefix=None, default_port=6333):
            created.append((env_prefix, fallback_prefix, default_port))

    monkeypatch.setattr("app.knowledge_base.vector_store_router.KnowledgeVectorStore", FakeStore)
    router = KnowledgeVectorStoreRouter()

    local = router.for_scope(KnowledgeBaseStorageScope.LOCAL)
    assert created == [("LOCAL_QDRANT", None, 6334)]
    assert router.for_scope("local") is local

    shared = router.for_scope("shared")
    assert created == [
        ("LOCAL_QDRANT", None, 6334),
        ("SHARED_QDRANT", "QDRANT", 6333),
    ]
    assert shared is not local


def test_new_knowledge_bases_default_to_local_vector_store():
    assert KnowledgeBaseCreate(name="本地库").vector_store_scope.value == "local"


@pytest.mark.asyncio
async def test_local_metadata_is_hidden_from_other_project_scopes(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scopes.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection, tables=[KnowledgeBase.__table__]
            )
        )
    async with factory() as session, session.begin():
        session.add_all(
            [
                KnowledgeBase(
                    id="shared", name="共享", qdrant_collection="shared",
                    vector_store_scope=KnowledgeBaseStorageScope.SHARED,
                ),
                KnowledgeBase(
                    id="local-a", name="项目 A", qdrant_collection="local-a",
                    vector_store_scope=KnowledgeBaseStorageScope.LOCAL, local_scope="project-a",
                ),
                KnowledgeBase(
                    id="local-b", name="项目 B", qdrant_collection="local-b",
                    vector_store_scope=KnowledgeBaseStorageScope.LOCAL, local_scope="project-b",
                ),
            ]
        )

    monkeypatch.setattr(
        "app.knowledge_base.permissions.get_local_knowledge_scope", lambda: "project-a"
    )
    async with factory() as session:
        visible = await KnowledgeBasePermissions.get_accessible_knowledge_bases(session)
        selected = await KnowledgeBasePermissions.filter_accessible_ids(
            session, ["shared", "local-a", "local-b"]
        )

    assert {kb.id for kb in visible} == {"shared", "local-a"}
    assert set(selected) == {"shared", "local-a"}
    await engine.dispose()


class _Repository:
    def __init__(self):
        self.item = type(
            "Item",
            (),
            {
                "id": "outbox-1", "kb_id": "local-kb", "record_type": "chunk",
                "record_id": "chunk-1", "operation": "upsert", "payload_version": 1,
                "payload": {"record_type": "chunk", "record_id": "chunk-1", "content": "测试"},
            },
        )()
        self.claimed = False
        self.completed = False

    async def claim_batch(self, _limit):
        if self.claimed:
            return []
        self.claimed = True
        return [self.item]

    async def is_latest(self, _item):
        return True

    async def mark_completed(self, _item_id):
        self.completed = True

    async def mark_retry(self, _item_id, _error):
        pytest.fail("a correctly routed write must not retry")


class _Store:
    def __init__(self):
        self.collections: list[str] = []

    async def create_collection(self, collection):
        self.collections.append(collection)

    async def upsert_records(self, collection, _records):
        self.collections.append(collection)


@pytest.mark.asyncio
async def test_outbox_worker_routes_local_target_to_local_store():
    repository = _Repository()
    local_store = _Store()
    shared_store = _Store()

    class Router:
        def for_scope(self, scope):
            return local_store if scope == "local" else shared_store

    worker = KnowledgeIndexOutboxWorker(
        repository=repository,
        vector_store=Router(),
        collection_resolver=lambda _kb_id: VectorIndexTarget("kb_local", "local"),
    )

    assert await worker.run_once() == 1
    assert repository.completed is True
    assert local_store.collections == ["kb_local", "kb_local"]
    assert shared_store.collections == []
