"""Shared conversation board routes: snapshot, filtering, URL rewrite, auth."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import shared_conversation_routes as routes
from app.api import social_app_routes
from app.auth.models import CurrentUser
from app.conversations import adapters as conversations_adapters
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource


def _user(user_id="u1", username="alice", admin=False) -> CurrentUser:
    return CurrentUser(
        id=user_id,
        username=username,
        display_name="Alice",
        is_admin=admin,
    )


def _web_row(session_id="sess-1"):
    return ConversationCatalogRecord(
        session_id=session_id,
        owner_user_id="u1",
        owner_username="alice",
        owner_display_name="Alice",
        source=ConversationSource.WEB,
        mode="expert",
        title="",
        read_only_on_web=False,
        created_at=datetime(2026, 10, 15),
        updated_at=datetime(2026, 10, 15),
    )


_HISTORY = [
    {"role": "user", "content": "上月空气质量怎么样？"},
    {"role": "assistant", "type": "tool_use", "content": "调用工具: execute_sql_query"},
    {"role": "user", "type": "tool_result", "content": "查询成功"},
    {"type": "thought", "content": "分析思路"},
    {
        "type": "final",
        "role": "assistant",
        "content": "结论：优良天数上升。",
        "attachments": [
            {
                "file_id": "res-chart-1",
                "resource_id": "res-chart-1",
                "filename": "chart.png",
                "mime_type": "image/png",
                "file_type": "image",
                "url": "/api/social/app/sessions/sess-1/resources/res-chart-1/content",
            }
        ],
    },
]


class _FakeSession:
    def __init__(self):
        self.added = []
        self.records = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def get(self, model, key):
        return self.records.get(key)

    async def scalar(self, statement):
        return 0

    async def execute(self, statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))


def _patch_snapshot_sources(monkeypatch, row, history):
    class Catalog:
        repository = SimpleNamespace(get=None)

    async def _get(session_id):
        return row if row.session_id == session_id else None

    Catalog.repository = SimpleNamespace(get=_get)

    class WebAdapter:
        async def restore(self, catalog_row, **options):
            session = SimpleNamespace(model_dump=lambda **kwargs: {"conversation_history": history})
            return {"session": session, "pagination": {}}

    class Adapters:
        def get(self, source):
            return WebAdapter()

    monkeypatch.setattr(
        routes, "get_conversation_catalog", lambda: Catalog()
    )
    monkeypatch.setattr(conversations_adapters, "get_conversation_adapters", lambda: Adapters())
    monkeypatch.setattr(
        social_app_routes, "_app_resource_descriptors", _async_no_descriptors
    )


async def _async_no_descriptors(session_id, resource_ids):
    return []


def _client(user=None) -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.require_shared_identity] = lambda: user or _user()
    return TestClient(app)


def test_create_share_filters_history_and_rewrites_resource_urls(monkeypatch, tmp_path):
    row = _web_row()
    _patch_snapshot_sources(monkeypatch, row, _HISTORY)

    fake = _FakeSession()
    monkeypatch.setattr(routes, "async_session", lambda: fake)
    monkeypatch.setattr(routes, "_share_dir", lambda share_id: tmp_path / share_id)

    source_file = tmp_path / "source.png"
    source_file.write_bytes(b"png-bytes")
    fake_resource = SimpleNamespace(
        resource_id="res-chart-1",
        locator={"path": str(source_file)},
        media_type="image/png",
        label="chart.png",
    )

    class FakeResourceService:
        async def get_resource(self, session_id, resource_id, status=None):
            return fake_resource if resource_id == "res-chart-1" else None

    import app.agent.resources.resource_service as resource_service_module

    monkeypatch.setattr(
        resource_service_module.SessionResourceService,
        "database",
        classmethod(lambda cls: FakeResourceService()),
    )
    import app.utils.path_config as path_config

    monkeypatch.setattr(path_config, "get_data_registry", lambda: tmp_path)

    response = _client().post("/api/shared-conversations", json={"session_id": "sess-1"})
    assert response.status_code == 200
    body = response.json()

    assert body["title"] == "上月空气质量怎么样？"  # falls back to first question
    assert body["first_question"] == "上月空气质量怎么样？"
    assert body["message_count"] == 3  # user / thought / final; tool turns dropped

    record = fake.added[0]
    assert len(record.attachments) == 1
    assert (tmp_path / record.share_id / "res-chart-1.png").read_bytes() == b"png-bytes"
    snapshot_urls = [
        attachment["url"]
        for message in record.snapshot
        for attachment in message.get("attachments", [])
    ]
    assert snapshot_urls and all(
        url.startswith(f"/api/shared-conversations/{record.share_id}/resources/") for url in snapshot_urls
    )


def test_create_share_rejects_non_owner(monkeypatch):
    row = _web_row()
    row.owner_user_id = "someone-else"
    _patch_snapshot_sources(monkeypatch, row, _HISTORY)
    monkeypatch.setattr(routes, "async_session", lambda: _FakeSession())

    response = _client().post("/api/shared-conversations", json={"session_id": "sess-1"})
    assert response.status_code == 403


def test_create_share_rejects_empty_conversation(monkeypatch):
    row = _web_row()
    _patch_snapshot_sources(monkeypatch, row, [{"type": "thought", "content": "只有思考"}])
    monkeypatch.setattr(routes, "async_session", lambda: _FakeSession())

    response = _client().post("/api/shared-conversations", json={"session_id": "sess-1"})
    assert response.status_code == 400


def test_delete_share_owner_withdraws_admin_removes(monkeypatch):
    record = routes.SocialSharedConversation(
        share_id="s1", owner_user_id="u1", owner_username="alice",
        owner_display_name="Alice", source_session_id="sess-1", source_kind="web",
        mode="", title="t", first_question="q", message_count=1,
        snapshot=[], attachments=[], status=routes.SHARE_STATUS_ACTIVE,
        created_at=datetime(2026, 10, 15), updated_at=datetime(2026, 10, 15),
    )

    fake = _FakeSession()
    fake.records = {"s1": record}
    monkeypatch.setattr(routes, "async_session", lambda: fake)

    response = _client().delete("/api/shared-conversations/s1")
    assert response.status_code == 200
    assert record.status == routes.SHARE_STATUS_WITHDRAWN

    record.status = routes.SHARE_STATUS_ACTIVE
    admin_client = _client(_user(user_id="boss", username="boss-admin", admin=True))
    response = admin_client.delete("/api/shared-conversations/s1")
    assert response.status_code == 200
    assert record.status == routes.SHARE_STATUS_REMOVED
    assert record.removed_by == "boss-admin"


def test_delete_share_rejects_unrelated_user(monkeypatch):
    record = routes.SocialSharedConversation(
        share_id="s2", owner_user_id="other", owner_username="bob",
        owner_display_name="Bob", source_session_id="sess-2", source_kind="web",
        mode="", title="t", first_question="q", message_count=1,
        snapshot=[], attachments=[], status=routes.SHARE_STATUS_ACTIVE,
        created_at=datetime(2026, 10, 15), updated_at=datetime(2026, 10, 15),
    )
    fake = _FakeSession()
    fake.records = {"s2": record}
    monkeypatch.setattr(routes, "async_session", lambda: fake)

    response = _client().delete("/api/shared-conversations/s2")
    assert response.status_code == 403


def test_resource_endpoint_serves_copied_file(tmp_path, monkeypatch):
    (tmp_path / "res-chart-1.png").write_bytes(b"png-bytes")
    record = SimpleNamespace(
        status=routes.SHARE_STATUS_ACTIVE,
        attachments=[
            {
                "resource_id": "res-chart-1",
                "stored_name": "res-chart-1.png",
                "filename": "chart.png",
                "media_type": "image/png",
            }
        ],
    )

    async def _active(share_id):
        return record

    monkeypatch.setattr(routes, "_active_share", _active)
    monkeypatch.setattr(routes, "_share_dir", lambda share_id: tmp_path)

    response = _client().get("/api/shared-conversations/s1/resources/res-chart-1")
    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"].startswith("image/png")


def test_resource_endpoint_serves_copied_file_with_content_suffix(tmp_path, monkeypatch):
    (tmp_path / "res-chart-1.png").write_bytes(b"png-bytes")
    record = SimpleNamespace(
        status=routes.SHARE_STATUS_ACTIVE,
        attachments=[
            {
                "resource_id": "res-chart-1",
                "stored_name": "res-chart-1.png",
                "filename": "chart.png",
                "media_type": "image/png",
            }
        ],
    )

    async def _active(share_id):
        return record

    monkeypatch.setattr(routes, "_active_share", _active)
    monkeypatch.setattr(routes, "_share_dir", lambda share_id: tmp_path)

    response = _client().get("/api/shared-conversations/s1/resources/res-chart-1/content")
    assert response.status_code == 200
    assert response.content == b"png-bytes"


class _FakeTicketService:
    def issue(self, kind, resource_id):
        return f"ticket-for-{resource_id}"

    def verify(self, grant, kind, resource_id):
        return grant == f"ticket-for-{resource_id}"


def test_report_view_and_file_roundtrip(tmp_path, monkeypatch):
    report_dir = tmp_path / "report"
    (report_dir / "report_files").mkdir(parents=True)
    (report_dir / "report.html").write_text("<html>report</html>")
    (report_dir / "report_files" / "chart.png").write_bytes(b"png")
    record = SimpleNamespace(
        share_id="s1",
        status=routes.SHARE_STATUS_ACTIVE,
        attachments=[{"kind": "report_package", "base": "report/", "entry": "report.html"}],
    )

    async def _active(share_id):
        return record

    monkeypatch.setattr(routes, "_active_share", _active)
    monkeypatch.setattr(routes, "_share_dir", lambda share_id: tmp_path)
    import app.auth.share_access as share_access

    monkeypatch.setattr(share_access, "get_share_access_service", lambda: _FakeTicketService())

    client = _client()
    view = client.get("/api/shared-conversations/s1/report-view")
    assert view.status_code == 200
    url = view.json()["url"]
    assert url.startswith("/api/shared-conversations/s1/reports/_t/ticket-for-s1/report.html")

    entry = client.get(url)
    assert entry.status_code == 200
    assert b"report" in entry.content

    asset = client.get("/api/shared-conversations/s1/reports/_t/ticket-for-s1/report_files/chart.png")
    assert asset.status_code == 200
    assert asset.content == b"png"

    forged = client.get("/api/shared-conversations/s1/reports/_t/wrong/report.html")
    assert forged.status_code == 401

    escape = client.get("/api/shared-conversations/s1/reports/_t/ticket-for-s1/../report-view")
    assert escape.status_code in {401, 403, 404, 307}


def test_report_view_404_without_package(tmp_path, monkeypatch):
    record = SimpleNamespace(share_id="s2", status=routes.SHARE_STATUS_ACTIVE, attachments=[])

    async def _active(share_id):
        return record

    monkeypatch.setattr(routes, "_active_share", _active)
    response = _client().get("/api/shared-conversations/s2/report-view")
    assert response.status_code == 404


def test_require_shared_identity_accepts_app_bearer_and_rejects_anonymous(monkeypatch):
    import asyncio

    from app.social.app_identity import AppIdentity

    request = SimpleNamespace(state=SimpleNamespace(current_user=None))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.require_shared_identity(request, authorization=None))
    assert exc.value.status_code == 401

    identity = AppIdentity(
        account_id="acc-1", display_name="Alice", social_user_id="u1", expires_at=9999999999
    )
    monkeypatch.setattr(routes, "resolve_access_token", lambda token: identity)
    user = asyncio.run(routes.require_shared_identity(request, authorization="Bearer some-token"))
    assert user.id == "u1"
    assert user.display_name == "Alice"


def test_create_share_enforces_per_user_quota(monkeypatch):
    class _QuotaSession(_FakeSession):
        async def scalar(self, statement):
            return routes.MAX_ACTIVE_SHARES_PER_USER

    monkeypatch.setattr(routes, "async_session", lambda: _QuotaSession())

    response = _client().post("/api/shared-conversations", json={"session_id": "sess-1"})
    assert response.status_code == 429


def test_create_share_cleans_up_files_when_commit_fails(monkeypatch, tmp_path):
    row = _web_row()
    _patch_snapshot_sources(monkeypatch, row, _HISTORY)

    class _FailingSession(_FakeSession):
        async def commit(self):
            raise RuntimeError("db down")

    fake = _FailingSession()
    monkeypatch.setattr(routes, "async_session", lambda: fake)
    monkeypatch.setattr(routes, "_share_dir", lambda share_id: tmp_path / share_id)

    source_file = tmp_path / "source.png"
    source_file.write_bytes(b"png-bytes")
    fake_resource = SimpleNamespace(
        resource_id="res-chart-1",
        locator={"path": str(source_file)},
        media_type="image/png",
        label="chart.png",
    )

    class FakeResourceService:
        async def get_resource(self, session_id, resource_id, status=None):
            return fake_resource if resource_id == "res-chart-1" else None

    import app.agent.resources.resource_service as resource_service_module

    monkeypatch.setattr(
        resource_service_module.SessionResourceService,
        "database",
        classmethod(lambda cls: FakeResourceService()),
    )
    import app.utils.path_config as path_config

    monkeypatch.setattr(path_config, "get_data_registry", lambda: tmp_path)

    with pytest.raises(RuntimeError):
        _client().post("/api/shared-conversations", json={"session_id": "sess-1"})

    assert [p for p in tmp_path.iterdir() if p.is_dir()] == []


def test_require_shared_identity_propagates_token_error_status(monkeypatch):
    import asyncio

    request = SimpleNamespace(state=SimpleNamespace(current_user=None))

    def _disabled(token):
        raise HTTPException(status_code=403, detail="app_account_disabled")

    monkeypatch.setattr(routes, "resolve_access_token", _disabled)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.require_shared_identity(request, authorization="Bearer token"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "app_account_disabled"


def test_require_shared_identity_prefers_web_identity_over_bearer_header():
    import asyncio

    web_user = _user()
    request = SimpleNamespace(state=SimpleNamespace(current_user=web_user))

    def _must_not_be_called(token):
        raise AssertionError("App token path must not run for web identity")

    user = asyncio.run(
        routes.require_shared_identity(request, authorization="Bearer web-session-token")
    )
    assert user is web_user


def test_escaped_like_keyword_escapes_wildcards():
    assert routes._escaped_like_keyword("100%_good\\x") == "%100\\%\\_good\\\\x%"
    assert routes._escaped_like_keyword("普通查询") == "%普通查询%"


def test_deep_replace_walks_nested_strings():
    payload = {
        "a": "/api/social/app/sessions/s1/resources/r1/content",
        "b": [{"c": "unchanged", "d": 5}],
    }
    result = routes._deep_replace(payload, "/api/social/app/sessions/s1/resources/", "/x/")
    assert result["a"] == "/x/r1/content"
    assert result["b"][0]["c"] == "unchanged"
    assert result["b"][0]["d"] == 5


def test_visible_history_drops_tool_turns_and_long_thoughts():
    history = [
        {"type": "user", "content": "q"},
        {"type": "tool_use", "content": "tool"},
        {"type": "thought", "content": "x" * 5000},
        {"type": "thought", "content": "short thought"},
        {"type": "final", "content": "answer"},
    ]
    visible = routes._visible_history(history, set(social_app_routes._MOBILE_VISIBLE_HISTORY_TYPES))
    roles = [str(item.get("type") or item.get("role")) for item in visible]
    assert roles == ["user", "thought", "final"]
    assert visible[1]["content"] == "short thought"
