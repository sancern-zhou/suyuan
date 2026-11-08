"""后台委派终态唤醒（assistant_wakeup）回归测试。

对齐 ZCode task-notification 语义清单：空闲唤醒、忙碌让路（活跃回合优先，
交付边界吸收不重复唤醒）、合批单轮、被顶掉重排/用户 Stop 丢弃、幂等账本、
通知契约块渲染。
"""
import asyncio
from unittest.mock import Mock

import pytest

from config.settings import settings


@pytest.fixture(autouse=True)
def _clean_wakeup_state(monkeypatch):
    import contextlib

    from app.agent.runtime import session_advisory_lock as lock_module
    from app.agent.runtime.cancellation import cancellation_registry
    from app.agent.runtime.cancellation_state import InMemoryCancellationStateStore
    from app.social import assistant_wakeup

    # 生产注册表单例挂的是 Redis store，连接绑定旧测试的事件循环；
    # 换成内存 store 隔离，避免跨用例的 loop 污染。
    original_store = cancellation_registry._store
    cancellation_registry._store = InMemoryCancellationStateStore()

    # 会话咨询锁连真实 PostgreSQL：测试内替换为直通锁（跨进程互斥语义不在此测）。
    @contextlib.asynccontextmanager
    async def passthrough_lock(session_id, *, wait_timeout=0):
        yield

    monkeypatch.setattr(lock_module, "session_advisory_lock", passthrough_lock)

    assistant_wakeup._PENDING_WAKES.clear()
    assistant_wakeup._DRAINING.clear()
    yield
    tasks = list(assistant_wakeup._DRAIN_TASKS)
    for task in tasks:
        task.cancel()
    assistant_wakeup._PENDING_WAKES.clear()
    assistant_wakeup._DRAINING.clear()
    cancellation_registry._store = original_store


def _record(run_id: str, session_id: str, *, status: str = "succeeded", **extra) -> dict:
    record = {
        "run_id": run_id,
        "kind": "child",
        "status": status,
        "owner_user_id": "user-1",
        "source_session_id": session_id,
        "target_mode": "expert_analysis",
        "goal": "分析空气质量数据",
        "result": {
            "status": status,
            "summary": "月均AQI 75.2",
            "data": {
                "result_envelope": {"summary": "月均AQI 75.2", "outputs": {"data_gaps": ["缺站点经纬度"]}},
                "file_paths": ["M:/tmp/result.json"],
            },
        },
    }
    record.update(extra)
    return record


async def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


@pytest.mark.asyncio
async def test_disabled_flag_queues_nothing(monkeypatch):
    from app.social import assistant_wakeup

    monkeypatch.setattr(settings, "assistant_delegation_wakeup_enabled", False)
    assistant_wakeup.request_delegation_wakeup(_record("delegation_a", "s1"))
    assert assistant_wakeup.pending_wakeup_count("s1") == 0
    assert not assistant_wakeup._DRAIN_TASKS


@pytest.mark.asyncio
async def test_terminal_request_queues_pending_and_drains(monkeypatch):
    from app.social import assistant_wakeup
    from app.social.assistant_runs import _request_wake_after_terminal

    record = _record("delegation_b", "s1")
    seen: list = []
    captured = asyncio.Event()

    async def fake_run_wake_turn(session_id, records):
        seen.append((session_id, list(records)))
        captured.set()

    monkeypatch.setattr(assistant_wakeup, "_run_wake_turn", fake_run_wake_turn)
    _request_wake_after_terminal(record)
    assert record["wake_state"] == "pending"
    assert await _wait_until(captured.is_set)
    assert seen and seen[0][1][0]["run_id"] == "delegation_b"


@pytest.mark.asyncio
async def test_user_cancelled_delegation_discards_without_wake():
    from app.social import assistant_wakeup
    from app.social.assistant_runs import _request_wake_after_terminal

    record = _record("delegation_c", "s1", status="cancelled")
    _request_wake_after_terminal(record)
    assert record["wake_state"] == "discarded"
    assert assistant_wakeup.pending_wakeup_count("s1") == 0


@pytest.mark.asyncio
async def test_absorbed_records_are_skipped_without_register():
    from app.social.assistant_wakeup import _run_wake_turn

    record = _record("delegation_d", "s1")
    record["wake_state"] = "absorbed_in_turn"
    # 记录已被交付边界认领：不进入 register，直接收口跳过。
    await asyncio.wait_for(_run_wake_turn("s1", [record]), timeout=2.0)


@pytest.mark.asyncio
async def test_busy_session_waits_then_wakes(monkeypatch):
    from app.agent.runtime.cancellation import cancellation_registry
    from app.social import assistant_wakeup

    record = _record("delegation_e", "s-busy")
    started = asyncio.Event()
    release = asyncio.Event()
    appended: list = []

    async def fake_synthesize(session_id, owner, records, cancel_event):
        started.set()
        await release.wait()
        return "整合结论"

    async def fake_append(session_id, answer, records, wake_id):
        appended.append(answer)
        return "msg_9"

    monkeypatch.setattr(assistant_wakeup, "_resolve_owner", _fake_owner)
    monkeypatch.setattr(assistant_wakeup, "_synthesize_wake_reply", fake_synthesize)
    monkeypatch.setattr(assistant_wakeup, "_append_wake_reply", fake_append)

    handle = await cancellation_registry.register("s-busy")
    try:
        assistant_wakeup.request_delegation_wakeup(record)
        # 活跃回合未结束：唤醒卡在 register 排队，未进入合成入口。
        await asyncio.sleep(0.15)
        assert not started.is_set()
        await cancellation_registry.unregister("s-busy", handle)
        assert await _wait_until(started.is_set)
        assert not appended
        release.set()
        assert await _wait_until(lambda: bool(appended))
        assert appended == ["整合结论"]
        assert record["wake_state"] == "promoted"
        assert record["wake_message_id"] == "msg_9"
    finally:
        release.set()


@pytest.mark.asyncio
async def test_multiple_delegations_batch_into_single_turn(monkeypatch):
    from app.social import assistant_wakeup

    records = [_record("delegation_f1", "s1"), _record("delegation_f2", "s1")]
    seen: list = []
    captured = asyncio.Event()

    async def fake_run_wake_turn(session_id, batch):
        seen.append(list(batch))
        captured.set()

    monkeypatch.setattr(assistant_wakeup, "_run_wake_turn", fake_run_wake_turn)
    for record in records:
        assistant_wakeup.request_delegation_wakeup(record)
    assert await _wait_until(captured.is_set)
    assert len(seen) == 1
    assert {record["run_id"] for record in seen[0]} == {"delegation_f1", "delegation_f2"}


@pytest.mark.asyncio
async def test_superseded_wake_requeues_then_discards_at_cap(monkeypatch):
    from app.agent.runtime.cancellation import cancellation_registry
    from app.social import assistant_wakeup

    record = _record("delegation_g", "s-sup")
    monkeypatch.setattr(assistant_wakeup, "_resolve_owner", _fake_owner)
    monkeypatch.setattr(assistant_wakeup, "_append_wake_reply", _fail_append)

    async def fake_synthesize(session_id, owner, records, cancel_event):
        # 模拟新用户消息顶掉唤醒回合：先留下 superseded 原因再抛取消。
        await cancellation_registry.cancel(session_id, reason="superseded_by_new_run")
        raise asyncio.CancelledError

    monkeypatch.setattr(assistant_wakeup, "_synthesize_wake_reply", fake_synthesize)
    try:
        # 直接调用 _run_wake_turn：由它自己 register；fake 在回合内以
        # superseded_by_new_run 取消并抛 CancelledError → 断言取消向上传播。
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(
                assistant_wakeup._run_wake_turn("s-sup", [record]), timeout=2.0
            )
        assert record["wake_state"] == "pending"
        assert record["wake_attempts"] == 1

        async def cancelled_synthesize(session_id, owner, records, cancel_event):
            raise asyncio.CancelledError

        monkeypatch.setattr(assistant_wakeup, "_synthesize_wake_reply", cancelled_synthesize)
        # 第二次被顶掉仍重排；随后把尝试次数顶到上限验证收口 discarded。
        for expected_attempts in (2, 3):
            record["wake_state"] = "pending"
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(
                    assistant_wakeup._run_wake_turn("s-sup", [record]), timeout=2.0
                )
            assert record["wake_attempts"] == expected_attempts
        assert record["wake_state"] == "discarded"
    finally:
        pass


@pytest.mark.asyncio
async def test_user_stop_discards_wake(monkeypatch):
    from app.agent.runtime.cancellation import cancellation_registry
    from app.social import assistant_wakeup

    record = _record("delegation_h", "s-stop")
    monkeypatch.setattr(assistant_wakeup, "_resolve_owner", _fake_owner)
    monkeypatch.setattr(assistant_wakeup, "_append_wake_reply", _fail_append)

    async def fake_synthesize(session_id, owner, records, cancel_event):
        await cancellation_registry.cancel(session_id, reason="user_paused")
        raise asyncio.CancelledError

    monkeypatch.setattr(assistant_wakeup, "_synthesize_wake_reply", fake_synthesize)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(
            assistant_wakeup._run_wake_turn("s-stop", [record]), timeout=2.0
        )
    assert record["wake_state"] == "discarded"
    assert "user_paused" in str(record.get("wake_state_reason"))


@pytest.mark.asyncio
async def test_empty_synthesis_falls_back_to_digest(monkeypatch):
    from app.social import assistant_wakeup

    record = _record("delegation_i", "s1")
    appended: list = []

    async def fake_synthesize(session_id, owner, records, cancel_event):
        return ""

    async def fake_append(session_id, answer, records, wake_id):
        appended.append(answer)
        return "msg_1"

    monkeypatch.setattr(assistant_wakeup, "_resolve_owner", _fake_owner)
    monkeypatch.setattr(assistant_wakeup, "_synthesize_wake_reply", fake_synthesize)
    monkeypatch.setattr(assistant_wakeup, "_append_wake_reply", fake_append)
    monkeypatch.setattr(assistant_wakeup, "_persist_record", lambda record: None)
    await asyncio.wait_for(assistant_wakeup._run_wake_turn("s1", [record]), timeout=2.0)
    assert appended and "succeeded" in appended[0] and "分析空气质量数据" in appended[0]
    assert record["wake_state"] == "promoted"


def test_build_wake_prompt_contract():
    from app.social.assistant_wakeup import build_wake_prompt

    record = _record("delegation_j", "s1")
    prompt = build_wake_prompt([record])
    assert "<task-notification>" in prompt
    assert "<run-id>delegation_j</run-id>" in prompt
    assert "<target-mode>expert_analysis</target-mode>" in prompt
    assert "<status>succeeded</status>" in prompt
    assert "<summary>月均AQI 75.2</summary>" in prompt
    assert "<data-gaps>缺站点经纬度</data-gaps>" in prompt
    assert "<artifacts>file:M:/tmp/result.json</artifacts>" in prompt
    assert "manage_assistant_runs action=result run_id=delegation_j" in prompt
    assert "不得当作零" in prompt
    assert "不要重启或伪造已受理的委派" in prompt


@pytest.mark.asyncio
async def test_wait_for_session_runs_marks_absorbed(monkeypatch):
    """交付边界吸收方就地认领：完成回调据此让路，不再触发唤醒。"""
    from app.social import assistant_wakeup
    from app.social.assistant_runs import (
        AssistantRunService,
        _PENDING_BY_SESSION,
        _request_wake_after_terminal,
    )

    record = _record("delegation_k", "s-abs")
    requested: list = []
    monkeypatch.setattr(
        assistant_wakeup,
        "request_delegation_wakeup",
        lambda item: requested.append(item),
    )

    async def job():
        pass

    task = asyncio.ensure_future(job())
    task._assistant_run_record = record
    _PENDING_BY_SESSION.setdefault("s-abs", set()).add(task)
    try:
        await asyncio.sleep(0.05)
        service = object.__new__(AssistantRunService)
        results, pending = await service.wait_for_session_runs("s-abs", timeout=2.0)
        assert pending == 0 and len(results) == 1
        assert record["wake_state"] == "absorbed_in_turn"
        # 交付边界认领后，完成回调不再请求唤醒。
        _request_wake_after_terminal(record)
        assert not requested
        assert assistant_wakeup.pending_wakeup_count("s-abs") == 0
    finally:
        _PENDING_BY_SESSION.pop("s-abs", None)


@pytest.mark.asyncio
async def test_session_missing_discards_wake(monkeypatch):
    from app.social import assistant_wakeup

    record = _record("delegation_l", "s-gone")

    async def fake_synthesize(session_id, owner, records, cancel_event):
        return "答案"

    async def fake_append(session_id, answer, records, wake_id):
        return None

    monkeypatch.setattr(assistant_wakeup, "_resolve_owner", _fake_owner)
    monkeypatch.setattr(assistant_wakeup, "_synthesize_wake_reply", fake_synthesize)
    monkeypatch.setattr(assistant_wakeup, "_append_wake_reply", fake_append)
    persisted: list = []
    monkeypatch.setattr(assistant_wakeup, "_persist_record", lambda item: persisted.append(item))
    await asyncio.wait_for(assistant_wakeup._run_wake_turn("s-gone", [record]), timeout=2.0)
    assert record["wake_state"] == "discarded"
    assert record["wake_state_reason"] == "session_missing"


@pytest.mark.asyncio
async def test_session_lock_timeout_discards(monkeypatch):
    """跨 worker 会话锁长时间占不到（超过交付边界等待上限）：收口 discarded。"""
    import contextlib

    from app.agent.runtime import session_advisory_lock as lock_module
    from app.social import assistant_wakeup

    record = _record("delegation_m", "s-lock")

    @contextlib.asynccontextmanager
    async def conflict_lock(session_id, *, wait_timeout=0):
        raise lock_module.SessionRunConflict("session_run_in_progress")
        yield  # pragma: no cover

    monkeypatch.setattr(lock_module, "session_advisory_lock", conflict_lock)
    monkeypatch.setattr(assistant_wakeup, "_resolve_owner", _fake_owner)
    monkeypatch.setattr(assistant_wakeup, "_append_wake_reply", _fail_append)
    persisted: list = []
    monkeypatch.setattr(assistant_wakeup, "_persist_record", lambda item: persisted.append(item))
    await asyncio.wait_for(assistant_wakeup._run_wake_turn("s-lock", [record]), timeout=2.0)
    assert record["wake_state"] == "discarded"
    assert record["wake_state_reason"] == "session_lock_timeout"


async def _fake_owner(session_id, record):
    return "user-1"


async def _fail_append(session_id, answer, records, wake_id):
    raise AssertionError("唤醒被取消后不应落库")
