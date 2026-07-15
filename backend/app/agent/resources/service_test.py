import pytest

from app.agent.resources.models import ResourceKind, ResourceLocator, ResourceRole, SessionResourceRef
from app.agent.resources.service import (
    ManifestPersistenceError,
    SessionResourceManifest,
    SessionResourceManifestService,
)


def make_ref(data_id: str) -> SessionResourceRef:
    return SessionResourceRef.create(
        kind=ResourceKind.DATA,
        locator=ResourceLocator(data_id=data_id),
        role=ResourceRole.PRIMARY,
        label=data_id,
        tool_name="query",
        run_id=data_id,
        turn_sequence=1,
    )


class FakeRepository:
    def __init__(self):
        self.rows: dict[str, SessionResourceManifest] = {}

    async def load(self, session_id):
        return self.rows.get(session_id, SessionResourceManifest(session_id=session_id))

    async def merge(self, session_id, incoming):
        from app.agent.resources.manifest import merge_resource_refs

        current = await self.load(session_id)
        if not incoming:
            return current
        saved = SessionResourceManifest(
            session_id=session_id,
            refs=merge_resource_refs(current.refs, incoming),
            version=current.version + 1,
        )
        self.rows[session_id] = saved
        return saved

    async def delete(self, session_id):
        return self.rows.pop(session_id, None) is not None


@pytest.mark.asyncio
async def test_same_session_id_has_one_manifest_without_mode_parameter():
    service = SessionResourceManifestService(FakeRepository())
    await service.merge("shared-a", [make_ref("data:v1:web")])
    await service.merge("shared-a", [make_ref("data:v1:social")])
    loaded = await service.load("shared-a")
    assert {ref.locator.data_id for ref in loaded.refs} == {"data:v1:web", "data:v1:social"}
    assert loaded.version == 2


@pytest.mark.asyncio
async def test_empty_merge_does_not_clear_or_increment():
    service = SessionResourceManifestService(FakeRepository())
    first = await service.merge("shared-a", [make_ref("data:v1:a")])
    second = await service.merge("shared-a", [])
    assert second == first


@pytest.mark.asyncio
async def test_repository_failure_is_never_reported_as_success():
    class FailingRepository(FakeRepository):
        async def merge(self, session_id, incoming):
            raise RuntimeError("database unavailable")

    service = SessionResourceManifestService(FailingRepository())
    with pytest.raises(ManifestPersistenceError, match="merge"):
        await service.merge("shared-a", [make_ref("data:v1:a")])


@pytest.mark.asyncio
async def test_delete_is_idempotent():
    service = SessionResourceManifestService(FakeRepository())
    await service.merge("shared-a", [make_ref("data:v1:a")])
    assert await service.delete("shared-a") is True
    assert await service.delete("shared-a") is False
