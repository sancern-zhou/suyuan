from app.agent.workflow.capabilities import build_child_capability_policy
from datetime import datetime, timedelta, timezone

from app.agent.workflow.runtime import WorkflowRuntime


def test_runtime_records_lineage_and_reconstructs_from_snapshot():
    runtime = WorkflowRuntime()
    parent = runtime.create_run(task_id="parent", max_attempts=2)
    child = runtime.create_run(task_id="child", parent_task_id="parent")
    runtime.register_child(parent.run_id, child.task_id)
    runtime.start(parent.run_id)
    runtime.start(child.run_id)
    runtime.transition(child.run_id, "succeeded", payload={"answer": "ok"})

    restored = WorkflowRuntime(snapshot=runtime.snapshot())
    assert restored.get_run(parent.run_id).child_task_ids == ["child"]
    assert restored.get_run(child.run_id).status == "succeeded"
    assert [event.event_type for event in restored.events(run_id=child.run_id)] == [
        "task.created",
        "task.running",
        "task.succeeded",
    ]


def test_runtime_rejects_invalid_transition_and_propagates_cancel_request():
    runtime = WorkflowRuntime()
    run = runtime.create_run(task_id="task")
    runtime.start(run.run_id)
    runtime.request_cancel(run.run_id, reason="user stopped")
    assert runtime.should_cancel(run.run_id) is True
    assert runtime.get_run(run.run_id).status == "cancelled"

    try:
        runtime.transition(run.run_id, "running")
    except ValueError as exc:
        assert "invalid workflow transition" in str(exc)
    else:
        raise AssertionError("terminal workflow runs must not resume")


def test_failed_run_can_resume_only_with_remaining_attempt_budget():
    runtime = WorkflowRuntime()
    run = runtime.create_run(task_id="retryable", max_attempts=2)
    runtime.start(run.run_id)
    runtime.transition(run.run_id, "failed", payload={"error": "temporary"})
    runtime.start(run.run_id)
    assert runtime.get_run(run.run_id).status == "running"
    assert runtime.get_run(run.run_id).attempt == 2


def test_deadline_and_parent_cancel_propagate_to_children():
    runtime = WorkflowRuntime()
    parent = runtime.create_run(task_id="parent", deadline_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    child = runtime.create_run(task_id="child")
    runtime.register_child(parent.run_id, child.task_id)
    runtime.start(parent.run_id)
    runtime.start(child.run_id)
    assert runtime.check_deadline(parent.run_id) is True
    assert runtime.get_run(child.run_id).status == "cancelled"


def test_child_capability_policy_filters_delegation_and_explicit_tools():
    policy = build_child_capability_policy(
        allowed_tools=["query", "render", "call_sub_agent"],
        allow_delegation=False,
    )
    filtered = policy.filter_registry({"query": 1, "render": 2, "call_sub_agent": 3, "write": 4})
    assert filtered == {"query": 1, "render": 2}


def test_empty_restricted_registry_does_not_fallback_to_builtin_tools():
    policy = build_child_capability_policy(allowed_tools=[])
    filtered = policy.filter_registry({"query": 1})
    assert bool(filtered) is True
    assert dict(filtered) == {}
