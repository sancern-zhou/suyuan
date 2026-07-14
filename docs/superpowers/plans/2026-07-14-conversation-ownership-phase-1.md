# Conversation Ownership Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce administrator/owner access for Web ReAct and knowledge-QA conversations through one authoritative catalog, with existing unowned history assigned to platform user `1`.

**Architecture:** Add a small conversation-catalog package backed by PostgreSQL and make it the authorization authority before any source store is read. Web sessions and knowledge-QA sessions keep their existing message stores; adapters convert both sources into the existing session-history response shape. The rollout creates and backfills catalog records before fail-closed enforcement is enabled.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async, PostgreSQL, pytest, Vue 3, Pinia

---

## File Structure

- Create `backend/app/conversations/models.py`: SQLAlchemy catalog row.
- Create `backend/app/conversations/schemas.py`: source enum and catalog DTOs.
- Create `backend/app/conversations/repository.py`: catalog persistence and filtered pagination.
- Create `backend/app/conversations/service.py`: registration, authorization, read-only checks, and source dispatch metadata.
- Create `backend/app/conversations/dependencies.py`: FastAPI dependency accessors.
- Create `backend/app/conversations/adapters.py`: Web and knowledge-QA summary/detail adapters.
- Create `backend/app/conversations/__init__.py`: public package exports.
- Create `backend/app/db/migrations/006_create_conversation_catalog.sql`: schema and idempotent backfill.
- Create `backend/tests/conversations/`: focused authentication, policy, migration, route, and adapter tests.
- Modify `backend/app/auth/models.py`: parse `admin` and `roleCodeList`.
- Modify `backend/app/auth/platform_client.py`: no protocol change; retain normalized payload path.
- Modify `backend/app/routers/agent.py`: register new Web sessions and authorize reuse/cancel/steer.
- Modify `backend/app/api/session_routes.py`: catalog-backed list, stats, detail, artifacts, mutation, import/export, and cleanup.
- Modify `backend/app/routers/knowledge_qa.py`: current-user-only create/reuse/history/archive/delete.
- Modify `backend/app/knowledge_base/conversation_store.py`: owner-aware queries and atomic catalog creation.
- Modify `frontend/src/components/management/SessionHistoryPanel.vue`: source and administrator owner labels.
- Modify `frontend/src/composables/reactAnalysis/useSessionManagement.js`: retain catalog metadata when merging history rows.

### Task 1: Parse Company Administrator Identity Safely

**Files:**
- Modify: `backend/app/auth/models.py`
- Test: `backend/tests/auth/test_platform_client.py`
- Test: `backend/tests/auth/test_auth_service.py`

- [ ] **Step 1: Write failing payload-normalization tests**

Add these tests to `backend/tests/auth/test_platform_client.py`:

```python
def test_company_admin_boolean_and_role_code_list_are_normalized():
    user = CurrentUser.from_company_payload(
        {
            "id": 1,
            "userName": "ScGuanLy",
            "name": "超级管理员",
            "admin": True,
            "roleCodeList": [{"roleCode": "OPS"}],
        },
        admin_role_codes=set(),
        sys_code="SUYUAN",
    )

    assert user.id == "1"
    assert user.role_codes == ("OPS",)
    assert user.is_admin is True


@pytest.mark.parametrize("value", [None, False, "true", 1, [], {}])
def test_company_admin_requires_literal_true(value):
    user = CurrentUser.from_company_payload(
        {"id": "u1", "userName": "user", "admin": value},
        admin_role_codes=set(),
        sys_code="SUYUAN",
    )

    assert user.is_admin is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/auth/test_platform_client.py -q
```

Expected: the first test fails because `roleCodeList` and `admin` are ignored.

- [ ] **Step 3: Implement strict administrator parsing**

Update the role lookup and constructor in `backend/app/auth/models.py`:

```python
role_codes = _role_codes(payload)
platform_admin = payload.get("admin") is True
return cls(
    id=user_id,
    username=username,
    display_name=display_name,
    role_codes=role_codes,
    is_admin=platform_admin or bool(set(role_codes).intersection(admin_role_codes)),
    sys_code=sys_code,
    auth_source="company",
)
```

Use this ordered fallback in `_role_codes`:

```python
raw_roles = payload.get("roleCodes")
if raw_roles is None:
    raw_roles = payload.get("roles")
if raw_roles is None:
    raw_roles = payload.get("roleList")
if raw_roles is None:
    raw_roles = payload.get("roleCodeList")
```

- [ ] **Step 4: Run authentication tests and verify GREEN**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/auth/test_platform_client.py backend/tests/auth/test_auth_service.py -q
```

Expected: all authentication tests pass.

- [ ] **Step 5: Commit the identity change**

```bash
git add backend/app/auth/models.py backend/tests/auth/test_platform_client.py backend/tests/auth/test_auth_service.py
git commit -m "fix: normalize company administrator identity"
```

### Task 2: Build the Authoritative Conversation Catalog

**Files:**
- Create: `backend/app/conversations/__init__.py`
- Create: `backend/app/conversations/models.py`
- Create: `backend/app/conversations/schemas.py`
- Create: `backend/app/conversations/repository.py`
- Create: `backend/app/conversations/service.py`
- Create: `backend/app/conversations/dependencies.py`
- Test: `backend/tests/conversations/test_catalog_service.py`

- [ ] **Step 1: Write failing access-policy tests**

Create `backend/tests/conversations/test_catalog_service.py`:

```python
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
    admin = CurrentUser(id="admin", username="admin", display_name="Admin", is_admin=True)

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
```

- [ ] **Step 2: Run the catalog test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/conversations/test_catalog_service.py -q
```

Expected: collection fails because `app.conversations` does not exist.

- [ ] **Step 3: Add catalog schemas and ORM model**

Create `backend/app/conversations/schemas.py`:

```python
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ConversationSource(str, Enum):
    WEB = "web"
    KNOWLEDGE_QA = "knowledge_qa"
    SOCIAL = "social"


class ConversationCatalogRecord(BaseModel):
    session_id: str
    owner_user_id: str
    owner_username: str
    owner_display_name: str
    source: ConversationSource
    mode: str | None = None
    title: str | None = None
    read_only_on_web: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

Create `backend/app/conversations/models.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text

from app.db.database import Base


class ConversationCatalogDB(Base):
    __tablename__ = "conversation_catalog"

    session_id = Column(String(255), primary_key=True)
    owner_user_id = Column(String(255), nullable=False)
    owner_username = Column(String(255), nullable=False)
    owner_display_name = Column(String(255), nullable=False)
    source = Column(String(32), nullable=False)
    mode = Column(String(50), nullable=True)
    title = Column(Text, nullable=True)
    read_only_on_web = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_conversation_catalog_owner_updated", "owner_user_id", "updated_at"),
        Index("ix_conversation_catalog_source_updated", "source", "updated_at"),
    )
```

- [ ] **Step 4: Add repository, service, and dependencies**

Implement `ConversationCatalogRepository` in `repository.py` with these public methods and concrete query behavior:

```python
class ConversationCatalogRepository:
    @staticmethod
    def _record(row: ConversationCatalogDB) -> ConversationCatalogRecord:
        return ConversationCatalogRecord.model_validate({
            column.name: getattr(row, column.name)
            for column in ConversationCatalogDB.__table__.columns
        })

    async def get(self, session_id: str) -> ConversationCatalogRecord | None:
        async with async_session() as session:
            row = await session.get(ConversationCatalogDB, session_id)
            return self._record(row) if row else None

    async def upsert(self, record: ConversationCatalogRecord) -> ConversationCatalogRecord:
        values = record.model_dump(mode="python")
        stmt = insert(ConversationCatalogDB).values(**values).on_conflict_do_update(
            index_elements=[ConversationCatalogDB.session_id],
            set_={
                "mode": values["mode"],
                "title": values["title"],
                "updated_at": values["updated_at"],
            },
        )
        async with async_session() as session:
            await session.execute(stmt)
            await session.commit()
        stored = await self.get(record.session_id)
        if stored is None:
            raise RuntimeError("catalog_upsert_failed")
        return stored

    async def delete(self, session_id: str) -> bool:
        async with async_session() as session:
            result = await session.execute(
                delete(ConversationCatalogDB).where(
                    ConversationCatalogDB.session_id == session_id
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def list_visible(self, *, user_id, limit, offset, source=None):
        stmt = select(ConversationCatalogDB)
        if user_id is not None:
            stmt = stmt.where(ConversationCatalogDB.owner_user_id == user_id)
        if source is not None:
            stmt = stmt.where(ConversationCatalogDB.source == source.value)
        stmt = stmt.order_by(ConversationCatalogDB.updated_at.desc()).offset(offset).limit(limit)
        async with async_session() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._record(row) for row in rows]

    async def count_visible(self, *, user_id: str | None) -> int:
        stmt = select(func.count()).select_from(ConversationCatalogDB)
        if user_id is not None:
            stmt = stmt.where(ConversationCatalogDB.owner_user_id == user_id)
        async with async_session() as session:
            return int((await session.scalar(stmt)) or 0)

    async def touch(self, session_id: str, *, title: str | None = None) -> bool:
        values = {"updated_at": datetime.utcnow()}
        if title is not None:
            values["title"] = title
        async with async_session() as session:
            result = await session.execute(
                update(ConversationCatalogDB)
                .where(ConversationCatalogDB.session_id == session_id)
                .values(**values)
            )
            await session.commit()
            return result.rowcount > 0
```

Import `datetime`, `select`, `update`, `delete`, `func`, PostgreSQL `insert`, `async_session`, the ORM model, and schemas used by this code.

Implement `service.py`:

```python
from fastapi import HTTPException

from app.auth.models import CurrentUser
from .schemas import ConversationCatalogRecord, ConversationSource


class ConversationCatalogService:
    def __init__(self, repository):
        self.repository = repository

    async def register(
        self, *, session_id: str, user: CurrentUser, source: ConversationSource,
        mode: str | None, title: str | None, read_only_on_web: bool = False,
    ) -> ConversationCatalogRecord:
        return await self.register_identity(
            session_id=session_id,
            owner_user_id=user.id,
            owner_username=user.username,
            owner_display_name=user.display_name,
            source=source,
            mode=mode,
            title=title,
            read_only_on_web=read_only_on_web,
        )

    async def register_identity(
        self, *, session_id: str, owner_user_id: str, owner_username: str,
        owner_display_name: str, source: ConversationSource, mode: str | None,
        title: str | None, read_only_on_web: bool = False,
    ) -> ConversationCatalogRecord:
        existing = await self.repository.get(session_id)
        if existing:
            if existing.owner_user_id != owner_user_id or existing.source != source:
                raise RuntimeError("catalog_identity_conflict")
            return existing
        return await self.repository.upsert(ConversationCatalogRecord(
            session_id=session_id,
            owner_user_id=owner_user_id,
            owner_username=owner_username,
            owner_display_name=owner_display_name,
            source=source,
            mode=mode,
            title=title,
            read_only_on_web=read_only_on_web,
        ))

    async def require_read(self, session_id: str, user: CurrentUser):
        row = await self.repository.get(session_id)
        if row is None or (not user.is_admin and row.owner_user_id != user.id):
            raise HTTPException(status_code=404, detail="session_not_found")
        return row

    async def require_write(self, session_id: str, user: CurrentUser):
        row = await self.require_read(session_id, user)
        if row.read_only_on_web:
            raise HTTPException(status_code=409, detail="social_session_read_only")
        return row

    async def list_visible(self, user: CurrentUser, *, limit: int, offset: int = 0):
        return await self.repository.list_visible(
            user_id=None if user.is_admin else user.id,
            limit=limit,
            offset=offset,
        )
```

Expose a singleton service from `dependencies.py`:

```python
from .repository import ConversationCatalogRepository
from .service import ConversationCatalogService

_service = ConversationCatalogService(ConversationCatalogRepository())


def get_conversation_catalog() -> ConversationCatalogService:
    return _service
```

- [ ] **Step 5: Export package API and verify GREEN**

Create `backend/app/conversations/__init__.py`:

```python
from .dependencies import get_conversation_catalog
from .schemas import ConversationCatalogRecord, ConversationSource
from .service import ConversationCatalogService

__all__ = [
    "ConversationCatalogRecord",
    "ConversationCatalogService",
    "ConversationSource",
    "get_conversation_catalog",
]
```

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/conversations/test_catalog_service.py -q
```

Expected: all catalog policy tests pass.

- [ ] **Step 6: Commit the catalog core**

```bash
git add backend/app/conversations backend/tests/conversations/test_catalog_service.py
git commit -m "feat: add authoritative conversation catalog"
```

### Task 3: Create and Backfill the Catalog Schema

**Files:**
- Create: `backend/app/db/migrations/006_create_conversation_catalog.sql`
- Create: `backend/tests/conversations/test_catalog_migration.py`

- [ ] **Step 1: Write a failing migration-contract test**

Create `backend/tests/conversations/test_catalog_migration.py`:

```python
from pathlib import Path


def test_catalog_migration_is_idempotent_and_backfills_required_sources():
    sql = Path("backend/app/db/migrations/006_create_conversation_catalog.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS conversation_catalog" in sql
    assert "ON CONFLICT (session_id) DO NOTHING" in sql
    assert "FROM sessions" in sql
    assert "FROM knowledge_conversation_sessions" in sql
    assert "'1', 'ScGuanLy', '超级管理员'" in sql
    assert "WHERE user_id IS NULL" in sql
    assert "social_session_mappings" not in sql
```

- [ ] **Step 2: Run the migration test and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/conversations/test_catalog_migration.py -q
```

Expected: fails because the SQL file does not exist.

- [ ] **Step 3: Add idempotent schema and backfill SQL**

Create `006_create_conversation_catalog.sql` with this structure:

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS conversation_catalog (
    session_id VARCHAR(255) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    owner_username VARCHAR(255) NOT NULL,
    owner_display_name VARCHAR(255) NOT NULL,
    source VARCHAR(32) NOT NULL CHECK (source IN ('web', 'knowledge_qa', 'social')),
    mode VARCHAR(50),
    title TEXT,
    read_only_on_web BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_conversation_catalog_owner_updated
    ON conversation_catalog(owner_user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_conversation_catalog_source_updated
    ON conversation_catalog(source, updated_at DESC);

INSERT INTO conversation_catalog (
    session_id, owner_user_id, owner_username, owner_display_name,
    source, mode, title, read_only_on_web, created_at, updated_at
)
SELECT session_id, '1', 'ScGuanLy', '超级管理员',
       'web', mode, LEFT(query, 256), FALSE, created_at, updated_at
FROM sessions
ON CONFLICT (session_id) DO NOTHING;

UPDATE knowledge_conversation_sessions
SET user_id = '1'
WHERE user_id IS NULL;

INSERT INTO conversation_catalog (
    session_id, owner_user_id, owner_username, owner_display_name,
    source, mode, title, read_only_on_web, created_at, updated_at
)
SELECT id, user_id,
       CASE WHEN user_id = '1' THEN 'ScGuanLy' ELSE user_id END,
       CASE WHEN user_id = '1' THEN '超级管理员' ELSE user_id END,
       'knowledge_qa', 'knowledge_qa', title, FALSE, created_at, updated_at
FROM knowledge_conversation_sessions
ON CONFLICT (session_id) DO NOTHING;

COMMIT;
```

- [ ] **Step 4: Run the migration contract test and SQL lint check**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/conversations/test_catalog_migration.py -q
git diff --check -- backend/app/db/migrations/006_create_conversation_catalog.sql
```

Expected: test passes and `git diff --check` prints nothing.

- [ ] **Step 5: Commit the migration**

```bash
git add backend/app/db/migrations/006_create_conversation_catalog.sql backend/tests/conversations/test_catalog_migration.py
git commit -m "feat: migrate existing conversation ownership"
```

### Task 4: Enforce Ownership on Web Agent Creation and Runtime Controls

**Files:**
- Modify: `backend/app/routers/agent.py`
- Create: `backend/tests/api/test_agent_conversation_access.py`

- [ ] **Step 1: Write failing route-policy tests**

Create a small FastAPI test app in `test_agent_conversation_access.py` that overrides `require_current_user` and `get_conversation_catalog`. Cover these behaviors:

```python
@pytest.mark.asyncio
async def test_reusing_session_requires_write_access(monkeypatch):
    catalog = RecordingCatalog(deny_write=True)
    request = AgentAnalyzeRequest(query="continue", session_id="other-session")

    with pytest.raises(HTTPException) as exc:
        await analyze_stream(request, FakeRequest({}), user=ordinary_user, catalog=catalog)

    assert exc.value.status_code == 404
    assert catalog.write_checks == ["other-session"]


@pytest.mark.asyncio
async def test_cancel_and_steer_require_write_access(monkeypatch):
    catalog = RecordingCatalog(deny_write=True)
    for operation in (
        lambda: cancel_analysis("other-session", ordinary_user, catalog),
        lambda: steer_analysis("other-session", AgentSteerRequest(message="x"), ordinary_user, catalog),
    ):
        with pytest.raises(HTTPException) as exc:
            await operation()
        assert exc.value.status_code == 404
```

The fake catalog must record `register`, `require_read`, and `require_write` calls without touching PostgreSQL.

- [ ] **Step 2: Run the focused route tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_agent_conversation_access.py -q
```

Expected: endpoint signatures do not accept authenticated user/catalog and no access check occurs.

- [ ] **Step 3: Add authenticated dependencies and pre-load checks**

Change the endpoint signatures in `agent.py`:

```python
from fastapi import Depends
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations import ConversationSource
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.service import ConversationCatalogService


async def analyze_stream(
    request: AgentAnalyzeRequest,
    raw_request: Request,
    user: CurrentUser = Depends(require_current_user),
    catalog: ConversationCatalogService = Depends(get_conversation_catalog),
):
    if request.session_id:
        await catalog.require_write(request.session_id, user)
```

Apply the same dependency pattern to `cancel_analysis` and `steer_analysis`, and call `require_write` before consulting runtime registries.

When `analyze_stream` creates a new generated `actual_session_id`, save the empty session first, verify the save result, then register it:

```python
saved = await session_manager.save_session_metadata(session)
if not saved:
    raise HTTPException(status_code=500, detail="session_create_failed")
try:
    await catalog.register(
        session_id=actual_session_id,
        user=user,
        source=ConversationSource.WEB,
        mode=request.mode or "assistant",
        title=request.query[:256],
    )
except Exception:
    await session_manager.delete_session(actual_session_id)
    raise
```

For an existing authorized session, retain the current metadata-save path and call `repository.touch` only after a successful save.

- [ ] **Step 4: Run route and existing agent tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_agent_conversation_access.py backend/tests/test_react_loop_with_adapter.py -q
```

Expected: access tests and existing agent flow tests pass.

- [ ] **Step 5: Commit Web runtime enforcement**

```bash
git add backend/app/routers/agent.py backend/tests/api/test_agent_conversation_access.py
git commit -m "feat: enforce ownership on agent sessions"
```

### Task 5: Replace Session APIs with Catalog-Authorized Dispatch

**Files:**
- Create: `backend/app/conversations/adapters.py`
- Modify: `backend/app/api/session_routes.py`
- Create: `backend/tests/api/test_session_catalog_routes.py`

- [ ] **Step 1: Write failing IDOR and list tests**

Create `test_session_catalog_routes.py` with a fake catalog and fake source adapters. Exercise the real router through `TestClient`:

```python
def test_ordinary_list_is_scoped_and_admin_list_contains_owner_metadata():
    ordinary_response = ordinary_client.get("/api/sessions")
    assert [row["owner_user_id"] for row in ordinary_response.json()["sessions"]] == ["u1"]

    admin_response = admin_client.get("/api/sessions")
    assert {row["owner_user_id"] for row in admin_response.json()["sessions"]} == {"u1", "u2"}


@pytest.mark.parametrize("suffix", [
    "", "/messages", "/visualizations", "/office-documents", "/drawio-board", "/restore",
])
def test_other_users_session_is_hidden_for_every_read_endpoint(suffix):
    method = ordinary_client.post if suffix == "/restore" else ordinary_client.get
    response = method(f"/api/sessions/u2-session{suffix}")
    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"


@pytest.mark.parametrize("suffix", ["/save", "/case", "", "/export"])
def test_other_users_session_is_hidden_for_every_write_endpoint(suffix):
    response = ordinary_client.request(
        "DELETE" if suffix == "" else "POST",
        f"/api/sessions/u2-session{suffix}",
    )
    assert response.status_code == 404
```

Also cover auto-save, unmark-case, import ownership, admin-only cleanup, and administrator success cases.

- [ ] **Step 2: Run route tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest backend/tests/api/test_session_catalog_routes.py -q
```

Expected: ordinary users can currently access the other session.

- [ ] **Step 3: Implement source adapters**

In `adapters.py`, define:

```python
class ConversationSourceAdapter(Protocol):
    async def summary(self, row: ConversationCatalogRecord) -> dict:
        raise NotImplementedError

    async def detail(self, row: ConversationCatalogRecord, **options) -> dict | None:
        raise NotImplementedError


class WebConversationAdapter:
    def __init__(self, manager):
        self.manager = manager

    async def summary(self, row):
        session = await self.manager.load_session(row.session_id, include_messages=False)
        if not session:
            return None
        return {
            **session.to_summary().model_dump(mode="json"),
            **row.model_dump(mode="json"),
        }

    async def detail(self, row, *, message_limit=100, lazy_artifacts=False):
        return await self.manager.load_session_with_pagination(
            row.session_id, message_limit, include_artifacts=not lazy_artifacts
        )


class KnowledgeQAConversationAdapter:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def summary(self, row):
        async with self.session_factory() as db:
            session = await db.get(ConversationSession, row.session_id)
            if not session:
                return None
            return {
                "session_id": session.id,
                "query": session.title,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "data_count": 0,
                "visual_count": 0,
                "has_error": False,
                "metadata": {},
                **row.model_dump(mode="json"),
            }
```

Add a registry mapping `ConversationSource.WEB` and `ConversationSource.KNOWLEDGE_QA` to adapters. Do not add the social adapter until phase 2.

- [ ] **Step 4: Authorize every session endpoint before source access**

Add these dependencies to each endpoint:

```python
user: CurrentUser = Depends(require_current_user)
catalog: ConversationCatalogService = Depends(get_conversation_catalog)
```

Use `await catalog.require_read(session_id, user)` for detail/messages/artifacts/restore. Use `await catalog.require_write(session_id, user)` for save/case/unmark/delete/auto-save/export. Perform the check before calling `session_manager`, repository, runtime cache, or file APIs.

Change list/stats/active to query catalog visibility first. List must preserve `source`, `owner_user_id`, `owner_username`, `owner_display_name`, and `read_only_on_web` in each returned row. Cleanup must reject non-admin users with `403 admin_required`. Import must register imported sessions to the current user after persistence and delete the imported session if registration fails.

- [ ] **Step 5: Run session route tests and regression tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/api/test_session_catalog_routes.py \
  backend/tests/test_session_manager_db.py \
  backend/tests/test_session_manager.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit authorized session dispatch**

```bash
git add backend/app/conversations/adapters.py backend/app/api/session_routes.py backend/tests/api/test_session_catalog_routes.py
git commit -m "feat: authorize unified session APIs"
```

### Task 6: Enforce Knowledge-QA Ownership and Register Sessions Atomically

**Files:**
- Modify: `backend/app/knowledge_base/conversation_store.py`
- Modify: `backend/app/routers/knowledge_qa.py`
- Modify: `backend/tests/api/test_authenticated_knowledge_routes.py`
- Create: `backend/tests/knowledge_base/test_conversation_ownership.py`

- [ ] **Step 1: Write failing store and route tests**

Add store tests proving that an existing session owned by `u1` cannot be resumed by `u2`, and route tests proving every history endpoint uses `CurrentUser`:

```python
@pytest.mark.asyncio
async def test_existing_knowledge_session_requires_same_owner(db_session):
    store = ConversationStore(db_session)
    await store._create_new_session(session_id="kqa-1", user_id="u1", first_query="q")

    with pytest.raises(ConversationAccessDenied):
        await store.get_or_create_session(session_id="kqa-1", user_id="u2")


def test_other_user_cannot_read_archive_or_delete_knowledge_history(client_u2):
    for method, path in (
        ("GET", "/api/knowledge-qa/history/kqa-u1"),
        ("GET", "/api/knowledge-qa/history/kqa-u1/recent"),
        ("POST", "/api/knowledge-qa/history/kqa-u1/archive"),
        ("DELETE", "/api/knowledge-qa/history/kqa-u1"),
    ):
        response = client_u2.request(method, path)
        assert response.status_code == 404
```

- [ ] **Step 2: Run knowledge tests and verify RED**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/knowledge_base/test_conversation_ownership.py \
  backend/tests/api/test_authenticated_knowledge_routes.py -q
```

Expected: an existing session is returned regardless of caller ownership and history endpoints lack user dependencies.

- [ ] **Step 3: Make store reuse owner-aware**

Define `ConversationAccessDenied` and reject mismatched owners before updating the session:

```python
class ConversationAccessDenied(RuntimeError):
    pass


if existing_session:
    if not user_id or existing_session.user_id != user_id:
        raise ConversationAccessDenied(session_id)
    existing_session.status = ConversationSessionStatus.ACTIVE
    existing_session.updated_at = datetime.utcnow()
```

Change `_create_new_session` to add a `ConversationCatalogDB` row to the same `self.db` transaction before the single commit. Pass authenticated username/display name into `get_or_create_session` and `_create_new_session`; do not accept those values from the HTTP body.

- [ ] **Step 4: Protect all knowledge history endpoints**

Add `user: CurrentUser = Depends(require_current_user)` and catalog dependency to history, recent, delete, archive, and list endpoints. Replace the optional `user_id` query parameter in list with `user.id`. Convert `ConversationAccessDenied` to `404 session_not_found`. Administrators may bypass the owner comparison only in management/history endpoints; ordinary streaming reuse remains owner-only.

Use this endpoint pattern:

```python
row = await catalog.require_read(session_id, user)
if row.source is not ConversationSource.KNOWLEDGE_QA:
    raise HTTPException(status_code=404, detail="session_not_found")
session = await conversation_store.get_session(session_id)
if not session:
    raise HTTPException(status_code=404, detail="session_not_found")
```

- [ ] **Step 5: Run knowledge and catalog tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/knowledge_base/test_conversation_ownership.py \
  backend/tests/api/test_authenticated_knowledge_routes.py \
  backend/tests/conversations -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit knowledge-QA isolation**

```bash
git add backend/app/knowledge_base/conversation_store.py backend/app/routers/knowledge_qa.py backend/tests/api/test_authenticated_knowledge_routes.py backend/tests/knowledge_base/test_conversation_ownership.py
git commit -m "feat: isolate knowledge conversation history"
```

### Task 7: Show Conversation Source and Administrator Ownership

**Files:**
- Modify: `frontend/src/components/management/SessionHistoryPanel.vue`
- Modify: `frontend/src/composables/reactAnalysis/useSessionManagement.js`
- Create: `frontend/src/components/management/sessionHistoryAccess.js`
- Create: `frontend/src/components/management/sessionHistoryAccess.test.js`

- [ ] **Step 1: Write failing frontend policy tests**

Create `sessionHistoryAccess.test.js`:

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'

import { historyRowLabels, preserveCatalogFields } from './sessionHistoryAccess.js'

test('catalog fields survive session history merges', () => {
  const merged = preserveCatalogFields(
    { session_id: 's1', source: 'knowledge_qa', owner_username: 'alice' },
    { session_id: 's1', query: 'hello' }
  )
  assert.equal(merged.source, 'knowledge_qa')
  assert.equal(merged.owner_username, 'alice')
})

test('administrator labels include source and owner', () => {
  assert.deepEqual(
    historyRowLabels({ source: 'web', owner_display_name: 'Alice', owner_username: 'alice' }, true),
    { source: 'Web', owner: 'Alice（alice）', readOnly: false }
  )
})
```

- [ ] **Step 2: Run frontend test and verify RED**

Run:

```bash
cd frontend && node --test src/components/management/sessionHistoryAccess.test.js
```

Expected: fails because the module does not exist.

- [ ] **Step 3: Implement pure presentation helpers**

Create `sessionHistoryAccess.js`:

```javascript
const SOURCE_LABELS = Object.freeze({
  web: 'Web',
  knowledge_qa: '知识库',
  social: '微信'
})

export function preserveCatalogFields(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming }
  for (const key of ['source', 'owner_user_id', 'owner_username', 'owner_display_name', 'read_only_on_web']) {
    if (incoming[key] == null && existing[key] != null) merged[key] = existing[key]
  }
  return merged
}

export function historyRowLabels(session, isAdmin) {
  const owner = isAdmin
    ? `${session.owner_display_name || session.owner_username || session.owner_user_id}（${session.owner_username || session.owner_user_id}）`
    : ''
  return {
    source: SOURCE_LABELS[session.source] || session.source || 'Web',
    owner,
    readOnly: session.read_only_on_web === true
  }
}
```

- [ ] **Step 4: Wire helpers into merge and panel rendering**

Replace direct spread merges in `useSessionManagement.js` with `preserveCatalogFields`. In `SessionHistoryPanel.vue`, render a source badge for every row and render the owner label only when a new Boolean `isAdmin` prop is true. Keep social read-only rendering dormant until phase 2 supplies social rows.

- [ ] **Step 5: Run frontend unit and auth suites**

Run:

```bash
cd frontend && node --test src/components/management/sessionHistoryAccess.test.js src/auth/*.test.mjs
```

Expected: all tests pass.

- [ ] **Step 6: Commit the history labels**

```bash
git add frontend/src/components/management/SessionHistoryPanel.vue frontend/src/composables/reactAnalysis/useSessionManagement.js frontend/src/components/management/sessionHistoryAccess.js frontend/src/components/management/sessionHistoryAccess.test.js
git commit -m "feat: label conversation source and owner"
```

### Task 8: Verify Phase 1 End to End

**Files:**
- Modify only if verification reveals a defect in files already listed above.

- [ ] **Step 1: Run focused backend suites**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/auth \
  backend/tests/conversations \
  backend/tests/api/test_agent_conversation_access.py \
  backend/tests/api/test_session_catalog_routes.py \
  backend/tests/api/test_authenticated_knowledge_routes.py \
  backend/tests/knowledge_base/test_conversation_ownership.py -q
```

Expected: all focused tests pass with no warnings caused by this feature.

- [ ] **Step 2: Run existing session regressions**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest \
  backend/tests/test_session_manager.py \
  backend/tests/test_session_manager_db.py \
  backend/tests/auth/test_auth_middleware.py \
  backend/tests/integration/test_gateway_auth_flow.py -q
```

Expected: all regression tests pass.

- [ ] **Step 3: Run frontend tests and build**

```bash
cd frontend && npm run test:auth && node --test src/components/management/sessionHistoryAccess.test.js && npm run build
```

Expected: tests pass and Vite build completes successfully.

- [ ] **Step 4: Perform migration dry verification against a disposable database**

Apply `006_create_conversation_catalog.sql` twice to a disposable PostgreSQL database populated with one Web session, one owned knowledge session, and one unowned knowledge session. Query:

```sql
SELECT source, owner_user_id, COUNT(*)
FROM conversation_catalog
GROUP BY source, owner_user_id
ORDER BY source, owner_user_id;
```

Expected: one Web/admin row, one retained knowledge owner row, one knowledge/admin row, and no duplicates after the second migration.

- [ ] **Step 5: Review changed endpoints for pre-access source reads**

Run:

```bash
rg -n "get_session\(|load_session\(|get_session_with_messages\(|delete_session\(" backend/app/api/session_routes.py backend/app/routers/agent.py backend/app/routers/knowledge_qa.py
```

Expected: every user-controlled `session_id` source read is preceded in the same endpoint by `require_read` or `require_write`.

- [ ] **Step 6: Commit any verification-only corrections**

If verification required changes:

```bash
git add backend/app backend/tests frontend/src
git commit -m "fix: close conversation ownership regressions"
```

If no files changed, do not create an empty commit.
