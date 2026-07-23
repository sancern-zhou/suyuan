import pytest
from fastapi import HTTPException

from app.auth.models import CurrentUser
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource
from app.conversations.service import ConversationCatalogService


class FakeRepository:
    def __init__(self, records=()):
        self.records = {row.session_id: row for row in records}

    async def get(self, session_id):
        return self.records.get(session_id)

    async def upsert(self, record):
        self.records[record.session_id] = record
        return record

    async def list_visible(self, *, user_id, limit, offset, source=None):
        records = list(self.records.values())
        if user_id is not None:
            records = [row for row in records if row.owner_user_id == user_id]
        if source is not None:
            records = [row for row in records if row.source == source]
        return records[offset : offset + limit]

    async def delete(self, session_id):
        return self.records.pop(session_id, None) is not None


def row(owner="u1", source=ConversationSource.WEB, read_only=False):
    return ConversationCatalogRecord(
        session_id="s1",
        owner_user_id=owner,
        owner_username=owner,
        owner_display_name=owner,
        source=source,
        mode="assistant",
        title="hello",
        read_only_on_web=read_only,
    )


@pytest.mark.asyncio
async def test_owner_and_admin_can_read_catalog_record():
    service = ConversationCatalogService(FakeRepository([row()]))
    owner = CurrentUser(id="u1", username="u1", display_name="U1")
    admin = CurrentUser(
        id="admin", username="admin", display_name="Admin", is_admin=True
    )

    assert (await service.require_read("s1", owner)).session_id == "s1"
    assert (await service.require_read("s1", admin)).session_id == "s1"


@pytest.mark.asyncio
async def test_other_user_and_missing_session_both_return_404():
    service = ConversationCatalogService(FakeRepository([row()]))
    other = CurrentUser(id="u2", username="u2", display_name="U2")

    for session_id in ("s1", "missing"):
        with pytest.raises(HTTPException) as exc:
            await service.require_read(session_id, other)
        assert exc.value.status_code == 404
        assert exc.value.detail == "session_not_found"


@pytest.mark.asyncio
async def test_social_record_rejects_web_write_with_409():
    service = ConversationCatalogService(
        FakeRepository([row(source=ConversationSource.SOCIAL, read_only=True)])
    )
    owner = CurrentUser(id="u1", username="u1", display_name="U1")

    with pytest.raises(HTTPException) as exc:
        await service.require_write("s1", owner)
    assert exc.value.status_code == 409
    assert exc.value.detail == "social_session_read_only"


@pytest.mark.asyncio
async def test_claim_web_draft_registers_new_session_for_current_user():
    repository = FakeRepository()
    service = ConversationCatalogService(repository)
    owner = CurrentUser(id="u1", username="u1", display_name="U1")

    claimed = await service.claim_web_draft(
        session_id="draft-1",
        user=owner,
        mode="assistant",
    )

    assert claimed.owner_user_id == "u1"
    assert claimed.source == ConversationSource.WEB
    assert claimed.mode == "assistant"


@pytest.mark.asyncio
async def test_claim_web_draft_rejects_session_owned_by_another_user():
    service = ConversationCatalogService(FakeRepository([row()]))
    other = CurrentUser(id="u2", username="u2", display_name="U2")

    with pytest.raises(HTTPException) as exc:
        await service.claim_web_draft(
            session_id="s1",
            user=other,
            mode="assistant",
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "session_not_found"


@pytest.mark.asyncio
async def test_registration_cannot_reassign_existing_catalog_identity():
    service = ConversationCatalogService(FakeRepository([row()]))

    with pytest.raises(RuntimeError, match="catalog_identity_conflict"):
        await service.register_identity(
            session_id="s1",
            owner_user_id="u2",
            owner_username="u2",
            owner_display_name="U2",
            source=ConversationSource.WEB,
            mode="assistant",
            title="changed",
        )


@pytest.mark.asyncio
async def test_ordinary_lists_only_self_while_admin_lists_all():
    second = row(owner="u2")
    second = second.model_copy(update={"session_id": "s2"})
    service = ConversationCatalogService(FakeRepository([row(), second]))
    ordinary = CurrentUser(id="u1", username="u1", display_name="U1")
    admin = CurrentUser(
        id="admin", username="admin", display_name="Admin", is_admin=True
    )

    assert [item.session_id for item in await service.list_visible(ordinary, limit=10)] == [
        "s1"
    ]
    assert {item.session_id for item in await service.list_visible(admin, limit=10)} == {
        "s1",
        "s2",
    }


@pytest.mark.asyncio
async def test_delete_removes_catalog_record_through_service_boundary():
    repository = FakeRepository([row()])
    service = ConversationCatalogService(repository)

    assert await service.delete("s1") is True
    assert await repository.get("s1") is None


@pytest.mark.asyncio
async def test_delete_removes_shared_resource_manifest_when_configured():
    deleted_manifests = []

    class ResourceService:
        async def delete(self, session_id):
            deleted_manifests.append(session_id)
            return True

    service = ConversationCatalogService(
        FakeRepository([row()]),
        resource_manifest_service=ResourceService(),
    )
    assert await service.delete("s1") is True
    assert deleted_manifests == ["s1"]
