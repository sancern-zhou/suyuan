from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.boards.routes import ManualVersionRequest, get_board_artifact_root, router
from app.boards.service import BoardVersionService
from app.conversations.dependencies import get_conversation_catalog
from app.db.database import Base, get_db


class _Catalog:
    async def require_read(self, session_id, user):
        return {"session_id": session_id, "user_id": user.id}

    async def require_write(self, session_id, user):
        return await self.require_read(session_id, user)


def test_manual_version_request_accepts_selected_source_version():
    request = ManualVersionRequest(
        base_revision=2,
        xml="<mxfile>V1</mxfile>",
        source_version_id="version-1",
    )

    assert request.source_version_id == "version-1"


@pytest.fixture
async def board_api(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        board = await BoardVersionService(session, storage_root=tmp_path / "artifacts").ensure_board(
            "board_session_api", title="API 画板"
        )
        await session.commit()
        board_id = board.id

    app = FastAPI()
    app.include_router(router)

    async def db_override():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_conversation_catalog] = lambda: _Catalog()
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id="user-1", username="tester", display_name="Tester", auth_source="mock"
    )
    app.dependency_overrides[get_board_artifact_root] = lambda: tmp_path / "artifacts"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, board_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_commit_and_history_contract(board_api):
    client, board_id = board_api
    response = await client.post(
        f"/api/boards/{board_id}/versions/manual",
        json={"base_revision": 0, "xml": "<mxfile>manual</mxfile>"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["board_id"] == board_id
    assert payload["revision"] == 1
    assert payload["version"]["source"] == "manual"

    history = await client.get(f"/api/boards/{board_id}/versions")
    assert history.status_code == 200
    assert [item["version_number"] for item in history.json()["versions"]] == [1]


@pytest.mark.asyncio
async def test_draft_and_version_xml_are_restorable_through_authorized_routes(board_api):
    client, board_id = board_api

    draft = await client.put(
        f"/api/boards/{board_id}/draft",
        json={"xml": "<mxfile>draft-layout</mxfile>"},
    )
    assert draft.status_code == 200
    draft_payload = draft.json()
    assert draft_payload["draft_revision"] == 1
    assert draft_payload["draft_xml_ref"]["read_url"].endswith(
        f"/api/boards/{board_id}/draft/xml"
    )

    draft_xml = await client.get(f"/api/boards/{board_id}/draft/xml")
    assert draft_xml.status_code == 200
    assert draft_xml.text == "<mxfile>draft-layout</mxfile>"

    committed = await client.post(
        f"/api/boards/{board_id}/versions/manual",
        json={"base_revision": 0, "xml": "<mxfile>accepted-layout</mxfile>"},
    )
    version_id = committed.json()["version"]["id"]
    version_xml = await client.get(f"/api/boards/{board_id}/versions/{version_id}/xml")
    assert version_xml.status_code == 200
    assert version_xml.text == "<mxfile>accepted-layout</mxfile>"


@pytest.mark.asyncio
async def test_stale_manual_commit_returns_conflict_contract(board_api):
    client, board_id = board_api
    first = await client.post(
        f"/api/boards/{board_id}/versions/manual",
        json={"base_revision": 0, "xml": "<mxfile>one</mxfile>"},
    )
    assert first.status_code == 200

    stale = await client.post(
        f"/api/boards/{board_id}/versions/manual",
        json={"base_revision": 0, "xml": "<mxfile>two</mxfile>"},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "board_version_conflict",
        "current_revision": 1,
    }


@pytest.mark.asyncio
async def test_restore_route_is_not_available(board_api):
    client, board_id = board_api

    response = await client.post(
        f"/api/boards/{board_id}/restore",
        json={"base_revision": 0, "version_id": "obsolete-version"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
