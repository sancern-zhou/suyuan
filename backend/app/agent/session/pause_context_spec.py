import asyncio

import pytest

from app.agent.runtime import cancellation as cancellation_runtime
from app.agent.memory.session_memory import SessionMemory
from app.agent.runtime.cancellation import CancellationRegistry
from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.agent.session.models import Session


def _paused_display_history():
    return [
        {
            "type": "user",
            "content": "查询站点数据并生成报告",
            "timestamp": "2026-08-02T10:00:00",
        },
        {
            "type": "thought",
            "content": "先查询站点数据",
            "data": {"run_id": "run_pause", "iteration": 1},
            "timestamp": "2026-08-02T10:00:01",
        },
        {
            "type": "tool_use",
            "content": "调用工具: query_station_data",
            "data": {
                "run_id": "run_pause",
                "tool_use_id": "tool_1",
                "tool_name": "query_station_data",
                "input": {"station": "A"},
            },
            "timestamp": "2026-08-02T10:00:02",
        },
        {
            "type": "tool_result",
            "content": "查询到 12 条数据",
            "data": {
                "run_id": "run_pause",
                "tool_use_id": "tool_1",
                "tool_name": "query_station_data",
                "result": {"status": "success", "summary": "查询到 12 条数据"},
                "is_error": False,
            },
            "timestamp": "2026-08-02T10:00:03",
        },
    ]


def test_append_paused_preserves_visible_trajectory_and_is_idempotent():
    session = Session(session_id="session_a", query="query")
    persistence = ConversationPersistenceService()

    persistence.append_paused(
        session,
        display_history=_paused_display_history(),
        run_id="run_pause",
        partial_answer="已完成数据查询，正在生成报告。",
        paused_at="2026-08-02T10:00:04",
    )
    persistence.append_paused(
        session,
        display_history=_paused_display_history(),
        run_id="run_pause",
        partial_answer="重复内容不应写入",
        paused_at="2026-08-02T10:00:05",
    )

    assert [message["type"] for message in session.conversation_history] == [
        "user",
        "thought",
        "tool_use",
        "tool_result",
        "final",
        "user_pause",
    ]
    assert session.conversation_history[-2]["data"]["partial"] is True
    assert session.conversation_history[-1]["data"]["reason"] == "user_paused"
    assert sum(message["type"] == "user_pause" for message in session.conversation_history) == 1


def test_append_paused_closes_unpaired_tool_call_as_unknown():
    session = Session(session_id="session_a", query="query")
    history = _paused_display_history()[:-1]

    ConversationPersistenceService().append_paused(
        session,
        display_history=history,
        run_id="run_pause",
        paused_at="2026-08-02T10:00:04",
    )

    synthetic_result = next(
        message
        for message in session.conversation_history
        if message["type"] == "tool_result"
    )
    assert synthetic_result["data"]["result"]["status"] == "unknown"
    assert synthetic_result["data"]["synthetic"] is True


def test_paused_trajectory_is_projected_into_next_llm_context():
    session = Session(session_id="session_a", query="query")
    ConversationPersistenceService().append_paused(
        session,
        display_history=_paused_display_history(),
        run_id="run_pause",
        partial_answer="已完成数据查询。",
        paused_at="2026-08-02T10:00:04",
    )

    projected = SessionMemory.project_history_messages_for_llm(
        session.conversation_history,
        session_id="session_a",
    )

    serialized = str(projected)
    assert "暂停前的可见分析" in serialized
    assert "query_station_data" in serialized
    assert "查询到 12 条数据" in serialized
    assert "已完成数据查询" in serialized
    assert "用户主动暂停了上一轮分析" in serialized


@pytest.mark.asyncio
async def test_pause_rejects_a_stale_run_id_without_stopping_the_active_run():
    registry = CancellationRegistry()
    cancel_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", cancel_event, "run_new")

    cancelled = await registry.cancel(
        "session_a",
        expected_run_id="run_old",
        reason="user_paused",
    )

    assert cancelled is False
    assert cancel_event.is_set() is False
    await registry.unregister("session_a", cancel_event)


@pytest.mark.asyncio
async def test_early_pause_is_delivered_when_the_route_arms_its_handler():
    registry = CancellationRegistry()
    cancel_event = await registry.register("session_a")

    async def wait_forever():
        await asyncio.Event().wait()

    run_task = asyncio.create_task(wait_forever())
    await registry.attach_run_task("session_a", run_task)
    await registry.cancel("session_a", reason="user_paused")

    assert run_task.cancelled() is False
    await registry.arm_run_task("session_a", cancel_event)
    await asyncio.sleep(0)
    assert run_task.cancelled() is True
    await registry.unregister("session_a", cancel_event)


@pytest.mark.asyncio
async def test_next_turn_waits_until_the_paused_run_finishes_finalization():
    registry = CancellationRegistry()
    first_event = await registry.register("session_a")
    await registry.attach_run_id("session_a", first_event, "run_old")

    async def old_run():
        try:
            await asyncio.Event().wait()
        finally:
            await registry.unregister("session_a", first_event)

    old_task = asyncio.create_task(old_run())
    await registry.attach_run_task("session_a", old_task)
    await registry.arm_run_task("session_a", first_event)

    next_event = await asyncio.wait_for(
        asyncio.create_task(registry.register("session_a")),
        timeout=1,
    )

    assert old_task.cancelled()
    assert next_event is not first_event
    await registry.unregister("session_a", next_event)


@pytest.mark.asyncio
async def test_remote_worker_pause_cancels_the_worker_that_owns_the_run():
    shared_store = cancellation_runtime.InMemoryCancellationStateStore()
    owner = CancellationRegistry(store=shared_store, poll_interval=0.01)
    remote = CancellationRegistry(store=shared_store, poll_interval=0.01)
    cancel_event = await owner.register("session_a")
    await owner.attach_run_id("session_a", cancel_event, "run_old")

    async def wait_forever():
        await asyncio.Event().wait()

    run_task = asyncio.create_task(wait_forever())
    await owner.attach_run_task("session_a", run_task)
    await owner.arm_run_task("session_a", cancel_event)

    assert await remote.cancel(
        "session_a",
        expected_run_id="run_old",
        reason="user_paused",
    )
    await asyncio.wait_for(cancel_event.wait(), timeout=0.5)
    await asyncio.sleep(0)

    assert run_task.cancelled()
    assert await owner.pause_reason("session_a", cancel_event) == "user_paused"
    await owner.unregister("session_a", cancel_event)


@pytest.mark.asyncio
async def test_remote_next_turn_waits_for_the_owner_to_commit_pause():
    shared_store = cancellation_runtime.InMemoryCancellationStateStore()
    owner = CancellationRegistry(store=shared_store, poll_interval=0.01)
    remote = CancellationRegistry(store=shared_store, poll_interval=0.01)
    cancel_event = await owner.register("session_a")
    await owner.attach_run_id("session_a", cancel_event, "run_old")

    assert await remote.cancel(
        "session_a",
        expected_run_id="run_old",
        reason="user_paused",
    )
    barrier = asyncio.create_task(
        remote.ensure_pause_succeeded("session_a", "run_old")
    )
    await asyncio.sleep(0.03)
    assert barrier.done() is False

    await asyncio.wait_for(cancel_event.wait(), timeout=0.5)
    await owner.unregister("session_a", cancel_event)
    await asyncio.wait_for(barrier, timeout=0.5)


@pytest.mark.asyncio
async def test_sse_disconnect_reads_remote_pause_reason_before_polling_catches_up():
    shared_store = cancellation_runtime.InMemoryCancellationStateStore()
    owner = CancellationRegistry(store=shared_store, poll_interval=10)
    remote = CancellationRegistry(store=shared_store, poll_interval=10)
    cancel_event = await owner.register("session_a")
    await owner.attach_run_id("session_a", cancel_event, "run_old")

    assert await remote.cancel(
        "session_a",
        expected_run_id="run_old",
        reason="user_paused",
    )

    assert await owner.pause_reason("session_a", cancel_event) == "user_paused"
    await owner.unregister("session_a", cancel_event)


@pytest.mark.asyncio
async def test_repeated_run_id_attachment_does_not_clear_remote_pause_request():
    shared_store = cancellation_runtime.InMemoryCancellationStateStore()
    owner = CancellationRegistry(store=shared_store, poll_interval=10)
    remote = CancellationRegistry(store=shared_store, poll_interval=10)
    cancel_event = await owner.register("session_a")
    await owner.attach_run_id("session_a", cancel_event, "run_old")

    assert await remote.cancel(
        "session_a",
        expected_run_id="run_old",
        reason="user_paused",
    )
    assert await owner.attach_run_id("session_a", cancel_event, "run_old")

    state = await shared_store.get("session_a")
    assert state is not None
    assert state.status == "pause_requested"
    assert state.reason == "user_paused"
    await owner.unregister("session_a", cancel_event)
