"""Selected nanobot goal-authority cases plus local transactional integration tests."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.social.assistant_request import (
    begin_assistant_request,
    end_assistant_request,
    require_assistant_request,
)
from app.social.assistant_task_models import AssistantTaskDB, AssistantTaskEventDB
from app.social.assistant_tasks import AssistantTaskService, TaskConflict, TaskNotFound
from app.tools.social.assistant_tasks.tool import ManageAssistantTasksTool


@contextmanager
def user_request(
    session_id="session-a", message="Prepare the meeting analysis", request_id="request-a"
):
    token = begin_assistant_request(session_id, message, request_id)
    try:
        yield require_assistant_request(session_id)
    finally:
        end_assistant_request(token)


@pytest_asyncio.fixture
async def database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'matters.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(AssistantTaskDB.__table__.create)
        await conn.run_sync(AssistantTaskEventDB.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield SimpleNamespace(service=AssistantTaskService(factory), factory=factory, engine=engine)
    await engine.dispose()


async def create(
    service, owner="alice", project="p1", request_id="request-a", goal="Meeting analysis"
):
    with user_request(request_id=request_id) as request:
        return await service.create(
            project, owner, request, goal=goal, completion_criteria="Deliver the checked analysis"
        )


def test_background_default_denial_and_exception_cleanup():
    with pytest.raises(PermissionError):
        require_assistant_request("session-a")
    with pytest.raises(RuntimeError):
        with user_request():
            assert require_assistant_request("session-a").request_id == "request-a"
            with pytest.raises(PermissionError):
                require_assistant_request("heartbeat-a")
            raise RuntimeError("interrupted")
    with pytest.raises(PermissionError):
        require_assistant_request("session-a")


def test_empty_input_does_not_authorize_or_leak_a_previous_request():
    with user_request():
        token = begin_assistant_request("session-a", "   ")
        try:
            with pytest.raises(PermissionError):
                require_assistant_request("session-a")
        finally:
            end_assistant_request(token)
        assert require_assistant_request("session-a").request_id == "request-a"


@pytest.mark.asyncio
async def test_inherited_background_task_cannot_keep_authority_after_turn():
    continue_child = asyncio.Event()

    async def child():
        await continue_child.wait()
        with pytest.raises(PermissionError):
            require_assistant_request("session-a")

    with user_request():
        task = asyncio.create_task(child())
    continue_child.set()
    await task


@pytest.mark.asyncio
async def test_nested_request_restores_parent_without_granting_sibling():
    with user_request() as parent:
        with user_request("session-b", request_id="other"):
            with pytest.raises(PermissionError):
                require_assistant_request("session-a")
        assert require_assistant_request("session-a") == parent


@pytest.mark.asyncio
async def test_persists_restart_and_repeated_create_is_idempotent(database):
    first = await create(database.service)
    second = await create(AssistantTaskService(database.factory))
    assert second["task_id"] == first["task_id"]
    stored = await AssistantTaskService(database.factory).get("p1", "alice", first["task_id"])
    assert stored["status"] == "ready"
    assert len(stored["events"]) == 1
    assert stored["events"][0]["user_message"] == "Prepare the meeting analysis"


@pytest.mark.asyncio
async def test_concurrent_create_is_one_task_and_one_event(database):
    results = await asyncio.gather(*(create(database.service) for _ in range(4)))
    assert len({task["task_id"] for task in results}) == 1
    task = await database.service.get("p1", "alice", results[0]["task_id"])
    assert len(task["events"]) == 1


@pytest.mark.asyncio
async def test_owner_and_project_isolation_in_all_operations(database):
    task = await create(database.service)
    for project, owner in [("p1", "bob"), ("p2", "alice")]:
        assert await database.service.list(project, owner) == []
        with pytest.raises(TaskNotFound):
            await database.service.get(project, owner, task["task_id"])
        with user_request() as request, pytest.raises(TaskNotFound):
            await database.service.change(
                project, owner, task["task_id"], request, expected_version=1, action="cancel"
            )
    assert (await database.service.get("p1", "alice", task["task_id"]))["version"] == 1


@pytest.mark.asyncio
async def test_wait_feedback_resume_complete_and_terminal_guard(database):
    task = await create(database.service)
    for version, action, fields in [
        (1, "wait", {"next_step": "Await field observations"}),
        (2, "feedback", {}),
        (3, "resume", {"next_step": "Recheck observations"}),
        (4, "complete", {"result_summary": "Checked against observations and delivered report"}),
    ]:
        with user_request(message=f"User request: {action}") as request:
            task = await database.service.change(
                "p1",
                "alice",
                task["task_id"],
                request,
                expected_version=version,
                action=action,
                **fields,
            )
    stored = await database.service.get("p1", "alice", task["task_id"])
    assert stored["status"] == "completed"
    assert [entry["version"] for entry in stored["events"]] == [1, 2, 3, 4, 5]
    with user_request() as request, pytest.raises(TaskConflict):
        await database.service.change(
            "p1", "alice", task["task_id"], request, expected_version=5, action="resume"
        )


@pytest.mark.asyncio
async def test_concurrent_cancel_and_complete_cannot_both_win(database):
    task = await create(database.service)

    async def change(action):
        with user_request() as request:
            return await database.service.change(
                "p1",
                "alice",
                task["task_id"],
                request,
                expected_version=1,
                action=action,
                **({"result_summary": "Delivered checked result"} if action == "complete" else {}),
            )

    results = await asyncio.gather(change("cancel"), change("complete"), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, TaskConflict) for result in results) == 1
    assert len((await database.service.get("p1", "alice", task["task_id"]))["events"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "change"])
async def test_audit_insert_failure_rolls_back_entire_mutation(database, operation):
    existing = await create(database.service) if operation == "change" else None

    def reject_audit(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("INSERT INTO assistant_task_events"):
            raise RuntimeError("injected audit storage failure")

    event.listen(database.engine.sync_engine, "before_cursor_execute", reject_audit)
    try:
        with pytest.raises(RuntimeError):
            if operation == "create":
                await create(database.service)
            else:
                with user_request() as request:
                    await database.service.change(
                        "p1",
                        "alice",
                        existing["task_id"],
                        request,
                        expected_version=1,
                        action="cancel",
                    )
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", reject_audit)
    tasks = await database.service.list("p1", "alice")
    if operation == "create":
        assert tasks == []
    else:
        stored = await database.service.get("p1", "alice", existing["task_id"])
        assert stored["status"] == "ready"
        assert stored["version"] == 1
        assert len(stored["events"]) == 1


@pytest.mark.asyncio
async def test_wait_and_completion_require_actual_description(database):
    task = await create(database.service)
    for action in ["wait", "block", "complete"]:
        with user_request() as request, pytest.raises(ValueError):
            await database.service.change(
                "p1", "alice", task["task_id"], request, expected_version=1, action=action
            )


@pytest.mark.asyncio
async def test_goal_change_preserves_original_and_requires_fresh_version(database):
    task = await create(database.service)
    with user_request(message="Only analyze the city center") as request:
        changed = await database.service.change(
            "p1",
            "alice",
            task["task_id"],
            request,
            expected_version=1,
            action="update",
            goal="City center analysis",
            completion_criteria="City center report",
        )
    assert changed["goal"] == "City center analysis"
    detail = await database.service.get("p1", "alice", task["task_id"])
    assert detail["events"][0]["changes"]["goal"] == "Meeting analysis"
    assert detail["events"][-1]["user_message"] == "Only analyze the city center"
    assert await database.service.list("p1", "alice", limit=1, offset=1) == []


@pytest.mark.asyncio
async def test_tool_end_to_end_uses_catalog_identity_and_current_user_feedback(
    database, monkeypatch
):
    from app.tools.social.assistant_tasks import tool as module
    from config.settings import settings

    async def identity(context):
        return SimpleNamespace(id="alice")

    monkeypatch.setattr(module, "resolve_task_user", identity)
    monkeypatch.setattr(settings, "project_id", "p1")
    tool = ManageAssistantTasksTool(database.service)
    context = SimpleNamespace(session_id="session-a")
    denied = await tool.execute(
        context=context, action="create", goal="Goal", completion_criteria="Deliver"
    )
    assert denied["success"] is False
    with user_request():
        created = await tool.execute(
            context=context, action="create", goal="Goal", completion_criteria="Deliver"
        )
    task_id = created["data"]["task"]["task_id"]
    with user_request(message="Field inspection found a stopped machine", request_id="feedback-b"):
        changed = await tool.execute(
            context=context, action="feedback", task_id=task_id, expected_version=1
        )
    assert changed["success"] is True
    detail = await tool.execute(context=context, action="get", task_id=task_id)
    assert (
        detail["data"]["task"]["events"][-1]["user_message"]
        == "Field inspection found a stopped machine"
    )
    with user_request():
        denied = await tool.execute(
            context=context,
            action="cancel",
            task_id=task_id,
            expected_version=2,
            owner_user_id="bob",
        )
        assert denied["success"] is False
        denied = await tool.execute(
            context=SimpleNamespace(session_id="background-a"),
            action="cancel",
            task_id=task_id,
            expected_version=2,
        )
        assert denied["success"] is False


@pytest.mark.asyncio
async def test_tool_database_failure_is_explicit_and_does_not_switch_storage(monkeypatch):
    from app.tools.social.assistant_tasks import tool as module

    async def identity(context):
        return SimpleNamespace(id="alice")

    async def fail(*args, **kwargs):
        raise RuntimeError("private database connection details")

    monkeypatch.setattr(module, "resolve_task_user", identity)
    result = await ManageAssistantTasksTool(SimpleNamespace(list=fail)).execute(
        context=SimpleNamespace(session_id="session-a"), action="list"
    )
    assert not result["success"]
    assert "private" not in result["error"]


def test_social_contract_applies_to_project_override_and_respects_disabled_tool(monkeypatch):
    from app.agent.prompts import prompt_builder, tool_registry

    monkeypatch.setattr(
        tool_registry, "_get_project_tool_names_by_mode", lambda mode: ["read_file"]
    )
    monkeypatch.setattr(tool_registry, "_get_project_disabled_tool_names", lambda: [])
    monkeypatch.setattr(
        prompt_builder, "load_project_mode_prompt", lambda mode: "Project-specific assistant"
    )
    prompt = prompt_builder.build_react_system_prompt("social")
    assert "Project-specific assistant" in prompt
    assert "持续事项与交办边界" in prompt
    assert "manage_assistant_tasks" in tool_registry.get_tools_by_mode("social")
    monkeypatch.setattr(
        tool_registry, "_get_project_disabled_tool_names", lambda: ["manage_assistant_tasks"]
    )
    assert "持续事项与交办边界" not in prompt_builder.build_react_system_prompt("social")
    assert "manage_assistant_tasks" not in tool_registry.get_tools_by_mode("expert")


@pytest.mark.asyncio
async def test_missing_catalog_owner_cannot_mutate_even_with_live_user_scope(database, monkeypatch):
    from app.conversations import dependencies

    async def find(session_id):
        return SimpleNamespace(owner_user_id="system")

    monkeypatch.setattr(
        dependencies, "get_conversation_catalog", lambda: SimpleNamespace(find=find)
    )
    with user_request():
        result = await ManageAssistantTasksTool(database.service).execute(
            context=SimpleNamespace(session_id="session-a"),
            action="create",
            goal="Goal",
            completion_criteria="Deliver",
        )
    assert not result["success"]
    assert await database.service.list("p1", "alice") == []


@pytest.mark.asyncio
async def test_app_http_task_reads_enforce_identity_and_fail_closed(database, monkeypatch):
    import httpx
    from fastapi import FastAPI

    from app.api import social_app_routes as routes
    from app.social import assistant_tasks as service_module
    from app.social.app_identity import AppIdentity, require_app_identity

    task = await create(database.service, owner="app:android:alice")
    monkeypatch.setattr(service_module, "AssistantTaskService", lambda: database.service)
    monkeypatch.setattr(routes.settings, "project_id", "p1")
    app = FastAPI()
    app.include_router(routes.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        base = "/api/social/app/assistant/tasks"
        assert (await client.get(base)).status_code == 401
        app.dependency_overrides[require_app_identity] = lambda: AppIdentity(
            "alice", "Alice", "app:android:alice", 9999999999
        )
        assert (await client.get(base)).json()["tasks"][0]["task_id"] == task["task_id"]
        assert (await client.get(f"{base}/{task['task_id']}")).status_code == 200
        app.dependency_overrides[require_app_identity] = lambda: AppIdentity(
            "bob", "Bob", "app:android:bob", 9999999999
        )
        assert (await client.get(base)).json()["tasks"] == []
        assert (await client.get(f"{base}/{task['task_id']}")).status_code == 404

        async def unavailable(*args, **kwargs):
            raise RuntimeError("private connection details")

        monkeypatch.setattr(
            service_module,
            "AssistantTaskService",
            lambda: SimpleNamespace(list=unavailable, get=unavailable),
        )
        assert (await client.get(base)).status_code == 503
        response = await client.get(f"{base}/{task['task_id']}")
        assert response.status_code == 503
        assert "private" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_error", [False, True])
async def test_app_stream_binds_original_request_and_revokes_on_exit(monkeypatch, raise_error):
    from app.agent.runtime.cancellation import cancellation_registry
    from app.api import social_app_routes as routes
    from app.social.app_identity import AppIdentity

    class Agent:
        async def analyze(self, **kwargs):
            request = require_assistant_request(kwargs["session_id"])
            assert request.user_message == "Please track my analysis"
            assert request.request_id == "client-request-a"
            assert kwargs["manual_mode"] == "social"
            if raise_error:
                raise RuntimeError("injected agent failure")
            yield {"type": "start", "data": {}}

    async def agent():
        return Agent()

    async def memory(identity):
        return object()

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(routes, "_get_agent", agent)
    monkeypatch.setattr(routes, "_get_memory_store", memory)
    monkeypatch.setattr(routes, "_social_preferences", lambda identity: {})
    monkeypatch.setattr(routes, "_persist_app_turn", noop)
    monkeypatch.setattr(cancellation_registry, "arm_run_task", noop)
    identity = AppIdentity("alice", "Alice", "app:android:alice", 9999999999)
    chunks = [
        item
        async for item in routes._stream_events_unlocked(
            identity,
            "session-a",
            "Please track my analysis",
            mode="social",
            request_id="client-request-a",
        )
    ]
    assert chunks
    with pytest.raises(PermissionError):
        require_assistant_request("session-a")


@pytest.mark.asyncio
async def test_social_bridge_binds_current_request_and_revokes_after_failure(monkeypatch):
    from app.social.agent_bridge import AgentBridge

    class Agent:
        async def analyze(self, **kwargs):
            assert (
                require_assistant_request(kwargs["session_id"]).user_message
                == "Please track my analysis"
            )
            raise RuntimeError("injected bridge agent failure")
            yield  # pragma: no cover

    bridge = object.__new__(AgentBridge)
    bridge.agent = Agent()
    bridge.mode = "social"
    answer, _ = await bridge._aggregate_agent_events(
        content="Please track my analysis", session_id="session-a", chat_id="alice"
    )
    assert "injected bridge agent failure" in answer
    with pytest.raises(PermissionError):
        require_assistant_request("session-a")
