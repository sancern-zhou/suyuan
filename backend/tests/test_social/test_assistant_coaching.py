"""Coaching isolation, authorization, backlog concurrency, and live capability checks."""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.social.assistant_coaching import AssistantCoachingService
from app.social.assistant_coaching_models import AssistantCoachingOwnerDB, AssistantSuggestionDB
from app.social.assistant_request import (
    begin_assistant_request,
    end_assistant_request,
    require_assistant_request,
)
from app.tools.social.assistant_coaching.tool import ManageAssistantCoachingTool


@contextmanager
def human(message="Help me use the project Agent", request_id="request-a"):
    token = begin_assistant_request("session-a", message, request_id)
    try:
        yield require_assistant_request("session-a")
    finally:
        end_assistant_request(token)


@pytest_asyncio.fixture
async def database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'coaching.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(AssistantCoachingOwnerDB.__table__.create)
        await conn.run_sync(AssistantSuggestionDB.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    catalog = {
        "tool:read_file": {
            "capability_id": "tool:read_file",
            "kind": "tool",
            "target": "read_file",
            "revision": "v1",
        },
        "workspace:expert": {
            "capability_id": "workspace:expert",
            "kind": "workspace",
            "target": "expert",
            "revision": "v1",
        },
    }
    service = AssistantCoachingService(factory, lambda: catalog)
    yield SimpleNamespace(engine=engine, factory=factory, catalog=catalog, service=service)
    await engine.dispose()


async def propose(db, goal="Review supplied evidence", owner="alice", project="p1", **fields):
    with human() as request:
        return await db.service.propose(
            project,
            owner,
            request,
            capability_id="tool:read_file",
            goal=goal,
            reason="The supplied file contains the evidence",
            suggested_prompt="Review my inspection file",
            **fields,
        )


async def decide(db, suggestion, action="accept", owner="alice", project="p1", version=None):
    with human(f"I choose to {action} this suggestion", "decision-a") as request:
        return await db.service.decide(
            project,
            owner,
            request,
            suggestion_id=suggestion["suggestion_id"],
            expected_version=suggestion["version"] if version is None else version,
            action=action,
        )


@pytest.mark.asyncio
async def test_persists_restart_and_deduplicates_rewritten_reason(database):
    first = await propose(database)
    second = await propose(database, goal="  REVIEW   supplied evidence ")
    assert first["created"] and not second["created"]
    assert first["suggestion"]["suggestion_id"] == second["suggestion"]["suggestion_id"]
    restarted = AssistantCoachingService(database.factory, lambda: database.catalog)
    assert len(await restarted.list("p1", "alice")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["accept", "dismiss"])
async def test_choice_is_durable_and_not_reoffered(database, action):
    item = (await propose(database))["suggestion"]
    result = await decide(database, item, action)
    assert result["suggestion"]["state"] == {"accept": "accepted", "dismiss": "dismissed"}[action]
    assert result["execution_state"] == "not_started"
    assert await database.service.list("p1", "alice") == []
    repeated = await propose(database)
    assert not repeated["created"]
    repeated_decision = await decide(database, item, action)
    assert repeated_decision["suggestion"]["version"] == 2
    async with database.factory() as session:
        row = (await session.execute(select(AssistantSuggestionDB))).scalar_one()
        assert row.source_user_message == "Help me use the project Agent"
        assert row.decision_user_message == f"I choose to {action} this suggestion"


@pytest.mark.asyncio
async def test_acceptance_provides_route_without_model_job_or_permission(database):
    item = (await propose(database, missing_inputs=["File path"]))["suggestion"]
    route = (await decide(database, item))["next_action"]
    assert route["kind"] == "tool" and route["target"] == "read_file"
    assert route["missing_inputs"] == ["File path"]
    assert route["execution_state"] == "not_started"
    async with database.engine.connect() as conn:
        tables = await conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
        assert {row[0] for row in tables} == {"assistant_coaching_owners", "assistant_suggestions"}


@pytest.mark.asyncio
async def test_workspace_acceptance_remains_handoff_not_child_execution(database):
    with human() as request:
        item = (
            await database.service.propose(
                "p1",
                "alice",
                request,
                capability_id="workspace:expert",
                goal="Explain this episode",
                reason="Needs professional analysis",
                suggested_prompt="Analyze this episode using supplied data",
            )
        )["suggestion"]
    route = (await decide(database, item))["next_action"]
    assert route["kind"] == "workspace"
    assert route["target"] == "expert"
    assert "call_sub_agent" not in route["instruction"]


@pytest.mark.asyncio
async def test_owner_project_and_system_isolation(database):
    item = (await propose(database))["suggestion"]
    for project, owner in [("p1", "bob"), ("p2", "alice")]:
        assert await database.service.list(project, owner, state="all") == []
        with pytest.raises(ValueError, match="不存在"):
            await decide(database, item, owner=owner, project=project)
    with pytest.raises(PermissionError):
        await database.service.list("p1", "system")
    assert (await database.service.list("p1", "alice"))[0]["version"] == 1


@pytest.mark.asyncio
async def test_closed_human_scope_cannot_authorize_propose_or_decide(database):
    item = (await propose(database))["suggestion"]
    with human() as request:
        pass
    with pytest.raises(PermissionError):
        await database.service.propose(
            "p1",
            "alice",
            request,
            capability_id="tool:read_file",
            goal="New goal",
            reason="Reason",
            suggested_prompt="Prompt",
        )
    with pytest.raises(PermissionError):
        await database.service.decide(
            "p1",
            "alice",
            request,
            suggestion_id=item["suggestion_id"],
            expected_version=1,
            action="accept",
        )


@pytest.mark.asyncio
async def test_competing_accept_and_dismiss_have_one_winner(database):
    item = (await propose(database))["suggestion"]
    results = await asyncio.gather(
        decide(database, item), decide(database, item, "dismiss"), return_exceptions=True
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1


@pytest.mark.asyncio
async def test_concurrent_pending_limit_and_duplicate_proposals(database):
    results = await asyncio.gather(*(propose(database) for _ in range(4)))
    assert sum(result["created"] for result in results) == 1
    results = await asyncio.gather(
        *(propose(database, goal=f"Task {i}") for i in range(8)), return_exceptions=True
    )
    assert sum(isinstance(result, dict) for result in results) == 4
    assert len(await database.service.list("p1", "alice")) == 5
    # Another owner has an independent budget.
    assert (await propose(database, owner="bob"))["created"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["removed", "revision"])
async def test_live_catalog_change_blocks_even_repeated_acceptance(database, change):
    item = (await propose(database))["suggestion"]
    await decide(database, item)
    if change == "removed":
        database.catalog.clear()
    else:
        database.catalog["tool:read_file"]["revision"] = "v2"
    with pytest.raises(ValueError, match="能力已变化"):
        await decide(database, item)


@pytest.mark.asyncio
async def test_unavailable_pending_suggestion_can_still_be_dismissed(database):
    item = (await propose(database))["suggestion"]
    database.catalog.clear()
    with pytest.raises(ValueError):
        await decide(database, item)
    assert (await decide(database, item, "dismiss"))["suggestion"]["state"] == "dismissed"


@pytest.mark.asyncio
async def test_stale_version_and_invalid_input_are_rejected(database):
    item = (await propose(database))["suggestion"]
    with pytest.raises(ValueError, match="版本"):
        await decide(database, item, version=2)
    with pytest.raises(ValueError):
        await propose(database, missing_inputs="Guess a station")
    with human() as request, pytest.raises(ValueError, match="未开放"):
        await database.service.propose(
            "p1",
            "alice",
            request,
            capability_id="unknown:tool",
            goal="Goal",
            reason="Reason",
            suggested_prompt="Prompt",
        )


@pytest.mark.asyncio
async def test_storage_failure_rolls_back_choice(database):
    item = (await propose(database))["suggestion"]

    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE assistant_suggestions"):
            raise RuntimeError("injected database failure")

    event.listen(database.engine.sync_engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(RuntimeError):
            await decide(database, item)
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", reject)
    assert (await database.service.list("p1", "alice"))[0]["version"] == 1


@pytest.mark.asyncio
async def test_tool_server_identity_background_denial_and_unknown_action(database, monkeypatch):
    from app.tools.social.assistant_coaching import tool as module
    from config.settings import settings

    async def identity(context):
        return SimpleNamespace(id="alice")

    monkeypatch.setattr(module, "resolve_task_user", identity)
    monkeypatch.setattr(settings, "project_id", "p1")
    tool = ManageAssistantCoachingTool(database.service)
    context = SimpleNamespace(session_id="session-a")
    assert (await tool.execute(context=context, action="discover", kind="workspace"))["data"][
        "total"
    ] == 1
    assert (await tool.execute(context=context, action="discover", offset=2))["data"][
        "capabilities"
    ] == []
    fields = dict(
        capability_id="tool:read_file", goal="Goal", reason="Reason", suggested_prompt="Prompt"
    )
    assert not (await tool.execute(context=context, action="propose", **fields))["success"]
    with human():
        assert not (
            await tool.execute(context=context, action="propose", owner_user_id="bob", **fields)
        )["success"]
        background = SimpleNamespace(session_id="session-a", scheduled_task_context={"job": 1})
        assert not (await tool.execute(context=background, action="propose", **fields))["success"]
        assert (await tool.execute(context=context, action="propose", **fields))["success"]
    assert not (await tool.execute(context=context, action="invalid"))["success"]
    assert len((await tool.execute(context=context, action="list"))["data"]["suggestions"]) == 1


@pytest.mark.asyncio
async def test_tool_missing_catalog_owner_fails_closed(database, monkeypatch):
    from app.conversations import dependencies

    async def find(session_id):
        return SimpleNamespace(owner_user_id="system")

    monkeypatch.setattr(
        dependencies, "get_conversation_catalog", lambda: SimpleNamespace(find=find)
    )
    result = await ManageAssistantCoachingTool(database.service).execute(
        context=SimpleNamespace(session_id="session-a"), action="discover"
    )
    assert not result["success"]


def test_shared_contract_survives_project_override_but_respects_disabled(monkeypatch):
    from app.agent.prompts import prompt_builder, tool_registry

    monkeypatch.setattr(prompt_builder, "load_project_mode_prompt", lambda mode: "Project prompt")
    monkeypatch.setattr(
        tool_registry, "_get_project_tool_names_by_mode", lambda mode: ["read_file"]
    )
    monkeypatch.setattr(tool_registry, "_get_project_disabled_tool_names", lambda: [])
    assert "项目 Agent 使用教练" in prompt_builder.build_react_system_prompt("social")
    assert "manage_assistant_coaching" not in tool_registry.get_tools_by_mode("expert")
    monkeypatch.setattr(
        tool_registry, "_get_project_disabled_tool_names", lambda: ["manage_assistant_coaching"]
    )
    assert "项目 Agent 使用教练" not in prompt_builder.build_react_system_prompt("social")


def test_catalog_matches_project_modes_and_enabled_tools(monkeypatch):
    from app.agent.prompts import tool_registry
    from app.social.assistant_capabilities import capability_catalog
    from app.tools import global_tool_registry
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "xuchang")
    monkeypatch.setattr(
        global_tool_registry,
        "get_tool_status",
        lambda name: (
            "enabled"
            if name in {"read_file", "execute_sql_query", "call_sub_agent"}
            else "disabled"
        ),
    )
    monkeypatch.setattr(
        global_tool_registry, "get_tool", lambda name: SimpleNamespace(description=name)
    )
    catalog = capability_catalog()
    assert "workspace:query" in catalog
    assert "tool:execute_sql_query" in catalog
    assert "delegate:query" not in catalog and "delegate:expert" not in catalog
    assert "delegate:report" not in catalog
    assert all("create_report_package" not in item["tools"] for item in catalog.values())
    # Availability changes invalidate persisted capability revisions.
    before = catalog["workspace:query"]["revision"]
    monkeypatch.setattr(
        global_tool_registry,
        "get_tool_status",
        lambda name: "enabled" if name == "read_file" else "disabled",
    )
    assert capability_catalog()["workspace:query"]["revision"] != before
    monkeypatch.setattr(tool_registry, "_get_project_disabled_tool_names", lambda: ["read_file"])
    assert "workspace:query" not in capability_catalog()


def test_migration_creates_identical_columns_and_is_repeatable(tmp_path):
    import sqlite3

    migration = (
        Path(__file__).resolve().parents[2] / "app/db/migrations/024_create_assistant_coaching.sql"
    )
    connection = sqlite3.connect(tmp_path / "migration.db")
    try:
        for _ in range(2):
            connection.executescript(migration.read_text(encoding="utf-8"))
        for model in (AssistantSuggestionDB, AssistantCoachingOwnerDB):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({model.__tablename__})")
            }
            assert columns == set(model.__table__.columns.keys())
    finally:
        connection.close()


def test_real_registry_registration_and_catalog_without_model_calls(monkeypatch):
    from app.social.assistant_capabilities import capability_catalog
    from app.tools import global_tool_registry
    from config.settings import settings

    assert isinstance(
        global_tool_registry.get_tool("manage_assistant_coaching"), ManageAssistantCoachingTool
    )
    monkeypatch.setattr(settings, "project_id", "xuchang")
    catalog = capability_catalog()
    assert "workspace:query" in catalog
    assert "boundary" in catalog["workspace:query"]["contract"]
    assert all(
        item["source"] == "active_project_manifest_and_enabled_tool_registry"
        for item in catalog.values()
    )
    for item in catalog.values():
        assert all(
            global_tool_registry.get_tool_status(name) == "enabled" for name in item["tools"]
        )
        if item["kind"] == "tool":
            assert "required_parameters" in item
