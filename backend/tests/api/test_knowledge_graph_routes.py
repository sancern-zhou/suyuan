import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base, get_db
from app.knowledge_base.graph_models import (
    KnowledgeGraphEntity,
)
from app.knowledge_base.models import KnowledgeBase


@pytest.fixture
def graph_api(tmp_path, monkeypatch):
    from app.api import knowledge_graph_routes

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph-api.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(
                KnowledgeBase(
                    id="kb1",
                    name="图谱知识库",
                    owner_id="owner",
                    qdrant_collection="kb_kb1",
                    graph_enabled=True,
                )
            )
            session.add_all(
                [
                    KnowledgeGraphEntity(
                        id="candidate",
                        kb_id="kb1",
                        entity_type="Pollutant",
                        name="候选臭氧",
                        normalized_name="候选臭氧",
                        review_status="candidate",
                    ),
                    KnowledgeGraphEntity(
                        id="confirmed",
                        kb_id="kb1",
                        entity_type="Pollutant",
                        name="臭氧",
                        normalized_name="臭氧",
                        review_status="confirmed",
                    ),
                ]
            )
            await session.commit()

    import asyncio

    asyncio.run(setup())

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(
        knowledge_graph_routes.KnowledgeBasePermissions,
        "can_manage",
        staticmethod(lambda kb, user_id, is_admin=False: user_id == "owner"),
    )
    app = FastAPI()
    app.include_router(knowledge_graph_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    asyncio.run(engine.dispose())


def test_graph_query_defaults_to_trusted_review_statuses(graph_api):
    response = graph_api.post(
        "/api/knowledge-base/kb1/graph/query",
        json={"query": "", "depth": 2, "limit": 20},
    )

    assert response.status_code == 200
    assert {item["review_status"] for item in response.json()["entities"]} == {
        "confirmed"
    }


def test_graph_status_and_schema_are_scoped_to_knowledge_base(graph_api):
    status = graph_api.get("/api/knowledge-base/kb1/graph/status")
    schema = graph_api.get("/api/knowledge-base/kb1/graph/schema")

    assert status.status_code == 200
    assert status.json()["knowledge_base_id"] == "kb1"
    assert status.json()["entity_count"] == 2
    assert schema.status_code == 200


def test_graph_mutation_requires_manage_permission(graph_api):
    denied = graph_api.patch(
        "/api/knowledge-base/kb1/graph/entities/candidate",
        json={"review_status": "confirmed"},
        headers={"X-User-Id": "viewer"},
    )
    allowed = graph_api.patch(
        "/api/knowledge-base/kb1/graph/entities/candidate",
        json={"review_status": "confirmed"},
        headers={"X-User-Id": "owner"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["review_status"] == "confirmed"


def test_graph_query_validates_depth_limit(graph_api):
    response = graph_api.post(
        "/api/knowledge-base/kb1/graph/query",
        json={"query": "臭氧", "depth": 3},
    )

    assert response.status_code == 422
