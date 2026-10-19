"""Web ingress, owner-scoped actions and durable local notification integration."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import assistant_routes as routes
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations import ConversationSource
from app.conversations.dependencies import get_conversation_catalog
from app.social.assistant_coaching import AssistantCoachingService
from app.social.assistant_coaching_models import AssistantCoachingOwnerDB, AssistantSuggestionDB
from app.social.assistant_followup_models import (
    AssistantOutboxDB,
    AssistantRunDB,
    AssistantTriggerDB,
)
from app.social.assistant_followups import AssistantFollowupService
from app.social.assistant_request import require_assistant_request
from app.social.assistant_task_models import AssistantTaskDB, AssistantTaskEventDB
from app.social.assistant_tasks import AssistantTaskService
from app.social.web_assistant import (
    social_runtime_mode,
    web_assistant_recipient,
    web_assistant_request,
)
from config.settings import settings

ALICE = CurrentUser(id="alice", username="alice", display_name="Alice")
BOB = CurrentUser(id="bob", username="bob", display_name="Bob", is_admin=True)


@pytest_asyncio.fixture
async def system(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")
    monkeypatch.setattr(settings, "assistant_followups_enabled", True)
    monkeypatch.setattr(settings, "assistant_analysis_enabled", False)
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'web.db').as_posix()}")
    tables = [
        AssistantTaskDB,
        AssistantTaskEventDB,
        AssistantTriggerDB,
        AssistantRunDB,
        AssistantOutboxDB,
        AssistantCoachingOwnerDB,
        AssistantSuggestionDB,
    ]
    async with engine.begin() as conn:
        for model in tables:
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tasks, followups = AssistantTaskService(factory), AssistantFollowupService(factory)
    capabilities = {"tool:read_file": {"kind": "tool", "target": "read_file", "revision": "v1"}}
    coaching = AssistantCoachingService(factory, lambda: capabilities)
    source = SimpleNamespace(owner_user_id="alice", source=ConversationSource.WEB)

    async def find(session_id):
        return source

    async def require_write(session_id, user):
        if source.owner_user_id != user.id:
            raise HTTPException(404, "session_not_found")
        return source

    catalog = SimpleNamespace(find=find, require_write=require_write)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.task_service] = lambda: tasks
    app.dependency_overrides[routes.followup_service] = lambda: followups
    app.dependency_overrides[routes.coaching_service] = lambda: coaching
    app.dependency_overrides[get_conversation_catalog] = lambda: catalog
    app.dependency_overrides[require_current_user] = lambda: ALICE
    with web_assistant_request("web-session", ALICE, "Track my inspection", "create-a"):
        task = await tasks.create(
            "default",
            "alice",
            require_assistant_request("web-session"),
            goal="Inspection review",
            completion_criteria="Verified findings delivered",
        )
        suggestion = (
            await coaching.propose(
                "default",
                "alice",
                require_assistant_request("web-session"),
                capability_id="tool:read_file",
                goal="Review uploaded notes",
                reason="Evidence is in the notes",
                suggested_prompt="Review the supplied notes",
            )
        )["suggestion"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            tasks=tasks,
            followups=followups,
            factory=factory,
            coaching=coaching,
            capabilities=capabilities,
            task=task,
            suggestion=suggestion,
            catalog=catalog,
            source=source,
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_http_owner_and_project_isolation_even_for_admin(system, monkeypatch):
    client = system.client
    assert len((await client.get("/api/assistant/tasks")).json()["tasks"]) == 1
    assert len((await client.get("/api/assistant/suggestions")).json()["suggestions"]) == 1
    system.app.dependency_overrides[require_current_user] = lambda: BOB
    assert (await client.get("/api/assistant/tasks")).json()["tasks"] == []
    assert (await client.get(f"/api/assistant/tasks/{system.task['task_id']}")).status_code == 404
    assert (
        await client.post(
            f"/api/assistant/suggestions/{system.suggestion['suggestion_id']}/actions",
            json={"action": "accept", "expected_version": 1},
        )
    ).status_code == 404
    system.app.dependency_overrides[require_current_user] = lambda: ALICE
    monkeypatch.setattr(settings, "project_id", "other")
    assert (await client.get("/api/assistant/tasks")).json()["tasks"] == []
    del system.app.dependency_overrides[require_current_user]
    assert (await client.get("/api/assistant/tasks")).status_code == 401


@pytest.mark.asyncio
async def test_feedback_complete_stop_and_conflicts_are_real_transactions(system):
    path = f"/api/assistant/tasks/{system.task['task_id']}/actions"
    response = await system.client.post(
        path,
        json={
            "action": "feedback",
            "expected_version": 1,
            "text": "The site has stopped production",
        },
    )
    assert response.status_code == 200
    task = (await system.client.get(path.removesuffix("/actions"))).json()["task"]
    assert task["version"] == 2 and "stopped production" in task["events"][-1]["user_message"]
    assert (
        await system.client.post(path, json={"action": "cancel", "expected_version": 1})
    ).status_code == 409
    assert (
        await system.client.post(path, json={"action": "complete", "expected_version": 2})
    ).status_code == 400
    assert (
        await system.client.post(
            path, json={"action": "cancel", "expected_version": 2, "owner_user_id": "bob"}
        )
    ).status_code == 422
    assert (
        await system.client.post(path, json={"action": "stop_followups", "expected_version": 2})
    ).status_code == 200
    response = await system.client.post(
        path,
        json={"action": "complete", "expected_version": 3, "text": "Verified findings delivered"},
    )
    assert response.json()["task"]["status"] == "completed"
    with pytest.raises(PermissionError):
        require_assistant_request("web-session")


@pytest.mark.asyncio
async def test_source_revalidation_and_disabled_tool_prevent_ui_bypass(system, monkeypatch):
    path = f"/api/assistant/tasks/{system.task['task_id']}/actions"
    system.source.source = ConversationSource.SOCIAL
    assert (
        await system.client.post(path, json={"action": "cancel", "expected_version": 1})
    ).status_code == 404
    system.source.source = ConversationSource.WEB
    from app.agent.prompts import tool_registry

    monkeypatch.setattr(
        tool_registry, "_get_project_disabled_tool_names", lambda: ["manage_assistant_tasks"]
    )
    assert (
        await system.client.post(path, json={"action": "cancel", "expected_version": 1})
    ).status_code == 403
    assert (await system.tasks.get("default", "alice", system.task["task_id"]))["version"] == 1


@pytest.mark.asyncio
async def test_accept_is_only_choice_and_dismiss_is_persistent(system):
    path = f"/api/assistant/suggestions/{system.suggestion['suggestion_id']}/actions"
    for _ in range(2):
        response = await system.client.post(path, json={"action": "accept", "expected_version": 1})
        assert response.status_code == 200
        assert response.json()["execution_state"] == "not_started"
        assert response.json()["suggestion"]["version"] == 2
    assert len(await system.tasks.list("default", "alice")) == 1
    assert (
        await system.client.post(path, json={"action": "dismiss", "expected_version": 2})
    ).status_code == 400
    system.capabilities.clear()
    assert (
        await system.client.post(path, json={"action": "accept", "expected_version": 2})
    ).status_code == 400


@pytest.mark.asyncio
async def test_web_reminder_delivery_and_inbox_share_durable_outbox(system, monkeypatch):
    from app.conversations import dependencies
    from app.social.assistant_analysis_agent import verify_analysis_owner
    from app.social.assistant_reminder_delivery import deliver_reminder

    monkeypatch.setattr(dependencies, "get_conversation_catalog", lambda: system.catalog)
    with web_assistant_request(
        "web-session", ALICE, "Remind me to check the inspection", "grant-a"
    ):
        await system.followups.create(
            "default",
            "alice",
            system.task["task_id"],
            require_assistant_request("web-session"),
            expected_version=1,
            kind="now",
            instructions="Check inspection feedback",
        )
    await system.followups.materialize("default")
    await system.followups.prepare_notifications("default")
    claimed = await system.followups.claim_notification("default")
    assert claimed is not None
    await system.followups.deliver("default", claimed, deliver_reminder)
    inbox = (await system.client.get("/api/assistant/notifications")).json()["notifications"]
    assert len(inbox) == 1 and "Check inspection feedback" in inbox[0]["content"]
    claim = {
        "task": {"owner_user_id": "alice"},
        "trigger": {
            "grant_session_id": "web-session",
            "recipient": web_assistant_recipient("alice"),
        },
    }
    await verify_analysis_owner(claim)
    system.source.source = ConversationSource.SOCIAL
    with pytest.raises(PermissionError):
        await verify_analysis_owner(claim)
    system.app.dependency_overrides[require_current_user] = lambda: BOB
    assert (await system.client.get("/api/assistant/notifications")).json()["notifications"] == []


@pytest.mark.asyncio
async def test_wrong_web_recipient_cannot_be_registered(system):
    from app.social.assistant_request import begin_assistant_request, end_assistant_request

    token = begin_assistant_request(
        "web-session", "Remind me", "wrong", delivery_user_id=web_assistant_recipient("bob")
    )
    try:
        with pytest.raises(PermissionError):
            await system.followups.create(
                "default",
                "alice",
                system.task["task_id"],
                require_assistant_request("web-session"),
                expected_version=1,
                kind="now",
                instructions="Reminder",
            )
    finally:
        end_assistant_request(token)


def test_social_toolset_coordinates_office_and_respects_project_disables(monkeypatch):
    from app.agent.prompts import tool_registry

    monkeypatch.setattr(settings, "project_id", "xuchang")
    social = tool_registry.get_tools_by_mode("social")
    assert "call_sub_agent" in social
    assert "execute_python" not in social
    assert "execute_python" in tool_registry.get_tools_by_mode("office")
    monkeypatch.setattr(tool_registry, "_get_project_disabled_tool_names", lambda: ["read_file"])
    assert "read_file" not in tool_registry.get_tools_by_mode("social")
    assert social_runtime_mode("assistant") == social_runtime_mode("social") == "social"
    assert social_runtime_mode("query") == "query"


@pytest.mark.asyncio
async def test_real_web_stream_uses_social_and_scopes_original_human_request(monkeypatch):
    from app.agent.session.models import Session
    from app.api import agent as routes
    from app.social import web_assistant

    session = Session(
        session_id="web-session", query="Previous query", metadata={"mode": "assistant"}
    )

    async def noop(*args, **kwargs):
        return True

    async def load(*args, **kwargs):
        return session

    @asynccontextmanager
    async def lock(*args, **kwargs):
        yield

    async def register(*args, **kwargs):
        return asyncio.Event()

    async def find(*args, **kwargs):
        return SimpleNamespace(mode="assistant")

    class Agent:
        async def analyze(self, **kwargs):
            assert kwargs["manual_mode"] == "social"
            assert kwargs["session_storage_mode"] == "assistant"
            assert kwargs["user_identifier"] == "server-memory-key"
            assert kwargs["social_memory_store"] is memory
            assert kwargs["runtime_metadata"]["authenticated_account"] == {
                "username": ALICE.username, "display_name": ALICE.display_name,
            }
            authority = require_assistant_request("web-session")
            assert authority.user_message == "Track my work"
            assert authority.delivery_user_id == web_assistant_recipient("alice")
            yield {"type": "start", "data": {}}

    memory = object()
    monkeypatch.setattr(
        web_assistant,
        "web_social_context",
        lambda user: {"user_identifier": "server-memory-key", "social_memory_store": memory},
    )
    monkeypatch.setattr(
        routes,
        "get_session_manager",
        lambda: SimpleNamespace(load_session_light=load, save_session_metadata=noop),
    )
    monkeypatch.setattr(routes, "session_advisory_lock", lock)
    monkeypatch.setattr(routes, "multi_expert_agent_instance", Agent())
    monkeypatch.setattr(routes, "_detached_run_stream", lambda request: None)
    monkeypatch.setattr(routes.cancellation_registry, "register", register)
    for name in ("attach_run_task", "arm_run_task", "unregister"):
        monkeypatch.setattr(routes.cancellation_registry, name, noop)

    class Request:
        async def json(self):
            return {}

    response = await routes.analyze_stream(
        routes.AgentAnalyzeRequest(
            query="Track my work",
            session_id="web-session",
            mode="assistant",
            user_id="spoofed",
            skill_ids=[],
            context_refs=[],
        ),
        Request(),
        user=ALICE,
        catalog=SimpleNamespace(find=find, require_write=noop),
    )
    chunks = [
        chunk.decode() if isinstance(chunk, bytes) else chunk
        async for chunk in response.body_iterator
    ]
    assert any("start" in chunk for chunk in chunks)
    assert not any("fatal_error" in chunk for chunk in chunks)
    with pytest.raises(PermissionError):
        require_assistant_request("web-session")


def test_memory_is_bound_to_server_user_and_uses_matching_store_identity(tmp_path, monkeypatch):
    from app.agent.memory import memory_store
    from app.social import user_preferences, web_assistant

    identifiers = []

    def store(**kwargs):
        identifiers.append(kwargs["user_id"])
        return object()

    class Preferences:
        def __init__(self, user_id):
            identifiers.append(user_id)
            self.soul_file = self.user_file = self.heartbeat_file = tmp_path / "profile.md"

        def get_preferences(self):
            return {}

        def load_soul_md(self):
            return ""

        def load_user_md(self):
            return ""

    monkeypatch.setattr(memory_store, "ImprovedMemoryStore", store)
    monkeypatch.setattr(user_preferences, "UserPreferences", Preferences)
    alice = web_assistant.web_social_context(ALICE)
    bob = web_assistant.web_social_context(BOB)
    assert alice["user_identifier"] != bob["user_identifier"]
    assert identifiers[0] == identifiers[1] == alice["user_identifier"]
