import pytest

from app.agent.workflow.registry import ActiveWorkflowRegistry


class _Coordinator:
    def __init__(self):
        self.reasons = []

    async def cancel(self, *, reason):
        self.reasons.append(reason)


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
