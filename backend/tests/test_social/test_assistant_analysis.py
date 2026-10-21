"""Analysis queue integration with temporary SQL storage and a fake model."""

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.social.assistant_analysis import AssistantAnalysisQueue
from app.social.assistant_analysis_agent import (
    analyze_claim,
    validate_output,
    verify_analysis_owner,
)
from app.social.assistant_followup_models import AssistantOutboxDB as Outbox
from app.social.assistant_followup_models import AssistantRunDB as Run
from app.social.assistant_followup_models import AssistantTriggerDB as Trigger
from app.social.assistant_followup_worker import AssistantFollowupWorker
from app.social.assistant_request import (
    AssistantRequest,
    begin_assistant_request,
    end_assistant_request,
    require_assistant_request,
)
from app.social.assistant_task_models import AssistantTaskDB as Task
from app.social.assistant_task_models import AssistantTaskEventDB as Event
from app.social.assistant_tasks import AssistantTaskService

NOW = datetime(2026, 10, 19, 1)
OWNER = "app:bot:alice"
REQUEST = AssistantRequest("session-a", "request-a", "Analyze when I provide field evidence", OWNER)


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    import app.social.assistant_analysis_agent as adapter
    from config.settings import settings

    monkeypatch.setattr(settings, "assistant_followups_enabled", True)
    monkeypatch.setattr(settings, "assistant_analysis_enabled", True)
    monkeypatch.setattr(adapter, "available_analysis_tools", lambda: [])
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'analysis.db').as_posix()}")
    async with engine.begin() as connection:
        for model in (Task, Event, Trigger, Run, Outbox):
            await connection.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tasks = AssistantTaskService(factory)
    task = await tasks.create(
        "p1",
        OWNER,
        REQUEST,
        goal="Investigate the station anomaly",
        completion_criteria="Check the field evidence",
    )
    yield SimpleNamespace(
        queue=AssistantAnalysisQueue(factory),
        tasks=tasks,
        task=task,
        factory=factory,
        engine=engine,
    )
    await engine.dispose()


async def plan(db, kind="now", request=REQUEST, version=1, **kwargs):
    return await db.queue.create(
        "p1",
        OWNER,
        db.task["task_id"],
        request,
        expected_version=version,
        kind=kind,
        execution_action="analyze",
        instructions="Review current evidence",
        now=NOW,
        **kwargs,
    )


async def feedback(
    db,
    version=1,
    message="Field result: inspected the suspected discharge",
    request_id="feedback-a",
):
    request = AssistantRequest("session-a", request_id, message, OWNER)
    return await db.tasks.change(
        "p1", OWNER, db.task["task_id"], request, expected_version=version, action="feedback"
    )


async def claim(db):
    await plan(db)
    await db.queue.materialize("p1", NOW)
    return await db.queue.claim("p1", NOW)


def result(status="progress", notify=True, evidence=None):
    return {
        "output": {
            "status": status,
            "summary": "The anomaly needs field verification",
            "next_step": "Provide the on-site inspection record",
            "evidence": evidence or [],
            "should_notify": notify,
        },
        "observations": [],
    }


async def state(db):
    return await db.queue.inspect("p1", OWNER, db.task["task_id"])


@pytest.mark.asyncio
async def test_analysis_disabled_does_not_create_or_execute_an_analysis(db, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "assistant_analysis_enabled", False)
    with pytest.raises(PermissionError):
        await plan(db)
    assert (await state(db))["triggers"] == []
    monkeypatch.setattr(settings, "assistant_analysis_enabled", True)
    await plan(db)
    monkeypatch.setattr(settings, "assistant_analysis_enabled", False)
    await db.queue.materialize("p1", NOW)
    assert (await state(db))["runs"] == []


@pytest.mark.asyncio
async def test_feedback_is_a_transactional_event_and_coalesces_before_claim(db):
    await plan(db, kind="feedback")
    assert await db.queue.claim("p1", NOW) is None
    first = await feedback(db)
    await feedback(
        db, version=first["version"], message="Second inspection arrived", request_id="feedback-b"
    )
    runs = (await state(db))["runs"]
    assert {item["state"] for item in runs} == {"queued", "superseded"}
    claimed = await db.queue.claim("p1", NOW)
    assert claimed["task_version"] == 3
    assert [item["id"] for item in claimed["feedback"]] == ["feedback:2", "feedback:3"]
    assert claimed["trigger"]["grant_message"] == REQUEST.user_message
    assert claimed["trigger"]["schedule"]["tool_names"] == []


@pytest.mark.asyncio
async def test_feedback_does_not_create_a_new_grant(db):
    await feedback(db)
    assert (await state(db))["runs"] == []
    assert (await state(db))["triggers"] == []


@pytest.mark.asyncio
async def test_large_feedback_is_bounded_and_explicitly_marked_as_excerpt(db):
    await plan(db, kind="feedback")
    await feedback(db, message="a" * 20000)
    await feedback(db, version=2, message="b" * 20000)
    claimed = await db.queue.claim("p1", NOW)
    assert sum(len(item["text"]) for item in claimed["feedback"]) <= 12000
    assert all(item["truncated"] for item in claimed["feedback"])
    assert claimed["feedback"][-1]["text"].startswith("b")


@pytest.mark.asyncio
async def test_feedback_enqueue_failure_rolls_back_feedback_event_and_version(db):
    await plan(db, kind="feedback")

    def fail(_connection, _cursor, sql, *_args):
        if sql.startswith("INSERT INTO assistant_runs"):
            raise RuntimeError("queue storage unavailable")

    event.listen(db.engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            await feedback(db)
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", fail)
    stored = await db.tasks.get("p1", OWNER, db.task["task_id"])
    assert stored["version"] == 1 and len(stored["events"]) == 1


@pytest.mark.asyncio
async def test_analysis_claim_is_project_scoped_and_single_per_matter(db):
    await plan(db)
    await plan(db, request=AssistantRequest("session-a", "another-plan", "analyze also", OWNER))
    await db.queue.materialize("p1", NOW)
    assert await db.queue.claim("p2", NOW) is None
    claims = await asyncio.gather(db.queue.claim("p1", NOW), db.queue.claim("p1", NOW))
    assert sum(item is not None for item in claims) == 1
    assert sum(item["state"] == "running" for item in (await state(db))["runs"]) == 1
    await db.queue.prepare_notifications("p1", NOW)
    assert (await state(db))["notifications"] == []


@pytest.mark.asyncio
async def test_result_audit_and_notice_commit_without_completing_the_matter(db):
    await plan(db, kind="feedback")
    await feedback(db)
    claimed = await db.queue.claim("p1", NOW)
    await db.queue.finish(
        "p1", claimed, result=result("ready_for_review", evidence=["feedback:2"]), now=NOW
    )
    stored = await db.tasks.get("p1", OWNER, db.task["task_id"])
    assert stored["status"] == "waiting_input" and stored["version"] == 3
    audit = stored["events"][-1]
    assert audit["kind"] == "analysis_result" and audit["user_message"] == ""
    assert audit["source_request_id"] == f"run:{claimed['run_id']}"
    records = await state(db)
    assert records["runs"][0]["state"] == "succeeded"
    assert len(records["notifications"]) == 1
    await db.queue.finish("p1", claimed, result=result(), now=NOW)
    assert len((await state(db))["notifications"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,changes",
    [
        ("feedback", {}),
        ("cancel", {}),
        ("update", {"goal": "Different scope"}),
        ("complete", {"result_summary": "Verified by user"}),
    ],
)
async def test_stale_or_revoked_analysis_never_overwrites_human_changes(db, action, changes):
    claimed = await claim(db)
    await db.tasks.change(
        "p1", OWNER, db.task["task_id"], REQUEST, expected_version=1, action=action, **changes
    )
    await db.queue.finish("p1", claimed, result=result(), now=NOW)
    records = await state(db)
    assert records["runs"][0]["state"] == ("superseded" if action == "feedback" else "cancelled")
    assert records["notifications"] == []
    assert (await db.tasks.get("p1", OWNER, db.task["task_id"]))["version"] == 2


@pytest.mark.asyncio
async def test_outbox_failure_rolls_back_analysis_result_and_task_audit(db):
    claimed = await claim(db)

    def fail(_connection, _cursor, sql, *_args):
        if sql.startswith("INSERT INTO assistant_outbox"):
            raise RuntimeError("notice storage unavailable")

    event.listen(db.engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            await db.queue.finish("p1", claimed, result=result(), now=NOW)
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", fail)
    assert (await state(db))["runs"][0]["state"] == "running"
    stored = await db.tasks.get("p1", OWNER, db.task["task_id"])
    assert stored["version"] == 1 and len(stored["events"]) == 1
    await db.queue.finish("p1", claimed, result=result(), now=NOW)
    assert (await state(db))["runs"][0]["state"] == "succeeded"


@pytest.mark.asyncio
async def test_identical_notified_results_are_quiet_and_silent_progress_is_saved(db):
    await plan(db, kind="feedback")
    for version in (1, 3):
        await feedback(db, version=version, request_id=f"feedback-{version}")
        claimed = await db.queue.claim("p1", NOW)
        await db.queue.finish("p1", claimed, result=result(), now=NOW)
    assert len((await state(db))["notifications"]) == 1
    await feedback(db, version=5)
    claimed = await db.queue.claim("p1", NOW)
    await db.queue.finish("p1", claimed, result=result(notify=False), now=NOW)
    assert len((await state(db))["notifications"]) == 1
    assert all(run["state"] == "succeeded" for run in (await state(db))["runs"])


@pytest.mark.asyncio
async def test_expired_run_is_failed_not_replayed_or_revived_by_late_result(db):
    claimed = await claim(db)
    restarted = AssistantAnalysisQueue(db.factory)
    await restarted.recover("p1", NOW + timedelta(minutes=6))
    await restarted.finish("p1", claimed, result=result(), now=NOW + timedelta(minutes=6))
    assert (await state(db))["runs"][0]["state"] == "failed"
    assert await restarted.claim("p1", NOW + timedelta(minutes=6)) is None
    assert (await db.tasks.get("p1", OWNER, db.task["task_id"]))["version"] == 1
    assert len((await state(db))["notifications"]) == 1


@pytest.mark.asyncio
async def test_forged_fencing_token_does_not_publish_result(db):
    claimed = await claim(db)
    await db.queue.finish("p1", {**claimed, "lease_token": "wrong"}, result=result(), now=NOW)
    assert (await state(db))["runs"][0]["state"] == "running"
    assert (await state(db))["notifications"] == []


def test_validation_rejects_fabricated_evidence_and_unreviewed_completion():
    with pytest.raises(ValueError):
        validate_output(result("ready_for_review")["output"], [])
    with pytest.raises(ValueError):
        validate_output(result(evidence=["tool:99"])["output"], [])
    with pytest.raises(ValueError):
        validate_output({**result()["output"], "status": "completed"}, [])


@pytest.mark.asyncio
async def test_adapter_uses_fixed_tools_memory_off_and_observed_evidence(db, monkeypatch):
    import app.social.assistant_analysis_agent as module

    claimed = await claim(db)
    claimed["trigger"]["schedule"]["tool_names"] = ["execute_sql_query"]
    monkeypatch.setattr(module, "available_analysis_tools", lambda: ["execute_sql_query"])
    monkeypatch.setattr(module, "verify_analysis_owner", AsyncMock())
    tool = AsyncMock(return_value={"success": True, "summary": "Observed station data"})
    factory_args, analyze_args = {}, {}

    class Agent:
        async def analyze(self, prompt, **kwargs):
            analyze_args.update(kwargs)
            observed = await factory_args["tool_registry"]["execute_sql_query"](sql="SELECT 1")
            assert "tool:1" in observed["summary"]
            yield {
                "type": "complete",
                "data": {
                    "answer": json.dumps(result("ready_for_review", evidence=["tool:1"])["output"])
                },
            }

    def factory(**kwargs):
        factory_args.update(kwargs)
        return Agent()

    output = await analyze_claim(
        claimed, agent_factory=factory, registry_builder=lambda names: {"execute_sql_query": tool}
    )
    assert set(factory_args["tool_registry"]) == {"execute_sql_query"}
    assert not factory_args["enable_memory"] and factory_args["max_iterations"] == 12
    assert analyze_args["manual_mode"] == "custom" and analyze_args["user_identifier"] == OWNER
    assert output["observations"][0]["id"] == "tool:1"


@pytest.mark.asyncio
async def test_analysis_owner_is_revalidated_before_execution(monkeypatch):
    import app.conversations.dependencies as module

    catalog = SimpleNamespace(find=AsyncMock(return_value=SimpleNamespace(owner_user_id="bob")))
    monkeypatch.setattr(module, "get_conversation_catalog", lambda: catalog)
    claimed = {
        "task": {"owner_user_id": OWNER},
        "trigger": {"grant_session_id": "session", "recipient": OWNER},
    }
    with pytest.raises(PermissionError):
        await verify_analysis_owner(claimed)
    catalog.find.return_value.owner_user_id = OWNER
    await verify_analysis_owner(claimed)


@pytest.mark.asyncio
async def test_worker_clears_inherited_human_authority_and_does_not_block_clock(db):
    # Use real wall clock for worker leases; never contact a live provider.
    await db.queue.create(
        "p1",
        OWNER,
        db.task["task_id"],
        REQUEST,
        expected_version=1,
        kind="now",
        execution_action="analyze",
        instructions="Analyze the feedback",
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def analyzer(claimed):
        with pytest.raises(PermissionError):
            require_assistant_request("session-a")
        entered.set()
        await release.wait()
        return result()

    service = db.queue
    worker = AssistantFollowupWorker(
        "p1",
        service=service,
        analysis_queue=db.queue,
        analyzer=analyzer,
        owner_verifier=AsyncMock(),
    )
    token = begin_assistant_request("session-a", "human request", delivery_user_id=OWNER)
    try:
        await worker.tick()
        await asyncio.wait_for(entered.wait(), 2)
        assert require_assistant_request("session-a").user_message == "human request"
        await asyncio.wait_for(worker.tick(), 2)
        await db.tasks.change(
            "p1", OWNER, db.task["task_id"], REQUEST, expected_version=1, action="cancel"
        )
        await worker.tick()
        assert (
            worker.analysis_task is None
            or worker.analysis_task.done()
            or worker.analysis_claim is None
        )
    finally:
        release.set()
        await worker.stop()
        end_assistant_request(token)
    assert (await state(db))["notifications"] == []


@pytest.mark.asyncio
async def test_blocked_matter_waits_for_explicit_resume(db):
    await plan(db)
    await db.queue.materialize("p1", NOW)
    await db.tasks.change(
        "p1",
        OWNER,
        db.task["task_id"],
        REQUEST,
        expected_version=1,
        action="block",
        next_step="Wait for equipment repair",
    )
    assert await db.queue.claim("p1", NOW) is None
    await db.tasks.change(
        "p1", OWNER, db.task["task_id"], REQUEST, expected_version=2, action="resume"
    )
    assert (await db.queue.claim("p1", NOW))["task_version"] == 3


@pytest.mark.asyncio
async def test_periodic_analysis_coalesces_queued_work_without_cancelling_admitted_run(db):
    await plan(db, kind="interval", interval_minutes=1)
    await db.queue.materialize("p1", NOW + timedelta(minutes=1))
    claimed = await db.queue.claim("p1", NOW + timedelta(minutes=1))
    for minute in (2, 3):
        await db.queue.materialize("p1", NOW + timedelta(minutes=minute))
    states = [run["state"] for run in (await state(db))["runs"]]
    assert states.count("running") == states.count("queued") == states.count("superseded") == 1
    assert await db.queue.is_active("p1", claimed, NOW + timedelta(minutes=3))


@pytest.mark.asyncio
async def test_worker_feedback_analysis_and_outbox_delivery_form_one_local_flow(db):
    await plan(db, kind="feedback")
    await feedback(db)
    analyzer = AsyncMock(return_value=result("ready_for_review", evidence=["feedback:2"]))
    delivery = AsyncMock(return_value="inbox_saved")
    worker = AssistantFollowupWorker(
        "p1",
        service=db.queue,
        analysis_queue=db.queue,
        analyzer=analyzer,
        owner_verifier=AsyncMock(),
        adapter=delivery,
    )
    try:
        await worker.tick()
        await worker.analysis_task
        await worker.delivery_task
        await worker.tick()
        await worker.analysis_task
        await worker.delivery_task
    finally:
        await worker.stop()
    assert analyzer.await_count == delivery.await_count == 1
    records = await state(db)
    assert records["runs"][0]["state"] == "succeeded"
    assert records["notifications"][0]["state"] == "inbox_saved"
    assert "待验收" in records["notifications"][0]["content"]


@pytest.mark.asyncio
async def test_adapter_limits_tool_calls_and_rejects_incomplete_or_fabricated_final_output(
    db, monkeypatch
):
    import app.social.assistant_analysis_agent as module

    claimed = await claim(db)
    monkeypatch.setattr(module, "available_analysis_tools", lambda: ["execute_sql_query"])
    monkeypatch.setattr(module, "verify_analysis_owner", AsyncMock())
    tool = AsyncMock(return_value={"success": True, "summary": "data"})

    class Agent:
        def __init__(self, tools):
            self.tools = tools

        async def analyze(self, *args, **kwargs):
            for _ in range(13):
                await self.tools["execute_sql_query"](sql="SELECT 1")
            yield {"type": "complete", "data": {"answer": "{}"}}

    with pytest.raises(RuntimeError, match="预算"):
        await analyze_claim(
            claimed,
            agent_factory=lambda **kwargs: Agent(kwargs["tool_registry"]),
            registry_builder=lambda names: {"execute_sql_query": tool},
        )
    assert tool.await_count == 12

    class MissingFinal:
        async def analyze(self, *args, **kwargs):
            yield {"type": "thought", "data": {"thought": "working"}}

    with pytest.raises(ValueError, match="最终输出"):
        await analyze_claim(
            claimed,
            agent_factory=lambda **kwargs: MissingFinal(),
            registry_builder=lambda names: {},
        )


def test_runtime_registry_refuses_expanded_or_non_read_only_tools(monkeypatch):
    import app.agent.tool_adapter as adapter
    import app.social.assistant_analysis_agent as module
    import app.tools as tools_module

    monkeypatch.setattr(module, "available_analysis_tools", lambda: ["execute_sql_query"])
    monkeypatch.setattr(
        tools_module,
        "global_tool_registry",
        SimpleNamespace(get_tool_status=lambda name: "enabled"),
    )

    async def unsafe(**kwargs):
        pass

    unsafe.is_read_only = lambda: False
    monkeypatch.setattr(
        adapter, "get_react_agent_tool_registry", lambda: {"execute_sql_query": unsafe}
    )
    with pytest.raises(PermissionError):
        module.build_analysis_registry(["bash"])
    with pytest.raises(PermissionError):
        module.build_analysis_registry(["execute_sql_query"])


@pytest.mark.asyncio
async def test_chat_tool_passes_analysis_and_feedback_without_expanding_authority(db, monkeypatch):
    import app.tools.social.assistant_followups.tool as module
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "p1")
    monkeypatch.setattr(
        module, "resolve_task_user", AsyncMock(return_value=SimpleNamespace(id=OWNER))
    )
    tool = module.ManageAssistantFollowupsTool(db.queue)
    token = begin_assistant_request("session-a", REQUEST.user_message, delivery_user_id=OWNER)
    try:
        output = await tool.execute(
            context=SimpleNamespace(session_id="session-a", scheduled_task_context=None),
            action="create",
            task_id=db.task["task_id"],
            expected_version=1,
            kind="feedback",
            execution_action="analyze",
            instructions="Review new evidence",
        )
        assert output["success"]
        assert output["data"]["action"] == "analyze" and output["data"]["kind"] == "feedback"
    finally:
        end_assistant_request(token)


def test_real_executor_distinguishes_empty_grant_from_default_tools(monkeypatch):
    from app.agent.core.executor import ToolExecutor

    registered = []

    def register_defaults(executor):
        registered.append(executor)
        executor.tool_registry["unrestricted_default"] = lambda: None

    monkeypatch.setattr(ToolExecutor, "_register_builtin_tools", register_defaults)
    empty = ToolExecutor(tool_registry={})
    assert empty.tool_registry == {} and registered == []
    assert empty.clone_for_run(None).tool_registry == {} and registered == []
    default = ToolExecutor()
    assert list(default.tool_registry) == ["unrestricted_default"] and registered == [default]


def test_real_react_factory_and_run_clone_keep_the_explicit_tool_boundary(monkeypatch):
    from app.agent.core.executor import ToolExecutor
    from app.agent.react_agent import create_react_agent

    def unexpected_defaults(executor):
        raise AssertionError("explicit registry must not load defaults")

    monkeypatch.setattr(ToolExecutor, "_register_builtin_tools", unexpected_defaults)
    agent = create_react_agent(tool_registry={}, enable_memory=False, max_iterations=12)
    assert agent.executor.tool_registry == agent.planner.tool_registry == {}
    assert agent.executor.clone_for_run(None).tool_registry == {}
