import asyncio

import pytest

from app.agent.workflow.registry import ActiveWorkflowRegistry


class _Coordinator:
    def __init__(self):
        self.reasons = []

    async def cancel(self, *, reason):
        self.reasons.append(reason)


class _Store:
    def __init__(self):
        self.states = {}

    async def register(self, key, run_id):
        if key in self.states:
            return False
        self.states[key] = type("State", (), {"run_id": run_id, "status": "running", "reason": None})()
        return True

    async def request_cancel(self, key, expected_run_id, reason):
        state = self.states.get(key)
        if not state or state.run_id != expected_run_id:
            return False
        state.status = "pause_requested"
        state.reason = reason
        return True

    async def get(self, key):
        return self.states.get(key)

    async def finish(self, key, run_id):
        self.states.pop(key, None)
        return True


@pytest.mark.asyncio
async def test_registry_tracks_and_cancels_live_workflow():
    registry = ActiveWorkflowRegistry()
    coordinator = _Coordinator()
    await registry.register("wf-1", coordinator, session_id="session-1")

    assert (await registry.get("wf-1")).session_id == "session-1"
    assert await registry.cancel("wf-1", reason="user requested") is True
    assert coordinator.reasons == ["user requested"]
    await registry.unregister("wf-1", coordinator)
    assert await registry.get("wf-1") is None


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_active_workflow():
    registry = ActiveWorkflowRegistry()
    first = _Coordinator()
    second = _Coordinator()
    await registry.register("wf-1", first)
    with pytest.raises(ValueError, match="already active"):
        await registry.register("wf-1", second)
    await registry.unregister("wf-1", first)
    assert await registry.get("wf-1") is None


@pytest.mark.asyncio
async def test_registry_accepts_remote_cancel_signal():
    store = _Store()
    registry = ActiveWorkflowRegistry(store=store, poll_interval=0.01)
    coordinator = _Coordinator()
    await registry.register("wf-remote", coordinator)
    await store.request_cancel("agent-workflow:wf-remote", "wf-remote", "remote stop")
    for _ in range(20):
        if coordinator.reasons:
            break
        await asyncio.sleep(0.01)
    assert coordinator.reasons == ["remote stop"]
    await registry.unregister("wf-remote", coordinator)
