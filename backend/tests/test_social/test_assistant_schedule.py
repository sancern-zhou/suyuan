"""Unified schedule integration: temporary DB, real task storage and mocked IPC only."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models import CurrentUser
from app.scheduled_tasks.storage.task_storage import TaskStorage
from app.social.assistant_followup_models import (
    AssistantOutboxDB,
    AssistantRunDB,
    AssistantTriggerDB,
)
from app.social.assistant_plans import AssistantPlanService, PlanCommand
from app.social.assistant_notification_models import AssistantNotificationDB
from app.social.assistant_request import (
    AssistantRequest,
    begin_assistant_request,
    end_assistant_request,
)
from app.social.assistant_task_models import AssistantTaskDB, AssistantTaskEventDB
from app.social.assistant_tasks import AssistantTaskService, TaskConflict, TaskNotFound
from app.social.web_assistant import web_assistant_recipient
from app.tools.social.assistant_schedule.tool import ManageAssistantScheduleTool
from config.settings import settings

USER = CurrentUser(id="alice", username="alice", display_name="Alice")
REQUEST = AssistantRequest("session-a", "request-a", "Remind me", web_assistant_recipient("alice"))


@pytest_asyncio.fixture
async def plans(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")
    monkeypatch.setattr(settings, "assistant_followups_enabled", True)
    monkeypatch.setattr(settings, "assistant_analysis_enabled", True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'plans.db').as_posix()}")
    async with engine.begin() as conn:
        for table in (
            AssistantTaskDB,
            AssistantTaskEventDB,
            AssistantTriggerDB,
            AssistantRunDB,
            AssistantOutboxDB,
            AssistantNotificationDB,
        ):
            await conn.run_sync(table.__table__.create)
    service = AssistantPlanService(async_sessionmaker(engine, expire_on_commit=False))
    storage = TaskStorage(tmp_path / "jobs")
    jobs = SimpleNamespace(
        list_tasks=lambda enabled_only=False: storage.list(enabled_only),
        get_task=storage.get,
        create_task=storage.create,
        update_task=storage.update,
    )
    monkeypatch.setattr(service, "_job_service", lambda: jobs)
    yield service
    await engine.dispose()


async def create(plans, purpose="remind", **fields):
    return (
        await plans.dispatch(
            "default",
            USER,
            PlanCommand(
                action="create",
                purpose=purpose,
                instructions="Collect field feedback",
                schedule={"kind": "interval", "interval_minutes": 30},
                **fields,
            ),
            REQUEST,
        )
    )["plan"]


async def control(plans, plan, action, **fields):
    return (
        await plans.dispatch(
            "default",
            USER,
            PlanCommand(
                action=action,
                plan_id=plan["plan_id"],
                expected_revision=plan["revision"],
                **fields,
            ),
            REQUEST,
        )
    )["plan"]


@pytest.mark.asyncio
async def test_reminder_lifecycle_is_individual_and_replay_safe(plans):
    first = await create(plans)
    assert (await create(plans))["plan_id"] == first["plan_id"]
    second = await create(plans, title="Another reminder")
    # Distinct title is included in the reminder goal; same text must not coalesce it.
    assert second["plan_id"] != first["plan_id"]
    paused = await control(plans, first, "pause")
    assert paused["state"] == "paused" and paused["next_at"] is None
    with pytest.raises(TaskConflict):
        await control(plans, first, "resume")
    resumed = await control(plans, paused, "resume")
    assert resumed["state"] == "active"
    cancelled = await control(plans, resumed, "cancel")
    assert cancelled["state"] == "cancelled"
    with pytest.raises(ValueError):
        await control(plans, cancelled, "resume")
    listing = await plans.dispatch("default", USER, PlanCommand(action="list"))
    assert listing["total"] == 2
    assert (
        next(p for p in listing["plans"] if p["plan_id"] == second["plan_id"])["state"] == "active"
    )


@pytest.mark.asyncio
async def test_read_and_mutation_are_owner_and_project_scoped(plans):
    plan = await create(plans)
    for project, user in (
        ("other", USER),
        ("default", CurrentUser(id="bob", username="bob", display_name="Bob")),
    ):
        with pytest.raises(TaskNotFound):
            await plans.dispatch(project, user, PlanCommand(action="get", plan_id=plan["plan_id"]))
    with pytest.raises(ValueError):
        await create(plans, purpose="execute", execution_mode="assistant")


@pytest.mark.asyncio
async def test_single_list_contains_reminder_and_real_office_job(plans):
    reminder = await create(plans)
    job = await create(plans, purpose="execute", execution_mode="office")
    assert (await create(plans, purpose="execute", execution_mode="office"))["plan_id"] == job[
        "plan_id"
    ]
    listing = await plans.dispatch("default", USER, PlanCommand(action="list"))
    assert {p["plan_id"] for p in listing["plans"]} == {reminder["plan_id"], job["plan_id"]}
    updated = await control(
        plans,
        job,
        "update",
        changes={
            "instructions": "Reconcile supplied file",
            "schedule": {"kind": "cron", "cron": "0 9 * * *"},
        },
    )
    stored = plans._job_service().get_task(job["plan_id"].split(":", 1)[1])
    assert stored.execution_mode == "office" and stored.cron == "0 9 * * *"
    assert stored.prompt == "Reconcile supplied file"
    from app.scheduled_tasks.scheduler.simple_scheduler import SimpleScheduler

    scheduler = SimpleScheduler(plans._job_service())
    scheduler.task_storage = SimpleNamespace(update=lambda task: task)
    scheduler._schedule_task(stored)
    assert scheduler.scheduler.get_job(stored.task_id) is not None
    paused = await control(plans, updated, "pause")
    assert paused["state"] == "paused"
    cancelled = await control(plans, paused, "cancel")
    assert cancelled["state"] == "cancelled"


@pytest.mark.asyncio
async def test_execute_accepts_leaf_sub_agent_mode(plans):
    job = await create(plans, purpose="execute", execution_mode="query_monitoring_city")
    assert job["execution_mode"] == "query_monitoring_city"
    stored = plans._job_service().get_task(job["plan_id"].split(":", 1)[1])
    assert stored.execution_mode == "query_monitoring_city"


@pytest.mark.asyncio
async def test_execution_binds_matter_and_verified_owner_reply_route(plans):
    matter = await AssistantTaskService(plans.session_factory).create(
        "default", USER.id, REQUEST, goal="Review file", completion_criteria="I approve the results",
    )
    plan = await create(plans, purpose="execute", execution_mode="office",
                        task_id=matter["task_id"], expected_version=1)
    stored = plans._job_service().get_task(plan["plan_id"].split(":", 1)[1])
    assert stored.assistant_recipient == REQUEST.delivery_user_id
    assert stored.assistant_matter_id == matter["task_id"]
    assert plan["result_delivery"] == "owner"
    with pytest.raises(TaskConflict):
        await create(plans, purpose="execute", execution_mode="office", title="stale",
                     task_id=matter["task_id"], expected_version=2)
    foreign = CurrentUser(id="bob", username="bob", display_name="Bob")
    with pytest.raises(TaskNotFound):
        await plans.dispatch("default", foreign, PlanCommand(
            action="create", purpose="execute", instructions="Run later", execution_mode="office",
            task_id=matter["task_id"], expected_version=1,
            schedule={"kind": "interval", "interval_minutes": 30},
        ), AssistantRequest("bob-session", "bob-request", "Run later", web_assistant_recipient("bob")))


@pytest.mark.asyncio
async def test_cancel_revokes_pending_reminder_delivery_and_feature_off_still_allows_stop(plans):
    plan = await create(plans)
    due = plan["next_at"] + timedelta(seconds=1)
    await plans.materialize("default", due)
    await plans.prepare_notifications("default", due)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(settings, "assistant_followups_enabled", False)
    try:
        latest = (
            await plans.dispatch(
                "default", USER, PlanCommand(action="get", plan_id=plan["plan_id"])
            )
        )["plan"]
        await control(plans, latest, "cancel")
        data = await plans.dispatch(
            "default", USER, PlanCommand(action="results", plan_id=plan["plan_id"])
        )
        assert data["notifications"][0]["state"] == "cancelled"
        with pytest.raises(PermissionError):
            await create(plans)
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_followup_uses_existing_feedback_queue_without_immediate_execution(plans):
    matter = await AssistantTaskService.create(
        plans,
        "default",
        USER.id,
        REQUEST,
        goal="Investigation",
        completion_criteria="Reviewed evidence",
    )
    command = PlanCommand(
        action="create",
        purpose="followup",
        task_id=matter["task_id"],
        expected_version=matter["version"],
        instructions="Review new field evidence",
        schedule={"kind": "feedback"},
    )
    plan = (await plans.dispatch("default", USER, command, REQUEST))["plan"]
    assert plan["next_at"] is None
    history = await plans.dispatch(
        "default", USER, PlanCommand(action="history", plan_id=plan["plan_id"])
    )
    assert history["runs"] == []
    tasks = AssistantTaskService(plans.session_factory)
    await tasks.change(
        "default",
        USER.id,
        matter["task_id"],
        REQUEST,
        action="feedback",
        expected_version=1,
        next_step="Field result received",
    )
    history = await plans.dispatch(
        "default", USER, PlanCommand(action="history", plan_id=plan["plan_id"])
    )
    assert len(history["runs"]) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"recipient": "bob"},
        {"purpose": "execute", "execution_mode": "office", "schedule": {"kind": "feedback"}},
        {"schedule": {"kind": "interval", "interval_minutes": 0}},
        {"schedule": {"kind": "cron", "cron": "bad"}},
    ],
)
def test_schema_rejects_ambiguous_or_unauthorized_requests(fields):
    values = dict(
        action="create",
        purpose="remind",
        instructions="test",
        schedule={"kind": "interval", "interval_minutes": 30},
    )
    values.update(fields)
    with pytest.raises(ValueError):
        PlanCommand.model_validate(values)


@pytest.mark.asyncio
async def test_tool_uses_authenticated_worker_ipc_and_rejects_background_mutation(monkeypatch):
    import app.tools.social.assistant_schedule.tool as module

    monkeypatch.setattr(module, "resolve_task_user", AsyncMock(return_value=USER))
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"plans": [], "total": 0})

    tool = ManageAssistantScheduleTool(
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kw)
    )
    context = SimpleNamespace(session_id="session-a", scheduled_task_context=None)
    assert (await tool.execute(context, action="list"))["success"]
    assert calls[0].url.path == "/internal/assistant-schedule"
    assert "x-suyuan-current-user" in calls[0].headers
    args = dict(
        action="create",
        purpose="remind",
        instructions="test",
        schedule={"kind": "interval", "interval_minutes": 30},
    )
    assert not (await tool.execute(context, **args))["success"]
    token = begin_assistant_request("session-a", "remind me")
    try:
        context.scheduled_task_context = {"task_id": "job"}
        assert not (await tool.execute(context, **args))["success"]
    finally:
        end_assistant_request(token)
    assert len(calls) == 1


def test_only_one_assistant_scheduling_tool_is_exposed(monkeypatch):
    from app.agent.prompts.tool_registry import get_tools_by_mode

    for project in ("default", "xuchang"):
        monkeypatch.setattr(settings, "project_id", project)
        tools = get_tools_by_mode("assistant")
        assert "manage_assistant_schedule" in tools
        assert {
            "schedule_task",
            "create_scheduled_task",
            "manage_scheduled_tasks",
            "manage_assistant_followups",
        }.isdisjoint(tools)


@pytest.mark.asyncio
async def test_real_worker_route_revalidates_session_and_registers_plan(plans, monkeypatch):
    import app.tools.social.assistant_schedule.tool as tool_module
    from app.api import assistant_plan_routes as routes
    from app.conversations import ConversationSource, dependencies
    from app.lifecycle.social_worker_api import create_social_worker_api_app

    catalog = SimpleNamespace(
        find=AsyncMock(
            return_value=SimpleNamespace(
                owner_user_id=USER.id,
                source=ConversationSource.WEB,
            )
        )
    )
    monkeypatch.setattr(dependencies, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(tool_module, "resolve_task_user", AsyncMock(return_value=USER))
    monkeypatch.setattr(settings, "social_worker_internal_token", "test-worker-key")
    app = create_social_worker_api_app(SimpleNamespace(), internal_token="test-worker-key")
    app.dependency_overrides[routes.plan_service] = lambda: plans
    tool = ManageAssistantScheduleTool(
        lambda **kw: httpx.AsyncClient(transport=httpx.ASGITransport(app=app), **kw)
    )
    context = SimpleNamespace(session_id="session-a", scheduled_task_context=None)
    token = begin_assistant_request("session-a", "Remind me every thirty minutes", "route-test")
    try:
        result = await tool.execute(
            context,
            action="create",
            purpose="remind",
            instructions="Follow up",
            schedule={"kind": "interval", "interval_minutes": 30},
        )
        assert result["success"], result
        plan = result["data"]["plan"]
        assert plan["state"] == "active"
        catalog.find.return_value = SimpleNamespace(
            owner_user_id="bob", source=ConversationSource.WEB
        )
        result = await tool.execute(context, action="get", plan_id=plan["plan_id"])
        assert result["http_status"] == 404
    finally:
        end_assistant_request(token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://worker"
    ) as client:
        result = await client.post(
            "/internal/assistant-schedule",
            json={
                "source_session_id": "session-a",
                "command": {"action": "list"},
            },
        )
        assert result.status_code == 403


@pytest.mark.asyncio
async def test_one_shot_keeps_utc_time_through_pause_resume(plans):
    at = datetime.now() + timedelta(days=2)
    command = PlanCommand(
        action="create",
        purpose="remind",
        instructions="One shot",
        schedule={"kind": "once", "run_at": at.isoformat() + "+00:00"},
    )
    plan = (await plans.dispatch("default", USER, command, REQUEST))["plan"]
    paused = await control(plans, plan, "pause")
    resumed = await control(plans, paused, "resume")
    assert resumed["next_at"] == plan["next_at"]


@pytest.mark.asyncio
async def test_concurrent_reminder_replay_creates_one_plan(plans):
    import asyncio

    first, second = await asyncio.gather(create(plans), create(plans))
    assert first["plan_id"] == second["plan_id"]
    assert (await plans.dispatch("default", USER, PlanCommand(action="list")))["total"] == 1


@pytest.mark.asyncio
async def test_existing_matter_reminder_does_not_upgrade_to_analysis(plans, monkeypatch):
    matter = await AssistantTaskService.create(
        plans,
        "default",
        USER.id,
        REQUEST,
        goal="Follow field feedback",
        completion_criteria="Reviewed field evidence",
    )
    monkeypatch.setattr(settings, "assistant_analysis_enabled", False)
    plan = await create(plans, task_id=matter["task_id"], expected_version=matter["version"])
    assert plan["task_id"] == matter["task_id"] and plan["purpose"] == "remind"
    async with plans.session_factory() as session:
        trigger = await session.get(AssistantTriggerDB, plan["plan_id"].split(":", 1)[1])
        assert trigger.action == "remind"


@pytest.mark.asyncio
async def test_administrator_assistant_cannot_read_another_users_execution(plans):
    plan = await create(plans, purpose="execute", execution_mode="office")
    administrator = USER.model_copy(update={"is_admin": True})
    task = plans._job_service().get_task(plan["plan_id"].split(":", 1)[1])
    task.owner_user_id = "bob"
    plans._job_service().update_task(task)
    with pytest.raises(TaskNotFound):
        await plans.dispatch(
            "default", administrator, PlanCommand(action="get", plan_id=plan["plan_id"])
        )
    assert (await plans.dispatch("default", administrator, PlanCommand(action="list")))[
        "total"
    ] == 0
