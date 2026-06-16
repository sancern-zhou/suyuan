import pytest

from app.agent.runtime.ownership import RunOwnershipRegistry


@pytest.mark.asyncio
async def test_revoke_run_immediately_disallows_stale_writes():
    registry = RunOwnershipRegistry()

    await registry.register("session_a", "run_old")
    assert await registry.can_write("session_a", "run_old") is True

    revoked = await registry.revoke("session_a", "run_old")

    assert revoked is True
    assert await registry.can_write("session_a", "run_old") is False


@pytest.mark.asyncio
async def test_new_run_takes_write_ownership_from_old_run():
    registry = RunOwnershipRegistry()

    await registry.register("session_a", "run_old")
    await registry.register("session_a", "run_new")

    assert await registry.can_write("session_a", "run_old") is False
    assert await registry.can_write("session_a", "run_new") is True
