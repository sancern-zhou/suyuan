import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.db.knowledge_database import get_knowledge_db
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.scene_models import KnowledgeSchemaSuggestion
from app.knowledge_base.scene_schemas import SceneDraft


@pytest.fixture
def scene_api(tmp_path, monkeypatch):
    from app.api import knowledge_scene_routes
    from app.services.llm_service import llm_service

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
                    KnowledgeSchemaSuggestion(
                        id="suggestion1",
                        kb_id="kb1",
                        suggestion_type="business_object",
                        payload={
                            "key": "complaint",
                            "name": "投诉",
                            "description": "公众投诉记录",
                        },
                        evidence=[{"document_id": "doc1", "chunk_id": "chunk1"}],
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

    async def fake_json(prompt, max_retries=2):
        if "主体—关系—客体" in prompt:
            return {
                "subject": {"local_id": "s1", "entity_type": "enterprise", "name": "企业A"},
                "relation_type": "has_noise_source",
                "object": {"local_id": "o1", "entity_type": "noise_source", "name": "1号空压机"},
                "statement": "企业A的主要噪声源是1号空压机",
            }
        return {
            "kind": "conditional_constraint",
            "summary": "按昼夜时段评价",
            "applies_to": ["monitoring_result"],
            "conditions": ["存在昼夜时段"],
            "required_logic": ["使用对应限值"],
            "forbidden_logic": [],
        }

    monkeypatch.setattr(llm_service, "call_llm_with_json_response", fake_json)

    async def override_db():
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(knowledge_scene_routes.router, prefix="/api")
    app.dependency_overrides[get_knowledge_db] = override_db
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id="owner", username="owner", display_name="Owner"
    )
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


def test_business_rule_parse_confirm_and_archive(scene_api):
    draft = scene_api.post(
        "/api/knowledge-base/kb1/scene/discover",
        headers={"X-User-Id": "owner"},
        json={"scene_goal": "分析企业噪声投诉与整改闭环", "desired_questions": []},
    ).json()
    scene_api.post(
        f"/api/knowledge-base/kb1/scene/profiles/{draft['id']}/confirm",
        headers={"X-User-Id": "owner"},
        json={
            "business_objects": draft["business_objects"],
            "business_logic": draft["business_logic"],
            "ignored_content": [],
        },
    )
    parsed = scene_api.post(
        "/api/knowledge-base/kb1/scene/rules/parse",
        headers={"X-User-Id": "owner"},
        json={"text": "监测结果应按昼夜时段评价"},
    )
    assert parsed.status_code == 200
    assert parsed.json()["status"] == "draft"
    confirmed = scene_api.post(
        f"/api/knowledge-base/kb1/scene/rules/{parsed.json()['id']}/confirm",
        headers={"X-User-Id": "owner"},
        json={"expected_version": 1},
    )
    assert confirmed.json()["status"] == "confirmed"
    archived = scene_api.delete(
        f"/api/knowledge-base/kb1/scene/rules/{parsed.json()['id']}",
        headers={"X-User-Id": "owner"},
    )
    assert archived.json()["status"] == "archived"


def test_user_fact_is_confirmed_after_preview(scene_api):
    draft = scene_api.post(
        "/api/knowledge-base/kb1/scene/discover",
        headers={"X-User-Id": "owner"},
        json={"scene_goal": "分析企业噪声投诉与整改闭环", "desired_questions": []},
    ).json()
    scene_api.post(
        f"/api/knowledge-base/kb1/scene/profiles/{draft['id']}/confirm",
        headers={"X-User-Id": "owner"},
        json={
            "business_objects": draft["business_objects"],
            "business_logic": draft["business_logic"],
            "ignored_content": [],
        },
    )
    preview = scene_api.post(
        "/api/knowledge-base/kb1/scene/facts/parse",
        headers={"X-User-Id": "owner"},
        json={"text": "企业A的主要噪声源是1号空压机"},
    )
    assert preview.status_code == 200
    assert preview.json()["review_status"] == "draft"
    confirmed = scene_api.post(
        f"/api/knowledge-base/kb1/scene/facts/{preview.json()['id']}/confirm",
        headers={"X-User-Id": "owner"},
        json={"resolutions": {}},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["review_status"] == "confirmed"


def test_accept_suggestion_creates_draft_without_mutating_confirmed_schema(scene_api):
    draft = scene_api.post(
        "/api/knowledge-base/kb1/scene/discover",
        headers={"X-User-Id": "owner"},
        json={"scene_goal": "分析企业噪声投诉与整改闭环", "desired_questions": []},
    ).json()
    confirmed = scene_api.post(
        f"/api/knowledge-base/kb1/scene/profiles/{draft['id']}/confirm",
        headers={"X-User-Id": "owner"},
        json={
            "business_objects": draft["business_objects"],
            "business_logic": draft["business_logic"],
            "ignored_content": [],
        },
    ).json()

    response = scene_api.post(
        "/api/knowledge-base/kb1/scene/suggestions/suggestion1/accept",
        headers={"X-User-Id": "owner"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert any(item["key"] == "complaint" for item in payload["business_objects"])
    scene = scene_api.get("/api/knowledge-base/kb1/scene", headers={"X-User-Id": "owner"}).json()
    assert scene["scene_status"] == "awaiting_confirmation"
    assert scene["schema_version"] == confirmed["schema_version"]


def test_reject_suggestion_removes_it_from_pending_list(scene_api):
    response = scene_api.post(
        "/api/knowledge-base/kb1/scene/suggestions/suggestion1/reject",
        headers={"X-User-Id": "owner"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    pending = scene_api.get(
        "/api/knowledge-base/kb1/scene/suggestions",
        headers={"X-User-Id": "owner"},
    ).json()
    assert pending["suggestions"] == []
