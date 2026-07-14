from types import SimpleNamespace

import pytest

from app.knowledge_base.conversation_store import (
    ConversationAccessDenied,
    ConversationStore,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDB:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        return _ScalarResult(self.existing)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, value):
        return None


@pytest.mark.asyncio
async def test_existing_knowledge_session_rejects_different_user():
    db = _FakeDB(SimpleNamespace(user_id="owner", turns=[]))
    store = ConversationStore(db)

    with pytest.raises(ConversationAccessDenied):
        await store.get_or_create_session(session_id="kqa-1", user_id="intruder")

    assert db.commits == 0


@pytest.mark.asyncio
async def test_new_knowledge_session_adds_catalog_before_single_commit():
    db = _FakeDB()
    store = ConversationStore(db)

    session_id, turns, is_new = await store.get_or_create_session(
        user_id="7",
        owner_username="alice",
        owner_display_name="Alice",
        first_query="hello",
    )

    assert session_id.startswith("kqa_")
    assert turns == []
    assert is_new is True
    assert [type(value).__name__ for value in db.added] == [
        "ConversationSession",
        "ConversationCatalogDB",
    ]
    assert db.added[1].owner_user_id == "7"
    assert db.added[1].owner_username == "alice"
    assert db.added[1].source == "knowledge_qa"
    assert db.commits == 1
