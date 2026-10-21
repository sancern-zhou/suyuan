import asyncio

from app.agent.workflow.coordinator import WorkflowCoordinator


def test_coordinator_runs_independent_nodes_in_parallel_and_respects_dependencies():
    async def run():
        started = []
        finished = []

        async def execute(node, dependencies, attempt, retry_context=None):
            started.append(node.task_id)
            await asyncio.sleep(0.01)
            finished.append(node.task_id)
            if node.task_id == "merge":
                assert set(dependencies) == {"air", "weather"}
            return {"task_id": node.task_id, "attempt": attempt}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "report-1",
                "nodes": [
                    {"task_id": "air"},
                    {"task_id": "weather"},
                    {"task_id": "merge", "dependencies": ["air", "weather"]},
                ],
            },
            executor=execute,
            max_concurrency=2,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert set(started[:2]) == {"air", "weather"}
        assert started[-1] == "merge"
        assert result["node_results"]["merge"]["task_id"] == "merge"

    asyncio.run(run())


def test_coordinator_retries_node_and_persists_a_resumable_snapshot():
    async def run():
        attempts = []
        snapshots = []

        async def execute(node, dependencies, attempt, retry_context=None):
            attempts.append(attempt)
            if len(attempts) == 1:
                raise RuntimeError("temporary")
            return {"ok": True}

        coordinator = WorkflowCoordinator(
            {"workflow_id": "retry-1", "nodes": [{"task_id": "fetch", "max_attempts": 2}]},
            executor=execute,
            persist=snapshots.append,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert attempts == [1, 2]
        restored = WorkflowCoordinator(
            result["definition"],
            executor=execute,
            snapshot=result,
        )
        assert restored.snapshot()["node_results"]["fetch"] == {"ok": True}
        assert snapshots
        assert all(
            snapshot.get("workflow_id") == "retry-1" and "definition" in snapshot
            for snapshot in snapshots
        )

    asyncio.run(run())


def test_coordinator_keeps_failed_node_child_link_for_history():
    async def execute(node, dependencies, attempt, retry_context=None):
        return {
            "success": False,
            "summary": "child failed",
            "metadata": {"session_id": "social__to__query__failed"},
        }

    coordinator = WorkflowCoordinator(
        {"workflow_id": "failure-1", "nodes": [{"task_id": "air"}]},
        executor=execute,
    )
    snapshot = asyncio.run(coordinator.run())
    assert snapshot["status"] == "failed"
    assert snapshot["node_sessions"]["air"] == "social__to__query__failed"
    assert "air" not in snapshot["node_results"]


def test_coordinator_persists_child_link_while_node_is_running():
    async def run():
        snapshots = []
        linked = asyncio.Event()
        release = asyncio.Event()
        coordinator = None

        async def execute(node, dependencies, attempt, retry_context=None):
            coordinator.bind_node_session(node.task_id, "report__to__query__live")
            linked.set()
            await release.wait()
            return {"ok": True, "metadata": {"session_id": "report__to__query__live"}}

        coordinator = WorkflowCoordinator(
            {"workflow_id": "live-1", "nodes": [{"task_id": "air"}]},
            executor=execute,
            persist=snapshots.append,
        )
        task = asyncio.create_task(coordinator.run())
        await linked.wait()
        assert snapshots[-1]["graph"]["air"]["status"] == "running"
        assert snapshots[-1]["node_sessions"]["air"] == "report__to__query__live"
        release.set()
        await task

    asyncio.run(run())


def test_coordinator_cancels_pending_nodes():
    async def run():
        release = asyncio.Event()

        async def execute(node, dependencies, attempt, retry_context=None):
            await release.wait()
            return {"ok": True}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "cancel-1",
                "nodes": [
                    {"task_id": "source"},
                    {"task_id": "downstream", "dependencies": ["source"]},
                ],
            },
            executor=execute,
        )
        task = asyncio.create_task(coordinator.run())
        await asyncio.sleep(0)
        await coordinator.cancel(reason="user stopped")
        release.set()
        result = await task
        assert result["status"] == "cancelled"
        assert result["graph"]["downstream"]["status"] == "cancelled"

    asyncio.run(run())


def test_coordinator_times_out_node_and_records_clear_error():
    async def run():
        attempts = []

        async def execute(node, dependencies, attempt, retry_context=None):
            attempts.append((attempt, node.timeout_seconds, retry_context))
            await asyncio.sleep(1)
            return {"ok": True}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "timeout-1",
                "nodes": [{"task_id": "expert", "timeout_seconds": 0.01}],
            },
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "failed"
        assert result["graph"]["expert"]["status"] == "failed"
        # 默认 max_attempts=2：最终错误来自扩容后的第 2 次尝试（0.01×1.5）
        assert "timed out after 0.015s" in result["node_errors"]["expert"]
        assert result["definition"]["nodes"][0]["timeout_seconds"] == 0.01
        # 两次尝试：首试原预算，重试扩容且携带失败原因与子会话续跑信息
        assert attempts[0] == (1, 0.01, None)
        assert attempts[1][0] == 2 and attempts[1][1] == 0.015
        assert attempts[1][2] is not None

    asyncio.run(run())


def test_coordinator_records_strict_node_lineage():
    async def run():
        async def execute(node, dependencies, attempt, retry_context=None):
            return {
                "status": "success",
                "success": True,
                "data": {
                    "result_envelope": {
                        "status": "completed",
                        "summary": node.task_id,
                        "outputs": {"attempt": attempt},
                        "evidence": [{"source": node.task_id}],
                        "artifacts": [],
                    }
                },
            }

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "lineage-1",
                "nodes": [{"task_id": "source", "require_lineage": True}],
            },
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        assert result["node_lineage"]["source"]["evidence"][0]["source_task_id"] == "source"

    asyncio.run(run())


def test_coordinator_resume_retries_failed_node_from_snapshot():
    async def run():
        definition = {
            "workflow_id": "resume-1",
            "nodes": [{"task_id": "source", "max_attempts": 2}],
        }
        first = WorkflowCoordinator(definition, executor=lambda *args: {"success": True})
        failed = first.snapshot()
        failed["status"] = "failed"
        failed["graph"]["source"]["status"] = "failed"
        failed["node_errors"] = {"source": "process interrupted"}
        failed["runtime"]["runs"][failed["workflow_run_id"]]["status"] = "failed"
        failed["runtime"]["runs"]["resume-1:source"]["status"] = "failed"
        failed["runtime"]["runs"]["resume-1:source"]["attempt"] = 1
        calls = []

        async def execute(node, dependencies, attempt, retry_context=None):
            calls.append(attempt)
            return {"success": True}

        resumed = WorkflowCoordinator(definition, executor=execute, snapshot=failed)
        result = await resumed.run()
        assert result["status"] == "succeeded"
        assert calls == [2]

    asyncio.run(run())


def test_coordinator_rejects_snapshot_for_changed_definition():
    first = WorkflowCoordinator(
        {"workflow_id": "fingerprint-1", "nodes": [{"task_id": "source", "goal": "原始目标"}]},
        executor=lambda *args: {"success": True},
    )
    snapshot = first.snapshot()
    try:
        WorkflowCoordinator(
            {"workflow_id": "fingerprint-1", "nodes": [{"task_id": "source", "goal": "修改后的目标"}]},
            executor=lambda *args: {"success": True},
            snapshot=snapshot,
        )
    except ValueError as exc:
        assert "definition" in str(exc)
    else:
        raise AssertionError("changed workflow definition must not reuse a snapshot")


def test_resume_reactivates_legacy_dependency_blocked_nodes():
    async def scenario():
        definition = {"workflow_id": "blocked", "nodes": [
            {"task_id": "source", "max_attempts": 2},
            {"task_id": "derived", "dependencies": ["source"]},
        ]}
        original = WorkflowCoordinator(definition, executor=lambda *args: {"success": True})
        snapshot = original.snapshot()
        snapshot["status"] = "failed"
        snapshot["graph"]["source"]["status"] = "failed"
        snapshot["graph"]["derived"]["status"] = "cancelled"
        snapshot["node_errors"] = {"source": "interrupted", "derived": "dependency failed"}
        snapshot["runtime"]["runs"]["blocked:source"].update(status="failed", attempt=1)
        snapshot["runtime"]["runs"][snapshot["workflow_run_id"]].update(status="failed", attempt=1)
        calls = []
        async def execute(node, dependencies, attempt, retry_context=None):
            calls.append(node.task_id)
            return {"success": True}
        restored = await WorkflowCoordinator(definition, executor=execute, snapshot=snapshot).run()
        assert restored["status"] == "succeeded"
        assert calls == ["source", "derived"]
        assert restored["node_errors"] == {}
    asyncio.run(scenario())


def test_parent_cancellation_stops_children_and_preserves_resumable_session():
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        coordinator = None
        async def execute(node, dependencies, attempt, retry_context=None):
            coordinator.bind_node_session(node.task_id, "child-existing")
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        definition = {"workflow_id": "shutdown", "nodes": [{"task_id": "node"}]}
        coordinator = WorkflowCoordinator(definition, executor=execute)
        task = asyncio.create_task(coordinator.run())
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert stopped.is_set()
        snapshot = coordinator.snapshot()
        assert snapshot["graph"]["node"]["status"] == "pending"
        async def resume(node, dependencies, attempt, retry_context=None):
            assert retry_context["session_id"] == "child-existing"
            return {"success": True}
        assert (await WorkflowCoordinator(definition, executor=resume, snapshot=snapshot).run())["status"] == "succeeded"
    asyncio.run(scenario())


def test_coordinator_expands_node_budget_on_retry():
    async def run():
        seen = []

        async def execute(node, dependencies, attempt, retry_context=None):
            seen.append(
                (
                    attempt,
                    node.max_iterations,
                    node.timeout_seconds,
                    node.payload.get("max_iterations"),
                    retry_context,
                )
            )
            if attempt == 1:
                # 生产失败形态：返回 failed 结果（metadata 携带子会话 id）
                return {
                    "status": "failed",
                    "success": False,
                    "result": "budget exhausted",
                    "metadata": {"session_id": "child-session-1"},
                }
            return {"ok": True}

        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "budget-1",
                "nodes": [
                    {
                        "task_id": "binning",
                        "max_attempts": 2,
                        "max_iterations": 20,
                        "timeout_seconds": 600,
                    }
                ],
            },
            executor=execute,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        # 首试保持原预算且无重试上下文；重试放大 50%（迭代 20→30、超时 600→900）
        # 并携带上次失败原因与会话，供子 Agent 在已有工作基础上修正
        assert len(seen) == 2
        assert seen[0][:4] == (1, 20, 600, None)
        assert seen[0][4] is None
        assert seen[1][:4] == (2, 30, 900.0, 30)
        assert seen[1][4]["error"] == "budget exhausted"
        assert seen[1][4]["session_id"]
        # 定义保持原值：扩容只作用于当次执行，不污染快照
        assert result["definition"]["nodes"][0]["max_iterations"] == 20
        assert result["definition"]["nodes"][0]["timeout_seconds"] == 600

    asyncio.run(run())


def test_invalid_parameters_do_not_consume_another_child_attempt():
    async def scenario():
        attempts = []
        async def execute(node, dependencies, attempt, retry_context=None):
            attempts.append(attempt)
            raise ValueError("invalid parameter")
        result = await WorkflowCoordinator(
            {"workflow_id": "invalid", "nodes": [{"task_id": "n", "max_attempts": 3}]},
            executor=execute,
        ).run()
        assert result["status"] == "failed"
        assert attempts == [1]
    asyncio.run(scenario())


def test_coordinator_injects_completed_results_and_journal():
    async def run():
        executed = []

        async def execute(node, dependencies, attempt, retry_context=None):
            executed.append(node.task_id)
            return {"status": "success", "data": {"result_envelope": {"status": "completed"}}}

        class FakeJournal:
            def __init__(self):
                self.events = []

            def append(self, **kwargs):
                self.events.append(kwargs)

        cached_result = {
            "status": "success",
            "data": {"result_envelope": {"status": "completed"}},
        }
        journal = FakeJournal()
        coordinator = WorkflowCoordinator(
            {
                "workflow_id": "cache-1",
                "nodes": [
                    {
                        "task_id": "air",
                        "target_mode": "query",
                        "goal": "取数",
                        "require_lineage": False,
                    },
                    {
                        "task_id": "analysis",
                        "target_mode": "expert_analysis",
                        "goal": "研判",
                        "dependencies": ["air"],
                        "require_lineage": False,
                        "phase": "研判阶段",
                    },
                ],
            },
            executor=execute,
            completed_results={"air": cached_result},
            journal=journal,
        )
        result = await coordinator.run()
        assert result["status"] == "succeeded"
        # air 命中缓存未执行；analysis 正常执行
        assert executed == ["analysis"]
        assert result["node_results"]["air"] == cached_result
        event_types = [e["event_type"] for e in journal.events]
        assert "node.started" in event_types
        assert "node.succeeded" in event_types
        assert "workflow.succeeded" in event_types
        # phase 透传进 journal 事件（位于 payload 内）
        started = next(e for e in journal.events if e["event_type"] == "node.started" and e["task_id"] == "analysis")
        assert started["payload"]["phase"] == "研判阶段"

    asyncio.run(run())
