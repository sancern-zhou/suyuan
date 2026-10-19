import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agent.workflow.registry import ActiveWorkflowRegistry
from app.social.assistant_request import begin_assistant_request, end_assistant_request
from app.social.assistant_runs import AssistantRunService
from app.tools.social.assistant_memory.tool import ManageAssistantMemoryTool
from app.tools.social.assistant_runs.tool import ManageAssistantRunsTool


@pytest.fixture
def context(tmp_path):
    workspace = tmp_path / "memory-user-a"
    workspace.mkdir()
    memory = workspace / "MEMORY.md"
    memory.write_text("# Preferences\n\nPrefer concise answers\n", encoding="utf-8")
    profile = workspace / "USER.md"
    profile.write_text("# Profile\n", encoding="utf-8")
    return SimpleNamespace(
        session_id="parent-a",
        runtime_mode="social",
        scheduled_task_context=None,
        assistant_memory_store=SimpleNamespace(
            mode="social", user_id="user-a", workspace=workspace, memory_file=memory
        ),
        assistant_profile_path=str(profile),
    )


@pytest.fixture
def request_scope(context):
    token = begin_assistant_request(context.session_id, "Please do the requested work")
    yield
    end_assistant_request(token)


@pytest.mark.asyncio
async def test_personal_memory_exact_update_delete_and_revision(context, request_scope):
    tool = ManageAssistantMemoryTool()
    read = await tool.execute(context=context, action="read", document="long_term")
    revision = read["data"]["revision"]
    changed = await tool.execute(
        context=context,
        action="update",
        document="long_term",
        expected_revision=revision,
        old_text="concise",
        new_text="detailed",
    )
    assert changed["success"]
    stale = await tool.execute(
        context=context,
        action="delete",
        document="long_term",
        expected_revision=revision,
        old_text="Prefer detailed answers",
    )
    assert not stale["success"]
    deleted = await tool.execute(
        context=context,
        action="delete",
        document="long_term",
        expected_revision=changed["data"]["revision"],
        old_text="Prefer detailed answers",
    )
    assert deleted["success"]
    assert "# Preferences" in context.assistant_memory_store.memory_file.read_text()


@pytest.mark.asyncio
async def test_personal_memory_no_paths_identity_or_background_authority(context):
    tool = ManageAssistantMemoryTool()
    for extra in ({"path": "../other/MEMORY.md"}, {"owner": "other"}):
        assert not (
            await tool.execute(context=context, action="read", document="long_term", **extra)
        )["success"]
    read = await tool.execute(context=context, action="read", document="long_term")
    assert not (
        await tool.execute(
            context=context,
            action="update",
            document="long_term",
            expected_revision=read["data"]["revision"],
            new_text="Injected",
        )
    )["success"]
    token = begin_assistant_request(context.session_id, "remember")
    try:
        context.scheduled_task_context = {"id": "background"}
        assert not (
            await tool.execute(
                context=context,
                action="delete",
                document="long_term",
                expected_revision=read["data"]["revision"],
                old_text="concise",
            )
        )["success"]
    finally:
        end_assistant_request(token)


@pytest.mark.asyncio
async def test_personal_profile_rejects_outside_binding_and_overflow(
    context, request_scope, tmp_path
):
    tool = ManageAssistantMemoryTool()
    read = await tool.execute(context=context, action="read", document="profile")
    assert not (
        await tool.execute(
            context=context,
            action="update",
            document="profile",
            expected_revision=read["data"]["revision"],
            new_text="x" * 12001,
        )
    )["success"]
    outside = tmp_path / "USER.md"
    outside.write_text("other user")
    context.assistant_profile_path = str(outside)
    assert not (await tool.execute(context=context, action="read", document="profile"))["success"]
    assert outside.read_text() == "other user"


@pytest.mark.asyncio
async def test_concurrent_memory_updates_do_not_overwrite(context, request_scope):
    tool = ManageAssistantMemoryTool()
    revision = (await tool.execute(context=context, action="read", document="long_term"))["data"][
        "revision"
    ]
    results = await asyncio.gather(
        *[
            tool.execute(
                context=context,
                action="update",
                document="long_term",
                expected_revision=revision,
                new_text=text,
            )
            for text in ("First update", "Second update")
        ]
    )
    assert sum(item["success"] for item in results) == 1


@pytest.fixture
def run_service(tmp_path, monkeypatch):
    async def user(context):
        return SimpleNamespace(id=getattr(context, "test_owner", "user-a"))

    monkeypatch.setattr("app.social.assistant_runs.resolve_task_user", user)
    return AssistantRunService(tmp_path / "runs", ActiveWorkflowRegistry())


@pytest.mark.asyncio
async def test_delegation_result_persists_and_is_personal(context, request_scope, run_service):
    async def execute(context, **kwargs):
        kwargs["_on_session_started"]("owned-child")
        assert kwargs["force_new_session"] is True
        return {
            "success": True,
            "status": "success",
            "result": "real result",
            "data": {"files": ["resource:1"]},
        }

    result = await run_service.launch(
        context, execute, {"target_mode": "office", "goal": "clean table"}, kind="child"
    )
    run_id = result["metadata"]["assistant_run_id"]
    restarted = AssistantRunService(run_service.root, ActiveWorkflowRegistry())
    persisted = await restarted.command(context, action="result", run_id=run_id, limit=12000)
    assert persisted["status"] == "succeeded"
    assert json.loads(persisted["content"])["result"] == "real result"
    context.test_owner = "user-b"
    assert (await restarted.command(context, action="list"))["runs"] == []
    with pytest.raises(ValueError):
        await restarted.command(context, action="get", run_id=run_id)


@pytest.mark.asyncio
async def test_background_delegation_cancel_is_confirmed_from_executor(
    context, request_scope, run_service
):
    started = asyncio.Event()

    async def execute(context, **kwargs):
        kwargs["_on_session_started"]("owned-child")
        started.set()
        await asyncio.Event().wait()

    result = await run_service.launch(
        context, execute, {"target_mode": "office", "run_in_background": True}, kind="child"
    )
    run_id = result["data"]["run_id"]
    await started.wait()
    assert (await run_service.command(context, action="get", run_id=run_id))["run"][
        "status"
    ] == "running"
    cancelled = await run_service.command(context, action="cancel", run_id=run_id)
    assert cancelled["accepted"] and cancelled["status"] == "cancel_requested"
    # Allow the real coroutine's finally block to persist cancellation.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert (await run_service.command(context, action="get", run_id=run_id))["run"][
        "status"
    ] == "cancelled"


@pytest.mark.asyncio
async def test_stale_run_unknown_never_reexecuted(context, request_scope, run_service):
    from config.settings import settings

    run_id = "delegation_" + "a" * 32
    run_service._save(
        settings.project_id, "user-a", {"run_id": run_id, "status": "running", "kind": "child"}
    )
    run = (await run_service.command(context, action="get", run_id=run_id))["run"]
    assert run["status"] == "unknown"
    assert not (await run_service.command(context, action="cancel", run_id=run_id))["accepted"]


@pytest.mark.asyncio
async def test_session_reuse_requires_owned_record(context, request_scope, run_service):
    async def execute(context, **kwargs):
        kwargs["_on_session_started"](kwargs.get("session_id") or "owned-child")
        return {"success": True, "status": "success", "metadata": {}}

    with pytest.raises(PermissionError):
        await run_service.launch(
            context, execute, {"target_mode": "office", "session_id": "someone-else"}, kind="child"
        )
    await run_service.launch(context, execute, {"target_mode": "office"}, kind="child")
    second = await run_service.launch(
        context, execute, {"target_mode": "office", "session_id": "owned-child"}, kind="child"
    )
    assert second["success"]


@pytest.mark.asyncio
async def test_steering_reports_real_acceptance(context, request_scope, run_service, monkeypatch):
    from app.agent.runtime.steering import InMemorySteeringStore, SteeringRegistry

    registry = SteeringRegistry(store=InMemorySteeringStore())
    monkeypatch.setattr("app.agent.runtime.steering.steering_registry", registry)
    started = asyncio.Event()
    release = asyncio.Event()

    async def execute(context, **kwargs):
        kwargs["_on_session_started"]("owned-office")
        started.set()
        await release.wait()
        return {"success": True, "status": "success"}

    launched = await run_service.launch(
        context, execute, {"target_mode": "office", "run_in_background": True}, kind="child"
    )
    await started.wait()
    run_id = launched["data"]["run_id"]
    try:
        assert not (
            await run_service.command(context, action="steer", run_id=run_id, message="add totals")
        )["accepted"]
        await registry.register("owned-office", "child-run", "office")
        assert (
            await run_service.command(context, action="steer", run_id=run_id, message="add totals")
        )["accepted"]
        assert (await registry.drain("owned-office", "child-run"))[0].content == "add totals"
    finally:
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_runs_tool_rejects_identity_and_missing_human_grant(context, run_service):
    tool = ManageAssistantRunsTool(run_service)
    assert not (await tool.execute(context=context, action="list", owner="other"))["success"]
    assert not (await tool.execute(context=context, action="list", offset=-1))["success"]

    async def execute(**kwargs):
        raise AssertionError("unauthorized launch")

    with pytest.raises(PermissionError):
        await run_service.launch(context, execute, {"target_mode": "office"}, kind="child")


@pytest.mark.asyncio
async def test_search_rebuild_unavailable_and_does_not_touch_index():
    from app.tools.social.session_search.tool import SessionSearchTool

    tool = SessionSearchTool()
    assert "rebuild" not in tool.function_schema["parameters"]["properties"]
    assert not (await tool.execute(query="test", rebuild=True))["success"]
    assert tool._fts_index is None


def test_assistant_tool_boundary_and_prompt(monkeypatch):
    from app.agent.prompts.prompt_builder import build_react_system_prompt
    from app.agent.prompts.tool_registry import get_tools_by_mode
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "default")
    tools = get_tools_by_mode("social")
    assert {"manage_assistant_memory", "manage_assistant_runs"}.issubset(tools)
    assert {"read_file", "edit_file"}.issubset(tools)
    assert {"wait_task", "bash"}.isdisjoint(tools)
    assert "edit_file" in get_tools_by_mode("office")
    prompt = build_react_system_prompt("social", memory_file_path="/private/MEMORY.md")
    assert "直接使用 edit_file" not in prompt
    assert "manage_assistant_memory" in prompt


@pytest.mark.asyncio
async def test_cross_worker_delegation_cancel_reuses_shared_control(
    context, request_scope, run_service
):
    from app.agent.runtime.cancellation_state import InMemoryCancellationStateStore

    store = InMemoryCancellationStateStore()
    worker_a = ActiveWorkflowRegistry(store=store, poll_interval=0.02)
    worker_b = ActiveWorkflowRegistry(store=store, poll_interval=0.02)
    run_service.registry = worker_a
    other_worker = AssistantRunService(run_service.root, worker_b)
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def execute(context, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    launched = await run_service.launch(
        context, execute, {"target_mode": "office", "run_in_background": True}, kind="child"
    )
    await started.wait()
    run_id = launched["data"]["run_id"]
    assert (await other_worker.command(context, action="get", run_id=run_id))["run"][
        "status"
    ] == "running"
    assert (await other_worker.command(context, action="cancel", run_id=run_id))["accepted"]
    await asyncio.wait_for(stopped.wait(), timeout=2)
    await asyncio.sleep(0)
    assert (await other_worker.command(context, action="get", run_id=run_id))["run"][
        "status"
    ] == "cancelled"


@pytest.mark.asyncio
async def test_nested_children_keep_owned_lineage_after_human_turn_ends(context, run_service):
    from app.social.assistant_runs import managed_delegation

    token = begin_assistant_request(context.session_id, "Run this DAG")
    ready = asyncio.Event()
    proceed = asyncio.Event()
    completed = asyncio.Event()

    async def execute(context, **kwargs):
        ready.set()
        await proceed.wait()
        service, project, owner, record = managed_delegation.get()
        child = service.child_arguments(project, owner, record, {"target_mode": "expert_analysis"})
        assert child["force_new_session"]
        child["_on_session_started"]("analysis-child")
        completed.set()
        return {"success": True, "status": "success"}

    try:
        launched = await run_service.launch(
            context, execute, {"workflow": {}, "run_in_background": True}, kind="workflow"
        )
        await ready.wait()
    finally:
        end_assistant_request(token)
    proceed.set()
    await asyncio.wait_for(completed.wait(), timeout=2)
    await asyncio.sleep(0)
    record = (await run_service.command(context, action="get", run_id=launched["data"]["run_id"]))[
        "run"
    ]
    assert record["child_sessions"] == ["analysis-child"]
    assert record["status"] == "succeeded"


@pytest.mark.asyncio
async def test_fact_read_is_personal_readonly_and_expiry_aware(context, request_scope):
    facts = context.assistant_memory_store.workspace / "facts"
    facts.mkdir()
    fact_id = "fact-0123456789abcdef"
    path = facts / f"{fact_id}.md"
    path.write_text(
        "---\nname: " + fact_id + "\nmetadata:\n  valid_until: '2099-01-01'\n---\n\nA stable fact",
        encoding="utf-8",
    )
    tool = ManageAssistantMemoryTool()
    result = await tool.execute(context=context, action="read", document="fact", fact_id=fact_id)
    assert result["success"] and "A stable fact" in result["data"]["content"]
    assert not (
        await tool.execute(context=context, action="delete", document="fact", fact_id=fact_id)
    )["success"]
    assert not (
        await tool.execute(context=context, action="read", document="fact", fact_id="../other")
    )["success"]
    path.write_text(
        path.read_text(encoding="utf-8").replace("2099-01-01", "2000-01-01"), encoding="utf-8"
    )
    assert not (
        await tool.execute(context=context, action="read", document="fact", fact_id=fact_id)
    )["success"]


@pytest.mark.asyncio
async def test_public_delegation_tools_return_queryable_run_handles(
    context, request_scope, run_service, monkeypatch
):
    from app.tools.agent_tools.call_sub_agent import CallSubAgentTool
    from app.tools.agent_tools.run_agent_workflow import RunAgentWorkflowTool

    monkeypatch.setattr("app.social.assistant_runs.AssistantRunService", lambda: run_service)

    async def child(**kwargs):
        kwargs["_on_session_started"]("owned-child")
        return {"success": True, "status": "success", "result": "Child result"}

    async def workflow(**kwargs):
        return {"success": True, "status": "success", "result": "DAG result"}

    single = CallSubAgentTool()
    monkeypatch.setattr(single, "_execute_foreground_as_subagent", child)
    result = await single.execute(context=context, target_mode="office", goal="Prepare a table")
    assert (
        await run_service.command(
            context, action="get", run_id=result["metadata"]["assistant_run_id"]
        )
    )["run"]["child_session_id"] == "owned-child"
    graph = RunAgentWorkflowTool()
    monkeypatch.setattr(graph, "_execute_untracked", workflow)
    result = await graph.execute(context=context, workflow={"nodes": []})
    assert (
        await run_service.command(
            context, action="get", run_id=result["metadata"]["assistant_run_id"]
        )
    )["run"]["kind"] == "workflow"
    assert "run_in_background" in graph.function_schema["parameters"]["properties"]


def test_run_executor_injects_bound_memory_into_tool_context(context):
    from app.agent.core.executor import ToolExecutor

    executor = ToolExecutor.__new__(ToolExecutor)
    executor.memory_manager = SimpleNamespace(session_id=context.session_id)
    executor.data_context_manager = SimpleNamespace()
    executor.task_list = None
    executor.llm_planner = None
    executor.runtime_mode = "social"
    executor.user_identifier = "server-bound-user"
    executor.runtime_metadata = {}
    executor.authorized_input_paths = []
    executor.assistant_memory_store = context.assistant_memory_store
    executor.assistant_profile_path = context.assistant_profile_path
    bound = executor._create_execution_context(1)
    assert bound.assistant_memory_store is context.assistant_memory_store
    assert bound.assistant_profile_path == context.assistant_profile_path


def test_tools_are_registered_as_real_implementations():
    from app.tools import global_tool_registry

    assert isinstance(
        global_tool_registry.get_tool("manage_assistant_memory"), ManageAssistantMemoryTool
    )
    assert isinstance(
        global_tool_registry.get_tool("manage_assistant_runs"), ManageAssistantRunsTool
    )
