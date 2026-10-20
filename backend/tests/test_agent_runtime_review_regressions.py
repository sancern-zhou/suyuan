"""Regression coverage for session ownership and native stream replay boundaries."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent.runtime.cancellation import CancellationRegistry, AgentRunCancelled
from app.agent.runtime.cancellation_state import InMemoryCancellationStateStore
from app.agent.runtime.session_advisory_lock import (
    SessionRunConflict, session_advisory_lock, serialize_agent_session,
)
from app.services.llm_service import LLMService
from app.services.llm_failover import LLMCandidate


@pytest.mark.asyncio
async def test_rejected_shared_claim_never_becomes_local_ownership():
    store = InMemoryCancellationStateStore()
    first, second = CancellationRegistry(store), CancellationRegistry(store)
    a, b = await first.register("s"), await second.register("s")
    try:
        assert await first.attach_run_id("s", a, "run-a")
        assert not await second.attach_run_id("s", b, "run-b")
        assert not await second.attach_run_id("s", b, "run-b")
        assert not await second.can_finalize("s", b)
        assert second._handles["s"].monitor_task is None
        assert await first.can_finalize("s", a)
        await store.finish("s", "run-a")
        assert not await second.can_finalize("s", b)
        await store.register("s", "replacement")
        assert not await first.can_finalize("s", a)
    finally:
        await second.unregister("s", b)
        await first.unregister("s", a)
    assert (await store.get("s")).run_id == "replacement"
    assert (await store.get("s")).status == "running"


@pytest.mark.asyncio
async def test_runtime_stops_before_execution_when_registration_fails(monkeypatch):
    from app.agent.runtime.agent_runtime import AgentRuntime
    from app.agent.runtime import agent_runtime as module

    runtime = object.__new__(AgentRuntime)
    runtime.memory = NS(session_id="s")
    runtime.executor = NS()
    runtime.config = NS(enhance_with_history=True, board_context=None, cancel_event=asyncio.Event())
    claim = AsyncMock(return_value=False)
    register_owner = AsyncMock()
    monkeypatch.setattr(module.cancellation_registry, "attach_run_id", claim)
    monkeypatch.setattr(module.run_ownership_registry, "register", register_owner)
    with pytest.raises(AgentRunCancelled, match="registration_rejected"):
        await anext(runtime.run("query"))
    register_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_session_rejected_across_tasks_but_other_sessions_and_reentry_work(fake_lock_db):
    async def competitor():
        with pytest.raises(SessionRunConflict):
            async with session_advisory_lock("s"):
                pytest.fail("competing run entered")
        async with session_advisory_lock("other"):
            pass

    async with session_advisory_lock("s"):
        async with session_advisory_lock("s"):
            assert len(fake_lock_db.connections) == 1
        await asyncio.create_task(competitor())
    assert not fake_lock_db.locked
    async with session_advisory_lock("s"):
        pass


@pytest.mark.asyncio
async def test_paused_continuation_can_wait_for_final_lock_release(fake_lock_db):
    async def continuation():
        async with session_advisory_lock("s", wait_timeout=1):
            return True
    async with session_advisory_lock("s"):
        next_run = asyncio.create_task(continuation())
        await asyncio.sleep(0)
        assert not next_run.done()
    assert await next_run
    assert not fake_lock_db.locked


@pytest.mark.asyncio
async def test_lock_released_on_cancel_and_invalidated_on_unlock_error(fake_lock_db):
    acquired = asyncio.Event()
    async def run():
        async with session_advisory_lock("s"):
            acquired.set()
            await asyncio.Event().wait()
    task = asyncio.create_task(run())
    await acquired.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not fake_lock_db.locked
    with pytest.raises(RuntimeError, match="unlock connection failure"):
        async with session_advisory_lock("s"):
            fake_lock_db.connections[-1].unlock_error = True
    assert fake_lock_db.connections[-1].invalidated
    assert not fake_lock_db.locked


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_in_child", [False, True])
async def test_direct_agent_entry_keeps_lock_until_generator_cleanup(fake_lock_db, cleanup_in_child):
    class Agent:
        @serialize_agent_session
        async def analyze(self, user_query, session_id=None):
            try:
                assert fake_lock_db.locked
                yield {"type": "start"}
            finally:
                assert fake_lock_db.locked  # persist before release
        def _generate_session_id(self): return "generated"
    gen = Agent().analyze("query")
    await anext(gen)
    assert fake_lock_db.locked
    if cleanup_in_child:
        await asyncio.create_task(gen.aclose())
    else:
        await gen.aclose()
    assert not fake_lock_db.locked
    async with session_advisory_lock("generated"):
        assert fake_lock_db.locked  # no stale re-entry after cross-task close


@pytest.mark.asyncio
@pytest.mark.parametrize("emitted", [0, 1, 3])
async def test_native_stream_fallback_only_before_any_observable_event(monkeypatch, emitted):
    class Stream:
        def __init__(self, fail): self.fail = fail
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def __aiter__(self): return self.events()
        async def events(self):
            events = [
                NS(type="message_start", message=NS(model="fake", usage=NS(input_tokens=1, output_tokens=0))),
                NS(type="content_block_start", index=0,
                   content_block=NS(type="tool_use", id="t1", name="read_state", input={})),
                NS(type="content_block_stop", index=0),
            ]
            for event in events[:emitted if self.fail else 3]: yield event
            if self.fail: raise httpx.ReadError("offline transport failure")
            yield NS(type="message_stop")

    class Service:
        provider, model, api_mode, request_fallbacks = "probe-a", "fake", "anthropic", ""
        anthropic_client = NS(messages=NS(stream=lambda **kwargs: Stream(True)))
        switched = False
        def _create_provider_override_service(self, *args): return None
        def _snapshot_provider_state(self): return dict(provider=self.provider, model=self.model)
        def _switch_provider_for_attempt(self, provider, model):
            self.provider = provider
            self.switched = True
            self.anthropic_client = NS(messages=NS(stream=lambda **kwargs: Stream(False)))
        def _restore_provider_state(self, state): pass
        def _build_anthropic_api_params(self, **kwargs): return {"messages": kwargs["messages"]}
        def provider_http_timeout(self, **kwargs): return 1
        def _is_context_overflow_error(self, error): return False

    monkeypatch.setattr("app.services.llm_service.get_cooldown_failure", lambda provider: None)
    monkeypatch.setattr("app.services.llm_service.mark_provider_cooldown", lambda *args: None)
    monkeypatch.setattr("app.services.llm_service.parse_fallback_candidates", lambda *args: [
        LLMCandidate("probe-a", "fake"), LLMCandidate("probe-b", "fake"),
    ])
    service = Service()
    events = []
    method = LLMService.chat_anthropic_streaming.__wrapped__
    if emitted:
        with pytest.raises(httpx.ReadError):
            async for event in method(service, messages=[{"role": "user", "content": "probe"}]):
                events.append(event)
        assert not service.switched
        assert len(events) == emitted
    else:
        events = [event async for event in method(service, messages=[{"role": "user", "content": "probe"}])]
        assert service.switched
    assert sum(e["type"] == "message_start" for e in events) == 1
    assert sum(e["type"] == "content_block_stop" for e in events) <= 1
