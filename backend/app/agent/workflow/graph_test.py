import asyncio

import pytest

from app.agent.workflow.graph import WorkflowConcurrencyGovernor, WorkflowGraph


def test_graph_exposes_only_tasks_whose_dependencies_succeeded():
    graph = WorkflowGraph()
    graph.add_task("fetch")
    graph.add_task("analyze", dependencies=["fetch"])
    graph.add_task("summarize", dependencies=["analyze"])
    assert graph.ready_tasks() == ["fetch"]
    graph.set_status("fetch", "succeeded")
    assert graph.ready_tasks() == ["analyze"]
    graph.set_status("analyze", "succeeded")
    assert graph.ready_tasks() == ["summarize"]


def test_graph_rejects_missing_dependencies_and_cycles():
    graph = WorkflowGraph()
    with pytest.raises(ValueError, match="not registered"):
        graph.add_task("analyze", dependencies=["fetch"])
    graph.add_task("fetch")
    graph.add_task("analyze", dependencies=["fetch"])
    with pytest.raises(ValueError, match="cycle"):
        graph.add_task("fetch", dependencies=["analyze"])


def test_concurrency_governor_limits_active_work():
    async def run():
        governor = WorkflowConcurrencyGovernor(limit=1)
        entered = []
        first = asyncio.Event()
        release = asyncio.Event()

        async def worker(name):
            async with governor:
                entered.append(name)
                if name == "first":
                    first.set()
                    await release.wait()

        first_task = asyncio.create_task(worker("first"))
        await first.wait()
        second_task = asyncio.create_task(worker("second"))
        await asyncio.sleep(0)
        assert entered == ["first"]
        release.set()
        await asyncio.gather(first_task, second_task)
        assert entered == ["first", "second"]

    asyncio.run(run())
