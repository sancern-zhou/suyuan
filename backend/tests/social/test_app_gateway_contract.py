import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import httpx
from fastapi import FastAPI

from app.social import app_identity
from app.social.session_mapper import SessionMapper
from app.api.social_app_routes import router as app_router
from app.api import social_app_routes
from app.auth.middleware import GatewayAuthenticationMiddleware
from app.agent.session.session_manager import SessionManager
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource
from config.settings import Settings


def configure_accounts(monkeypatch):
    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-signing-secret")
    monkeypatch.setattr(
        app_identity.settings,
        "app_accounts_json",
        json.dumps(
            {
                "alice": {"secret": "alice-secret", "name": "Alice"},
                "disabled": {"secret": "disabled-secret", "status": "disabled"},
            }
        ),
    )
    monkeypatch.setattr(app_identity.settings, "app_access_token_ttl_seconds", 3600)


def test_app_token_derives_server_owned_social_identity(monkeypatch):
    configure_accounts(monkeypatch)
    token, identity = app_identity.issue_access_token("alice", "alice-secret")

    resolved = app_identity.resolve_access_token(token)
    assert resolved.account_id == "alice"
    assert resolved.social_user_id == "app:android:alice"
    assert resolved.as_current_user().auth_source == "app"

    with pytest.raises(Exception):
        app_identity.resolve_access_token(token + "x")


def test_disabled_account_cannot_login(monkeypatch):
    configure_accounts(monkeypatch)
    with pytest.raises(Exception) as exc_info:
        app_identity.issue_access_token("disabled", "disabled-secret")
    assert getattr(exc_info.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_app_session_mapping_is_not_expired_after_24_hours(tmp_path):
    mapper = SessionMapper(data_dir=str(tmp_path))
    await mapper.save_mapping("app:android:alice", "social_session_alice")
    mapper._timestamp_cache["app:android:alice"] = datetime.now() - timedelta(days=30)
    mapper._timestamp_cache["qq:bot:bob"] = datetime.now() - timedelta(days=30)
    mapper._mappings["qq:bot:bob"] = "social_session_bob"

    assert await mapper.get_session("app:android:alice") == "social_session_alice"
    assert await mapper.get_session("qq:bot:bob") is None


@pytest.mark.asyncio
async def test_app_history_session_uses_catalog_not_current_session_mapping(monkeypatch):
    identity = app_identity.AppIdentity("alice", "Alice", "app:android:alice", 9999999999)
    row = ConversationCatalogRecord(
        session_id="social_session_old",
        owner_user_id=identity.social_user_id,
        owner_username="alice",
        owner_display_name="Alice",
        source=ConversationSource.SOCIAL,
        mode="social",
    )

    class Mapper:
        async def get_session(self, user_id):
            return "social_session_current"

    class Catalog:
        async def find(self, session_id):
            return row if session_id == row.session_id else None

        async def register_identity(self, **kwargs):
            return row

    async def fake_mapper(_request):
        return Mapper()

    monkeypatch.setattr(social_app_routes, "_loaded_session_mapper", fake_mapper)
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: Catalog())

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    assert await social_app_routes._ensure_session(request, identity, row.session_id) == row.session_id


@pytest.mark.asyncio
async def test_app_turn_persists_transcript_to_social_file_store(tmp_path, monkeypatch):
    from app.agent.session import session_manager as file_session_module

    manager = SessionManager(storage_base_path=str(tmp_path))
    monkeypatch.setattr(file_session_module, "_global_session_manager", manager)

    await social_app_routes._persist_app_turn(
        "social_session_history",
        "第一轮问题",
        [
            {"type": "user", "role": "user", "content": "第一轮问题"},
            {"type": "final", "role": "assistant", "content": "第一轮回复"},
        ],
    )
    await social_app_routes._persist_app_turn(
        "social_session_history",
        "第二轮问题",
        [
            {"type": "user", "role": "user", "content": "第二轮问题"},
            {"type": "final", "role": "assistant", "content": "第二轮回复"},
        ],
    )

    loaded = manager.load_session("social_session_history")
    assert loaded is not None
    assert [message["content"] for message in loaded.conversation_history] == [
        "第一轮问题", "第一轮回复", "第二轮问题", "第二轮回复"
    ]
    assert (tmp_path / "social_session_history.json").exists()


@pytest.mark.asyncio
async def test_app_stream_persists_complete_event_transcript(tmp_path, monkeypatch):
    from app.agent.session import session_manager as file_session_module

    manager = SessionManager(storage_base_path=str(tmp_path))
    monkeypatch.setattr(file_session_module, "_global_session_manager", manager)

    class FakeAgent:
        async def analyze(self, **kwargs):
            yield {"type": "start", "data": {"session_id": kwargs["session_id"]}}
            yield {"type": "streaming_text", "data": {"chunk": "流式回复", "is_complete": True}}
            yield {"type": "complete", "data": {"answer": "流式回复"}}

    async def fake_agent():
        return FakeAgent()

    async def fake_memory_store(_identity):
        return object()

    monkeypatch.setattr(social_app_routes, "_get_agent", fake_agent)
    monkeypatch.setattr(social_app_routes, "_get_memory_store", fake_memory_store)
    monkeypatch.setattr(social_app_routes, "_social_preferences", lambda _identity: {})

    identity = app_identity.AppIdentity("alice", "Alice", "app:android:alice", 9999999999)
    events = [
        event
        async for event in social_app_routes._stream_events(
            identity,
            "social_session_stream",
            "流式问题",
        )
    ]

    assert len(events) == 3
    loaded = manager.load_session("social_session_stream")
    assert loaded is not None
    assert [message["content"] for message in loaded.conversation_history] == [
        "流式问题", "流式回复"
    ]


@pytest.mark.asyncio
async def test_app_gateway_bypasses_company_boundary_but_requires_app_token(monkeypatch):
    configure_accounts(monkeypatch)
    app = FastAPI()
    settings = Settings(
        _env_file=None,
        auth_mode="company",
        trusted_gateway_networks="127.0.0.1/32",
    )

    class UnexpectedCompanyAuth:
        async def authenticate(self, *_args):
            raise AssertionError("App route must not call company auth")

    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=settings,
        auth_service=UnexpectedCompanyAuth(),
    )
    app.include_router(app_router)

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_response = await client.post(
            "/api/social/app/auth/login",
            json={"account_id": "alice", "account_secret": "alice-secret"},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        missing_token = await client.get("/api/social/app/me")
        assert missing_token.status_code == 401

        profile = await client.get(
            "/api/social/app/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert profile.status_code == 200
        assert profile.json()["social_user_id"] == "app:android:alice"
