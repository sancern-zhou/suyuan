import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base, get_db
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.scene_schemas import SceneDraft


@pytest.fixture
def scene_api(tmp_path, monkeypatch):
    from app.api import knowledge_scene_routes

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scene-api.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all(
                [
                    KnowledgeBase(
                        id="empty",
                        name="空知识库",
                        owner_id="owner",
                        qdrant_collection="kb_empty",
                    ),
                    KnowledgeBase(
                        id="kb1",
                        name="噪声知识库",
                        owner_id="owner",
                        qdrant_collection="kb_kb1",
                    ),
                    Document(
                        id="doc1",
                        knowledge_base_id="kb1",
                        filename="noise.md",
                        status=DocumentStatus.COMPLETED,
                        ingestion_status="completed",
                        chunk_count=1,
                    ),
                ]
            )
            await session.flush()
            session.add(
                KnowledgeChunk(
                    id="chunk1",
                    kb_id="kb1",
                    document_id="doc1",
                    content_generation=1,
                    chunk_key="chunk1",
                    content_hash="hash1",
                    chunk_index=0,
                    content="企业拥有空压机",
                    embedding_text="企业拥有空压机",
                )
            )
            await session.commit()

    asyncio.run(setup())

    async def fake_discover(self, **kwargs):
        return SceneDraft.model_validate(
            {
                "scene_goal": kwargs["scene_goal"],
                "desired_questions": kwargs["desired_questions"],
                "business_objects": [
                    {"key": "enterprise", "name": "企业"},
                    {"key": "noise_source", "name": "噪声源"},
                ],
                "business_logic": [
                    {
                        "key": "enterprise_has_noise_source",
                        "statement": "企业拥有噪声源",
                        "source_key": "enterprise",
                        "relation_key": "has_noise_source",
                        "target_key": "noise_source",
                        "policy": "allowed",
                    }
                ],
                "source_document_ids": ["doc1"],
            }
        )

    monkeypatch.setattr(
        knowledge_scene_routes.SceneDiscoveryService,
        "discover",
        fake_discover,
    )
    monkeypatch.setattr(
        knowledge_scene_routes.KnowledgeBasePermissions,
        "can_manage",
        staticmethod(lambda kb, user_id, is_admin=False: user_id == "owner"),
    )

    async def override_db():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(knowledge_scene_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    asyncio.run(engine.dispose())


def test_scene_discovery_requires_document(scene_api):
    response = scene_api.post(
        "/api/knowledge-base/empty/scene/discover",
        headers={"X-User-Id": "owner"},
        json={"scene_goal": "分析企业噪声投诉与整改闭环", "desired_questions": []},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "representative_document_required"


def test_confirm_scene_compiles_schema_and_sets_ready(scene_api):
    draft = scene_api.post(
        "/api/knowledge-base/kb1/scene/discover",
        headers={"X-User-Id": "owner"},
        json={
            "scene_goal": "分析企业噪声投诉与整改闭环",
            "desired_questions": ["哪些噪声源导致投诉？"],
        },
    ).json()
    response = scene_api.post(
        f"/api/knowledge-base/kb1/scene/profiles/{draft['id']}/confirm",
        headers={"X-User-Id": "owner"},
        json={
            "business_objects": draft["business_objects"],
            "business_logic": draft["business_logic"],
            "ignored_content": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["scene_status"] == "ready"
    assert response.json()["schema_version"] == 1
