# Unified Resource Preview Hard Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `session_resources` the only source for tool-produced files, live previews, downloads, charts, boards, and new-session restoration, with a new file-products tab and no legacy preview or path-based access mechanism.

**Architecture:** Tools publish explicit resource groups whose primary, preview, rendition, source, and attachment members are persisted before a `resources_changed` event is emitted. The backend exposes only session-scoped catalog and opaque content URLs; a dedicated Pinia resource store drives file, document, chart, and board views through a renderer registry. This is a destructive hard cut for newly created conversations: no history migration, compatibility reads, or backup path is retained.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async/PostgreSQL, pytest; Vue 3, Pinia, Vite, Node test runner; SSE; Nginx.

---

## File and responsibility map

### Backend resource domain

- `backend/app/agent/resources/contracts.py`: strict producer declaration contract and enums.
- `backend/app/agent/resources/resource_service.py`: resource group publication, derivative attachment, catalog versions, in-memory behavior.
- `backend/app/db/models_session.py`: authoritative SQLAlchemy resource row/version models.
- `backend/app/db/session_resources_repository.py`: transactional PostgreSQL implementation.
- `backend/app/db/migrations/014_hard_cutover_resource_delivery.sql`: destructive schema replacement and legacy-column removal.
- `backend/app/db/database.py`: startup schema parity for clean databases; never silently recreates legacy columns.
- `backend/app/tools/resource_declarations.py`: shared builders for primary resources and related members.

### Backend delivery and runtime

- `backend/app/api/session_resource_routes.py`: catalog, content, directory-asset endpoints, and safe action-link serialization.
- `backend/app/agent/resources/actions.py`: converts trusted capabilities to domain action links; producer metadata cannot inject URLs.
- `backend/app/api/session_routes.py`: session restore metadata only; no message artifact extraction.
- `backend/app/core/routing.py`: registers the focused resource router.
- `backend/app/agent/resources/runtime.py`: persists each successful tool result before emitting change events.
- `backend/app/agent/react_agent.py`: inserts committed `resources_changed` events into the stream.
- `backend/app/routers/agent.py`, `backend/app/social/agent_bridge.py`: forward resource events without synthesizing previews.
- Artifact-producing tool modules listed in Tasks 5–7: explicit declarations only.

### Frontend resource domain and UI

- `frontend/src/api/sessionResources.js`: catalog, content URL, download, and action client.
- `frontend/src/stores/sessionResourceStore.js`: sole per-session resource state and version synchronization.
- `frontend/src/services/resourceGroups.js`: pure grouping, filtering, preview choice, and target-tab selectors.
- `frontend/src/services/resourceRendererRegistry.js`: renderer name to component mapping.
- `frontend/src/components/resources/ResourceProductsPanel.vue`: top-level tool file products.
- `frontend/src/components/resources/ResourcePreviewHost.vue`: common preview loading/error boundary.
- `frontend/src/components/resources/renderers/*.vue`: format-specific renderers with no session querying.
- `frontend/src/components/reactAnalysis/RightPanelContainer.vue`: file/document/chart/board resource tabs.
- `frontend/src/composables/reactAnalysis/useSessionManagement.js`: parallel message/catalog restoration.
- `frontend/src/composables/reactAnalysis/usePanelManagement.js`: resource-derived visibility and selection.
- `frontend/src/stores/reactStore.js`: conversation state only; removes artifact history and preview-event branches.

### Files removed after replacement

- `frontend/src/services/officeDocumentRecovery.js`
- `frontend/src/services/officeDocumentRecovery.test.js`
- `frontend/src/services/sessionDocumentResources.js`
- `frontend/src/services/sessionDocumentResources.test.js`
- `frontend/src/composables/reactAnalysis/useOfficeDocumentHandler.js`
- `frontend/src/composables/reactAnalysis/useRightPanelState.js`
- `frontend/src/composables/reactAnalysis/panelTabPolicy.js`
- `frontend/src/composables/reactAnalysis/panelTabPolicy.test.js`
- `frontend/src/components/OfficeDocumentPanel.vue`
- Legacy resource projection files and tests under `backend/app/agent/resources/manifest.py`, `manifest_test.py`, `models.py`, `models_test.py`, and `service_test.py` after import scans prove no current consumer.

---

### Task 1: Replace the database and declaration contract with grouped resources

**Files:**
- Create: `backend/app/db/migrations/014_hard_cutover_resource_delivery.sql`
- Modify: `backend/app/agent/resources/contracts.py`
- Modify: `backend/app/db/models_session.py`
- Modify: `backend/app/db/database.py`
- Test: `backend/tests/agent/resources/test_contracts.py`
- Test: `backend/tests/db/test_session_resources_schema.py`

- [ ] **Step 1: Write failing contract tests for groups, relations, renderers, and server-only locators**

Add tests that validate one primary plus related resources and reject an unbound derivative:

```python
from app.agent.resources.contracts import ResourceDeclaration, ResourceRelation


def test_grouped_preview_declaration_is_explicit():
    primary = ResourceDeclaration.model_validate({
        "kind": "file", "group_key": "report:air-quality",
        "resource_key": "docx", "relation": "primary", "role": "report",
        "label": "空气质量报告.docx", "locator": {"path": "/tmp/report.docx"},
        "format": "docx", "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "renderer": "file", "capabilities": ["download", "edit", "preview"],
    })
    preview = ResourceDeclaration.model_validate({
        "kind": "file", "group_key": "report:air-quality",
        "resource_key": "html-preview", "parent_key": "docx",
        "relation": "preview", "role": "report", "label": "HTML预览",
        "locator": {"path": "/tmp/report.html"}, "format": "html",
        "media_type": "text/html", "renderer": "html", "capabilities": ["preview"],
    })
    assert primary.relation is ResourceRelation.PRIMARY
    assert preview.parent_key == primary.resource_key


def test_derivative_requires_parent_key():
    with pytest.raises(ValueError, match="parent_key"):
        ResourceDeclaration.model_validate({
            "kind": "file", "group_key": "report:x", "resource_key": "pdf",
            "relation": "preview", "role": "report", "label": "PDF",
            "locator": {"path": "/tmp/x.pdf"}, "format": "pdf",
            "media_type": "application/pdf", "renderer": "pdf",
        })
```

- [ ] **Step 2: Run the contract tests and confirm they fail**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/agent/resources/test_contracts.py
```

Expected: FAIL because `group_key`, `resource_key`, `relation`, `renderer`, `capabilities`, and `parent_key` are not defined.

- [ ] **Step 3: Implement the strict declaration types**

Replace presentation-specific declarations with these concepts:

```python
class ResourceRelation(str, Enum):
    PRIMARY = "primary"
    PREVIEW = "preview"
    RENDITION = "rendition"
    SOURCE = "source"
    ATTACHMENT = "attachment"


class ResourceRenderer(str, Enum):
    FILE = "file"
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    IMAGE = "image"
    CHART = "chart"
    BOARD = "board"


class ResourceCapability(str, Enum):
    PREVIEW = "preview"
    DOWNLOAD = "download"
    EDIT = "edit"
    RENDER = "render"
    SHARE = "share"


class ResourceDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ResourceKind
    group_key: str = Field(min_length=1, max_length=255)
    resource_key: str = Field(min_length=1, max_length=255)
    parent_key: str | None = Field(default=None, max_length=255)
    relation: ResourceRelation = ResourceRelation.PRIMARY
    role: ResourceRole = ResourceRole.OUTPUT
    label: str = Field(min_length=1, max_length=512)
    locator: ResourceLocator
    format: str = Field(min_length=1, max_length=64)
    media_type: str = Field(min_length=1, max_length=255)
    renderer: ResourceRenderer = ResourceRenderer.FILE
    capabilities: set[ResourceCapability] = Field(default_factory=set)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: ResourceStatus = ResourceStatus.ACTIVE
    tool_name: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def validate_relation(self):
        if self.relation is ResourceRelation.PRIMARY and self.parent_key:
            raise ValueError("primary resource cannot have parent_key")
        if self.relation is not ResourceRelation.PRIMARY and not self.parent_key:
            raise ValueError("non-primary resource requires parent_key")
        return self
```

Remove `PresentationType`, `DocumentPresentation`, `VisualizationPresentation`, and preview-type inference from the durable contract.

- [ ] **Step 4: Write the destructive schema test and migration**

Test that migration 014 contains a fresh grouped table and removes legacy structures:

```python
def test_hard_cutover_migration_has_grouped_resource_schema():
    sql = Path("backend/app/db/migrations/014_hard_cutover_resource_delivery.sql").read_text()
    normalized = " ".join(sql.upper().split())
    for column in ("GROUP_ID", "PARENT_RESOURCE_ID", "RELATION", "FORMAT", "MEDIA_TYPE", "RENDERER", "CAPABILITIES", "VERSION"):
        assert column in normalized
    assert "DROP TABLE IF EXISTS SESSION_RESOURCE_MANIFESTS" in normalized
    assert "DROP COLUMN IF EXISTS DATA_IDS" in normalized
    assert "DROP COLUMN IF EXISTS VISUAL_IDS" in normalized
    assert "DROP COLUMN IF EXISTS OFFICE_DOCUMENTS" in normalized
```

Migration 014 must deliberately discard old resource state:

```sql
BEGIN;
DROP TABLE IF EXISTS session_resource_manifests;
DROP TABLE IF EXISTS session_resources;
DROP TABLE IF EXISTS session_resource_versions;

CREATE TABLE session_resource_versions (
    session_id VARCHAR(255) PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_resources (
    resource_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    group_id VARCHAR(64) NOT NULL,
    parent_resource_id VARCHAR(64) REFERENCES session_resources(resource_id) ON DELETE CASCADE,
    resource_key VARCHAR(255) NOT NULL,
    relation VARCHAR(32) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    role VARCHAR(32) NOT NULL,
    label VARCHAR(512) NOT NULL,
    locator JSONB NOT NULL,
    format VARCHAR(64) NOT NULL,
    media_type VARCHAR(255) NOT NULL,
    renderer VARCHAR(64) NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_name VARCHAR(255) NOT NULL DEFAULT '',
    run_id VARCHAR(255) NOT NULL,
    turn_sequence INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, group_id, version, resource_key)
);

CREATE INDEX ix_session_resources_catalog
    ON session_resources(session_id, status, updated_at DESC);
CREATE INDEX ix_session_resources_group
    ON session_resources(session_id, group_id, version);

ALTER TABLE IF EXISTS sessions
    DROP COLUMN IF EXISTS data_ids,
    DROP COLUMN IF EXISTS visual_ids,
    DROP COLUMN IF EXISTS office_documents;
COMMIT;
```

- [ ] **Step 5: Align SQLAlchemy and startup schema, then run tests**

Update `SessionResourceDB` to the exact migration columns and constraints. Update `_ensure_session_resources_schema()` to create this schema only when absent; do not put destructive drops in startup code.

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/agent/resources/test_contracts.py backend/tests/db/test_session_resources_schema.py
```

Expected: PASS.

- [ ] **Step 6: Commit the contract and schema**

```bash
git add backend/app/agent/resources/contracts.py backend/app/db/models_session.py backend/app/db/database.py backend/app/db/migrations/014_hard_cutover_resource_delivery.sql backend/tests/agent/resources/test_contracts.py backend/tests/db/test_session_resources_schema.py
git commit -m "refactor: define grouped session resource contract"
```

### Task 2: Implement transactional group publication and derivative attachment

**Files:**
- Modify: `backend/app/agent/resources/resource_service.py`
- Modify: `backend/app/db/session_resources_repository.py`
- Test: `backend/tests/agent/resources/test_resource_service.py`
- Create: `backend/tests/db/test_session_resource_group_repository.py`

- [ ] **Step 1: Write failing service tests for versions and relations**

Use declarations from Task 1 and assert:

```python
@pytest.mark.asyncio
async def test_publish_group_keeps_versions_and_binds_children():
    service = SessionResourceService.in_memory()
    first = await service.publish_group("s1", "run-1", "report:air", [docx("v1"), pdf_preview("v1")])
    second = await service.publish_group("s1", "run-2", "report:air", [docx("v2"), pdf_preview("v2")])
    assert first.catalog_version == 1
    assert second.catalog_version == 2
    assert second.group_version == 2
    current = await service.list_resources("s1", status="active")
    history = await service.list_resources("s1", status=None)
    assert {r.version for r in current.resources} == {2}
    assert {r.version for r in history.resources} == {1, 2}
    preview = next(r for r in current.resources if r.relation == "preview")
    primary = next(r for r in current.resources if r.relation == "primary")
    assert preview.parent_resource_id == primary.resource_id


@pytest.mark.asyncio
async def test_attach_derivatives_uses_parent_version():
    service = SessionResourceService.in_memory()
    published = await service.publish_group("s1", "run-1", "report:air", [docx("v1")])
    primary = published.resources[0]
    attached = await service.attach_resources("s1", "render-1", primary.resource_id, [pdf_preview("v1")])
    assert attached.resources[0].group_id == primary.group_id
    assert attached.resources[0].version == primary.version
```

- [ ] **Step 2: Run tests and confirm the old upsert model fails**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/agent/resources/test_resource_service.py
```

Expected: FAIL because `publish_group`, `attach_resources`, `group_id`, relation binding, and retained versions do not exist.

- [ ] **Step 3: Implement immutable stored resources and batch results**

Define `StoredResource` with the migration fields and expose:

```python
@dataclass(frozen=True)
class ResourcePublishResult:
    catalog_version: int
    group_version: int
    resources: list[StoredResource]


class SessionResourceService:
    async def publish_group(self, session_id, run_id, group_key, resources, *, turn_sequence=0):
        declarations = list(resources)
        if self._repository is not None:
            return await self._repository.publish_group(
                session_id, run_id, group_key, declarations, turn_sequence=turn_sequence
            )
        return self._publish_memory_group(
            session_id, run_id, group_key, declarations, turn_sequence=turn_sequence
        )

    async def attach_resources(self, session_id, run_id, parent_resource_id, resources, *, turn_sequence=0):
        declarations = list(resources)
        if self._repository is not None:
            return await self._repository.attach_resources(
                session_id, run_id, parent_resource_id, declarations,
                turn_sequence=turn_sequence,
            )
        return self._attach_memory_resources(
            session_id, run_id, parent_resource_id, declarations,
            turn_sequence=turn_sequence,
        )

    async def list_resources(self, session_id, *, kind=None, role=None, renderer=None,
                             group_id=None, status="active", limit=100, cursor=None):
        return await self._catalog_backend().list_resources(
            session_id, kind=kind, role=role, renderer=renderer,
            group_id=group_id, status=status, limit=limit, cursor=cursor,
        )

    async def resource_counts(self, session_id):
        return await self._catalog_backend().resource_counts(session_id)

    async def catalog_version(self, session_id):
        return await self._catalog_backend().catalog_version(session_id)

    async def get_resource(self, session_id, resource_id, *, status="active"):
        return await self._catalog_backend().get_resource(
            session_id, resource_id, status=status
        )
```

For the in-memory implementation, `_catalog_backend()` returns a small adapter over `_MemoryState`; for database mode it returns the repository. `_publish_memory_group()` and `_attach_memory_resources()` implement the same validation and version transitions asserted by the tests rather than delegating to SQL-specific code.

Compute stable IDs as follows:

```python
group_id = sha256(f"{session_id}:{group_key}".encode()).hexdigest()[:32]
resource_id = sha256(
    f"{session_id}:{group_id}:{group_version}:{declaration.resource_key}".encode()
).hexdigest()[:32]
```

Publishing a group increments that group's version, marks its former active members `superseded`, resolves `parent_key` against the new batch, and increments the session catalog version once. Attaching derivatives requires an active parent and increments only the catalog version.

- [ ] **Step 4: Implement repository transactions and locking**

In `SessionResourcesRepository`, lock `session_resource_versions` and the current primary group rows with `FOR UPDATE`. Perform status updates and inserts inside one `AsyncSession.begin()` block. Reject duplicate resource keys, missing parents, mismatched group keys, and derivatives whose declared parent is not in the same publication batch.

The repository test must run against its fake/transaction boundary and assert that a failed child insert leaves the old active group unchanged.

- [ ] **Step 5: Run service and repository tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/agent/resources/test_resource_service.py backend/tests/db/test_session_resource_group_repository.py
```

Expected: PASS.

- [ ] **Step 6: Commit the persistence implementation**

```bash
git add backend/app/agent/resources/resource_service.py backend/app/db/session_resources_repository.py backend/tests/agent/resources/test_resource_service.py backend/tests/db/test_session_resource_group_repository.py
git commit -m "feat: publish versioned session resource groups"
```

### Task 3: Add secure catalog and opaque content delivery

**Files:**
- Create: `backend/app/api/session_resource_routes.py`
- Create: `backend/app/agent/resources/actions.py`
- Modify: `backend/app/api/session_routes.py`
- Modify: `backend/app/core/routing.py`
- Create: `backend/tests/api/test_session_resource_catalog.py`
- Create: `backend/tests/api/test_session_resource_content.py`
- Modify: `backend/tests/api/test_upload_resource_ref_contract.py`

- [ ] **Step 1: Write failing catalog DTO tests**

Assert the response contains group and renderer fields but never physical locators:

```python
resource = response.json()["resources"][0]
assert resource["resource_id"]
assert resource["group_id"]
assert resource["relation"] == "primary"
assert resource["renderer"] == "pdf"
assert resource["content_url"].endswith(f"/{resource['resource_id']}/content")
assert "locator" not in resource
assert "file_path" not in resource
assert "/tmp/" not in response.text
```

Also assert filters are `renderer`, `role`, `kind`, `group_id`, `status`, and cursor; remove `presentation_type`.

- [ ] **Step 2: Write failing content and directory-asset security tests**

Cover:

```python
assert inline.headers["content-disposition"].startswith("inline;")
assert download.headers["content-disposition"].startswith("attachment;")
assert download.headers["x-content-type-options"] == "nosniff"
assert traversal.status_code == 403                 # asset_path=../../secret
assert symlink_escape.status_code == 403
assert wrong_session.status_code == 404
assert unauthorized.status_code == 404
assert missing.status_code == 404
```

Directory artifact entrypoints use `/content/` with a trailing slash so relative HTML assets resolve beneath `/content/{asset_path}`.

- [ ] **Step 3: Run API tests and verify failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/api/test_session_resource_catalog.py backend/tests/api/test_session_resource_content.py
```

Expected: FAIL because the current route exposes `locator`, accepts `presentation_type`, and only serves direct files.

- [ ] **Step 4: Implement the focused resource router**

Move resource endpoints out of `session_routes.py`. Build DTOs with a single serializer:

```python
def resource_dto(session_id: str, item: StoredResource) -> dict:
    base = f"/api/sessions/{quote(session_id, safe='')}/resources/{item.resource_id}"
    directory = item.kind == "artifact" and bool(item.metadata.get("entrypoint"))
    return {
        "resource_id": item.resource_id,
        "ref_id": item.resource_id,
        "group_id": item.group_id,
        "parent_resource_id": item.parent_resource_id,
        "resource_key": item.resource_key,
        "relation": item.relation,
        "kind": item.kind,
        "role": item.role,
        "label": item.label,
        "format": item.format,
        "media_type": item.media_type,
        "renderer": item.renderer,
        "capabilities": item.capabilities,
        "actions": resource_action_links(session_id, item),
        "version": item.version,
        "status": item.status,
        "content_url": f"{base}/content/" if directory else f"{base}/content",
        "download_url": f"{base}/content?disposition=attachment" if "download" in item.capabilities else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
```

Resolve file paths only after `catalog.require_read()`. For directory artifacts, combine `locator.path`, `metadata.entrypoint`, and optional `asset_path`, call `resolve()`, require `candidate.is_relative_to(root)`, reject any symlink component that resolves outside root, and serve with CSP for HTML.

Implement `resource_action_links()` as a trusted resolver keyed by capability and resource format. It may return existing authenticated Office/report/board/share command URLs, but it must never copy a URL from tool metadata. Tests assert unsupported capability/format pairs produce no link.

- [ ] **Step 5: Register the router and remove the old route definitions**

Add `RouterSpec("app.api.session_resource_routes", description="Session resource delivery", owner="core")` immediately after session management. Remove resource endpoint functions and locator serialization from `session_routes.py`.

- [ ] **Step 6: Run focused API tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/api/test_session_resource_catalog.py backend/tests/api/test_session_resource_content.py backend/tests/api/test_upload_resource_ref_contract.py
```

Expected: PASS.

- [ ] **Step 7: Commit the resource delivery API**

```bash
git add backend/app/api/session_resource_routes.py backend/app/agent/resources/actions.py backend/app/api/session_routes.py backend/app/core/routing.py backend/tests/api/test_session_resource_catalog.py backend/tests/api/test_session_resource_content.py backend/tests/api/test_upload_resource_ref_contract.py
git commit -m "feat: serve session resources through opaque content URLs"
```

### Task 4: Persist every tool result before emitting resource changes

**Files:**
- Modify: `backend/app/agent/resources/runtime.py`
- Modify: `backend/app/agent/react_agent.py`
- Modify: `backend/app/routers/agent.py`
- Modify: `backend/app/social/agent_bridge.py`
- Test: `backend/app/agent/resources/runtime_test.py`
- Create: `backend/tests/agent/test_resource_change_stream.py`

- [ ] **Step 1: Write failing ordering and event tests**

Test that persistence finishes before the stream sees a change event:

```python
@pytest.mark.asyncio
async def test_tool_resources_are_committed_before_change_event():
    order = []
    service = RecordingService(order)
    events = [tool_result_event(resources=[primary_file()]), complete_event()]
    emitted = [event async for event in stream_with_resources(events, service=service)]
    order.extend(event["type"] for event in emitted)
    assert order.index("commit") < order.index("resources_changed")
    changed = next(e for e in emitted if e["type"] == "resources_changed")
    assert changed["data"]["resource_version"] == 1
    assert changed["data"]["changed_resource_ids"]


@pytest.mark.asyncio
async def test_failed_persistence_does_not_emit_change_event():
    emitted = [e async for e in stream_with_resources([tool_result_event()], service=FailingService())]
    assert not any(e["type"] == "resources_changed" for e in emitted)
    assert any(e["type"] == "resource_error" for e in emitted)
```

- [ ] **Step 2: Run tests and confirm terminal-only flush fails them**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/app/agent/resources/runtime_test.py backend/tests/agent/test_resource_change_stream.py
```

Expected: FAIL because resources are currently accumulated until a terminal event.

- [ ] **Step 3: Replace terminal accumulation with per-result publication**

Make `RunResourceAccumulator.capture()` return newly validated declarations grouped by `group_key`. Add:

```python
async def persist_tool_result_resources(service, session_id, run_id, event, *, turn_sequence):
    declarations, rejected = normalize_tool_resources(result=_successful_result(event))
    published = []
    for group_key, members in groupby_group_key(declarations).items():
        published.append(await service.publish_group(
            session_id, run_id, group_key, members, turn_sequence=turn_sequence
        ))
    return ResourceEventResult.from_published(published, rejected=rejected)
```

In `react_agent.py`, call it after ownership validation and before yielding the `tool_result`. Yield exactly one `resources_changed` event with the highest catalog version and all changed IDs. On failure, yield `resource_error` and mark terminal resource durability false; do not re-upsert at completion or in `finally`.

- [ ] **Step 4: Make transport layers pass resource events unchanged**

Remove preview injection in `routers/agent.py` and `social/agent_bridge.py`. Preserve `resources_changed` and `resource_error` types and their `session_id`, `run_id`, version, and IDs.

- [ ] **Step 5: Run runtime and stream tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/app/agent/resources/runtime_test.py backend/tests/agent/test_resource_change_stream.py backend/tests/test_social_multimodal.py
```

Expected: PASS.

- [ ] **Step 6: Commit durable live notifications**

```bash
git add backend/app/agent/resources/runtime.py backend/app/agent/react_agent.py backend/app/routers/agent.py backend/app/social/agent_bridge.py backend/app/agent/resources/runtime_test.py backend/tests/agent/test_resource_change_stream.py
git commit -m "feat: publish resources before live preview notifications"
```

### Task 5: Replace file producer helpers and convert generic output tools

**Files:**
- Modify: `backend/app/tools/resource_declarations.py`
- Modify: `backend/app/api/upload_routes.py`
- Modify: `backend/app/tools/utility/bash_tool.py`
- Modify: `backend/app/tools/utility/execute_python_tool.py`
- Modify: `backend/app/tools/utility/edit_file_tool_v2.py`
- Modify: `backend/app/tools/utility/write_file_tool.py`
- Modify: `backend/app/tools/utility/read_file_tool.py`
- Modify: `backend/app/tools/social/cli_session/tool.py`
- Modify: `backend/app/tools/social/terminal_session/tool.py`
- Modify: `backend/app/tools/browser/actions/file_ops.py`
- Modify: `backend/app/tools/browser/actions/pdf.py`
- Modify: `backend/app/tools/browser/actions/screenshot.py`
- Modify: `backend/app/tools/browser/actions/trace.py`
- Modify: `backend/app/tools/external_data/gfs_downloader/tool.py`
- Modify: `backend/app/tools/external_data/gfs_processor/tool.py`
- Modify: `backend/app/tools/query/get_platform_weather_image/tool.py`
- Modify: `backend/app/tools/query/local_satellite_image_tool.py`
- Modify: `backend/app/tools/query/qianlima_realtime_tender/tool.py`
- Modify: `backend/app/tools/utility/parse_pdf_tool.py`
- Modify: `backend/app/tools/utility/skill_management/create_skill_draft_tool.py`
- Modify: `backend/app/tools/utility/vectorize_document_tool.py`
- Modify: `backend/app/tools/workflow/workflow_tool.py`
- Create: `backend/tests/tools/test_explicit_file_resource_producers.py`

- [ ] **Step 1: Write failing builder and producer contract tests**

Assert a builder produces one group with explicit members:

```python
members = file_product(
    primary_path=tmp_path / "report.docx",
    group_key="report:air",
    tool_name="write_file",
    previews=[preview_file(tmp_path / "report.pdf", renderer="pdf")],
)
assert [m["relation"] for m in members] == ["primary", "preview"]
assert members[1]["parent_key"] == members[0]["resource_key"]
assert all(m["group_key"] == "report:air" for m in members)
```

For each generic producer, invoke its existing result-normalization seam and assert every returned output file has a matching explicit resource declaration with no preview/path inference required.

- [ ] **Step 2: Run producer tests and confirm failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_explicit_file_resource_producers.py
```

Expected: FAIL because existing builders emit the old flat/presentation contract.

- [ ] **Step 3: Implement grouped shared builders**

Provide focused builders named `primary_file`, `derivative_file`, `directory_artifact`, `chart_resource`, `board_resource`, and `file_product`. The primary builder must have this complete shape; the other builders use the same keys and add only the relation-specific parent or entrypoint fields:

```python
def primary_file(path, *, group_key, tool_name, role="output", renderer="file",
                 capabilities=("download",)) -> dict:
    resolved = Path(path).expanduser().resolve()
    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return {
        "kind": "file",
        "group_key": group_key,
        "resource_key": f"primary:{resolved.suffix.lower().lstrip('.') or 'file'}",
        "relation": "primary",
        "role": role,
        "label": resolved.name,
        "locator": {"path": str(resolved)},
        "format": resolved.suffix.lower().lstrip(".") or "file",
        "media_type": media_type,
        "renderer": renderer,
        "capabilities": list(capabilities),
        "metadata": {"size": resolved.stat().st_size} if resolved.is_file() else {},
        "tool_name": tool_name,
    }
```

Builders set `format`, `media_type`, `renderer`, capabilities, deterministic member keys, and directory `metadata.entrypoint`. They never put download URLs or local paths in metadata.

- [ ] **Step 4: Convert uploads and generic producers**

Replace calls to old `file_resource/resources_for_files` with the grouped helpers. User uploads use `role=attachment`, `relation=primary`, `group_key=f"upload:{file_id}"`; they remain selectable context but do not appear in the file-products tab.

Generic command tools must declare only files created or materially modified by that invocation, not every path mentioned in stdout.

- [ ] **Step 5: Run producer and upload tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_explicit_file_resource_producers.py backend/tests/api/test_upload_resource_ref_contract.py backend/app/tools/utility
```

Expected: PASS.

- [ ] **Step 6: Commit generic producer conversion**

```bash
git add backend/app/tools/resource_declarations.py backend/app/api/upload_routes.py backend/app/tools/utility backend/app/tools/social/cli_session backend/app/tools/social/terminal_session backend/app/tools/browser/actions backend/tests/tools/test_explicit_file_resource_producers.py backend/tests/api/test_upload_resource_ref_contract.py
git commit -m "refactor: declare generic tool file products explicitly"
```

### Task 6: Convert Office, report, and HTML artifact producers and actions

**Files:**
- Modify: `backend/app/tools/utility/publish_session_file_tool.py`
- Modify: `backend/app/tools/report/report_package/tool.py`
- Modify: `backend/app/tools/report/read_docx/tool.py`
- Modify: `backend/app/tools/html_artifact/tool.py`
- Modify: `backend/app/tools/office/ppt_master_tool.py`
- Modify: `backend/app/tools/office/read_pptx_tool.py`
- Modify: `backend/app/tools/office/editable_ppt/tool.py`
- Modify: `backend/app/tools/office/validate_pptx_tool.py`
- Modify: `backend/app/services/report_preview_refresh.py`
- Modify: `backend/app/services/html_artifact_service.py`
- Modify: `backend/app/api/office_routes.py`
- Modify: `backend/app/api/report_routes.py`
- Modify: `backend/app/api/html_artifact_routes.py`
- Create: `backend/tests/tools/test_rich_artifact_resource_groups.py`
- Create: `backend/tests/api/test_resource_actions_refresh_catalog.py`

- [ ] **Step 1: Write failing rich artifact group tests**

For DOCX, report, HTML artifact, spreadsheet, and PPT assert exact group shapes. Example PPT expectations:

```python
assert member(resources, "pptx").relation == "primary"
assert member(resources, "pdf").relation == "preview"
assert member(resources, "montage").relation == "preview"
assert all(page.relation == "attachment" for page in page_members(resources))
assert all(r.parent_key == "pptx" for r in resources if r.resource_key != "pptx")
```

Action tests must assert render/edit success calls `attach_resources()` or `publish_group()` and returns only `{success, resource_version, changed_resource_ids}` rather than a preview URL.

- [ ] **Step 2: Run tests and confirm failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_rich_artifact_resource_groups.py backend/tests/api/test_resource_actions_refresh_catalog.py
```

Expected: FAIL against legacy `pdf_preview`, `html_preview`, download URL, and related-files payloads.

- [ ] **Step 3: Convert rich producers to resource groups**

Use these stable group keys:

```text
report:{report_id}
html-artifact:{artifact_id}
office:{document_id or normalized logical name}
presentation:{project_id or normalized logical name}
```

Represent HTML artifact roots as directory resources with `metadata.entrypoint="index.html"`. Represent report QMD as source, DOCX as primary/rendition according to the tool's actual deliverable, HTML as preview, and charts/assets as attachments. Do not embed `pdf_url`, `html_url`, `download_url`, `related_files`, or filesystem paths in public metadata.

- [ ] **Step 4: Make edit/render actions update the catalog**

Office edits that create a new deliverable call `publish_group()` to create a new group version. Preview/render operations call `attach_resources()` against the active primary. Report and HTML sharing routes remain domain-specific public-share flows, but authenticated preview/download routes stop being front-end dependencies.

- [ ] **Step 5: Run rich producer, action, and existing domain tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_rich_artifact_resource_groups.py backend/tests/api/test_resource_actions_refresh_catalog.py backend/app/tools/office backend/app/tools/report backend/app/services/quarto_report_renderer_source_qmd_test.py
```

Expected: PASS.

- [ ] **Step 6: Commit rich artifact conversion**

```bash
git add backend/app/tools/utility/publish_session_file_tool.py backend/app/tools/report backend/app/tools/html_artifact backend/app/tools/office backend/app/services/report_preview_refresh.py backend/app/services/html_artifact_service.py backend/app/api/office_routes.py backend/app/api/report_routes.py backend/app/api/html_artifact_routes.py backend/tests/tools/test_rich_artifact_resource_groups.py backend/tests/api/test_resource_actions_refresh_catalog.py
git commit -m "refactor: publish office and report previews as resources"
```

### Task 7: Convert charts, images, maps, and boards to resource content

**Files:**
- Modify: `backend/app/tools/visualization/create_report_chart/tool.py`
- Modify: `backend/app/tools/visualization/chart_image_renderer/tool.py`
- Modify: `backend/app/tools/visualization/generate_map/tool.py`
- Modify: `backend/app/tools/visualization/create_drawio_board/tool.py`
- Modify: `backend/app/tools/visualization/create_drawio_board/render_tool.py`
- Modify: `backend/app/tools/visualization/create_drawio_board/accept_tool.py`
- Modify: `backend/app/boards/application.py`
- Modify: `backend/app/boards/service.py`
- Modify: `backend/app/boards/routes.py`
- Modify: analysis tools currently calling `resources_for_visuals` under `backend/app/tools/analysis/`
- Create: `backend/tests/tools/test_visual_and_board_resource_groups.py`
- Create: `backend/tests/api/test_visual_and_board_resource_content.py`

- [ ] **Step 1: Write failing visual and board resource tests**

```python
chart = member(resources, "chart-spec")
assert chart.kind == "visual"
assert chart.renderer == "chart"
assert chart.media_type == "application/json"

board = member(resources, "board-xml")
assert board.renderer == "board"
assert board.media_type in {"application/xml", "text/xml"}
assert screenshot.parent_key == board.resource_key
assert screenshot.relation == "preview"
```

API tests fetch chart JSON and board XML through the same content endpoint used for files.

- [ ] **Step 2: Run tests and confirm failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_visual_and_board_resource_groups.py backend/tests/api/test_visual_and_board_resource_content.py
```

Expected: FAIL because visuals and boards are currently reconstructed from special payloads/services.

- [ ] **Step 3: Publish chart and image groups**

Store chart specs as registry-backed JSON resources; charts with exported PNG/SVG add rendition members. Convert every current `resources_for_visuals()` caller to the explicit chart/image builder and stable group key based on the visual logical identity.

- [ ] **Step 4: Publish board snapshots and previews**

Accepted and candidate board versions write XML/JSON primary resources plus screenshot preview resources. Board mutation/version routes remain commands, but their successful result publishes a resource version and emits a resource change. Remove read-side dependence on `/drawio-board` for new-session preview restoration.

- [ ] **Step 5: Run visual, board, and analysis tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_visual_and_board_resource_groups.py backend/tests/api/test_visual_and_board_resource_content.py backend/app/tools/visualization backend/tests/test_board_mode_split.py
```

Expected: PASS.

- [ ] **Step 6: Commit visual and board conversion**

```bash
git add backend/app/tools/visualization backend/app/tools/analysis backend/app/boards backend/tests/tools/test_visual_and_board_resource_groups.py backend/tests/api/test_visual_and_board_resource_content.py backend/tests/test_board_mode_split.py
git commit -m "refactor: deliver charts and boards through session resources"
```

### Task 8: Remove backend resource inference and legacy read mechanisms

**Files:**
- Modify: `backend/app/api/session_routes.py`
- Modify: `backend/app/conversations/adapters.py`
- Modify: `backend/app/agent/session/conversation_persistence.py`
- Modify: `backend/app/scheduled_tasks/conversation_persistence.py`
- Modify: `backend/app/db/session_repository.py`
- Modify: `backend/app/agent/selection_context.py`
- Modify: `backend/app/agent/active_contexts.py`
- Modify: `backend/app/agent/chat_composer_selection_spec.py`
- Modify: `backend/app/tools/utility/list_session_resources_tool.py`
- Modify: `backend/app/api/utility_routes.py`
- Modify: `backend/app/api/office_routes.py`
- Modify: `backend/app/core/routing.py`
- Delete: `backend/app/agent/resources/manifest.py`
- Delete: `backend/app/agent/resources/manifest_test.py`
- Delete: `backend/app/agent/resources/models.py`
- Delete: `backend/app/agent/resources/models_test.py`
- Delete: `backend/app/agent/resources/service_test.py`
- Delete: stale migration tests referring to migration 008.
- Create: `backend/tests/test_no_legacy_resource_mechanisms.py`

- [ ] **Step 1: Write a failing static hard-cut test**

Scan production sources, not test fixtures, for forbidden behavior:

```python
FORBIDDEN = (
    "_extract_visualizations_from_messages",
    "_extract_office_documents_from_messages",
    "session_resource_manifests",
    'get("office_documents"',
    'metadata.get("visualizations"',
    '@router.get("/file/{file_path:path}")',
    '@router.post("/download-word")',
    '@router.post("/download-ppt")',
    '@router.post("/download-excel")',
)
```

Also inspect FastAPI OpenAPI and assert path-based file and typed download endpoints are absent.

- [ ] **Step 2: Run the hard-cut test and confirm failure**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_no_legacy_resource_mechanisms.py
```

Expected: FAIL with the current message extractors, legacy persistence signatures, and routes.

- [ ] **Step 3: Remove legacy recovery and persistence parameters**

Session restore returns `resource_version` and counts derived only from the unified resource service:

```python
session_data["resource_version"] = await resources.catalog_version(session_id)
session_data["resource_counts"] = (await resources.resource_counts(session_id)).model_dump()
```

Remove `office_documents` parameters and calls from conversation persistence. Remove legacy payload fields from adapters. Keep message lazy stripping only for message-size control, not for resource discovery.

- [ ] **Step 4: Remove path-based read/download routes and dead resource models**

Delete `/api/file/{path}` and Office typed download routes after repository-wide `rg` confirms Tasks 5–7 and frontend tasks have no consumers. If `utility_routes.py` has no remaining endpoint, remove its `RouterSpec`; otherwise retain the module without the path route.

Before deleting `SessionResourceRef`, convert composer selection, active contexts, and `list_session_resources` to `StoredResource` and the new enums from `contracts.py`. Selection IDs become `resource_id`; status/kind comparisons use their stored string values; public composer serialization uses the safe DTO fields and never includes `locator`. Then delete the dead manifest/ref implementation only after:

```bash
rg -n "agent\.resources\.(manifest|models)|SessionResourceRef|derive_legacy_views" backend/app --glob '*.py'
```

returns no production imports.

- [ ] **Step 5: Run backend hard-cut and session tests**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/test_no_legacy_resource_mechanisms.py backend/tests/api/test_session_catalog_routes.py backend/tests/api/test_social_history_adapter.py backend/tests/conversations
```

Expected: PASS with tests updated to `/resources` and no stale migration import.

- [ ] **Step 6: Commit backend cleanup**

```bash
git add -A backend/app backend/tests
git commit -m "refactor: remove legacy backend preview recovery"
```

### Task 9: Add the frontend resource API and sole per-session Store

**Files:**
- Create: `frontend/src/api/sessionResources.js`
- Create: `frontend/src/api/sessionResources.test.js`
- Create: `frontend/src/stores/sessionResourceStore.js`
- Create: `frontend/src/stores/sessionResourceStore.test.js`
- Modify: `frontend/src/api/session.js`

- [ ] **Step 1: Write failing API URL tests**

```javascript
assert.equal(resourceContentUrl('s 1', 'r/1'), '/api/sessions/s%201/resources/r%2F1/content')
assert.equal(resourceDownloadUrl('s 1', 'r/1'), '/api/sessions/s%201/resources/r%2F1/content?disposition=attachment')
assert.deepEqual(buildResourceQuery({ renderer: 'pdf', status: 'active', cursor: '20' }),
  'renderer=pdf&status=active&cursor=20')
```

- [ ] **Step 2: Write failing Store tests for isolation and version ordering**

```javascript
const store = createResourceStoreHarness()
await store.loadCatalog('session-a')
store.selectResource('session-a', 'resource-a')
await store.loadCatalog('session-b')
assert.equal(store.selectedResource('session-a').resource_id, 'resource-a')

await store.onResourcesChanged({ session_id: 'session-a', resource_version: 4 })
await store.onResourcesChanged({ session_id: 'session-a', resource_version: 3 })
assert.equal(fetchCount('session-a'), 2) // initial + version 4 only
```

Add a deferred-promise test proving a stale response is discarded after a new request token or session switch.

- [ ] **Step 3: Run frontend tests and confirm failure**

```bash
cd /home/xckj/suyuan/frontend
node --test src/api/sessionResources.test.js src/stores/sessionResourceStore.test.js
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 4: Implement API helpers and Pinia Store**

The API client exposes:

```javascript
export const listSessionResources = (sessionId, filters = {}) =>
  request(`${BASE_URL}/${encodeURIComponent(sessionId)}/resources?${buildResourceQuery(filters)}`)
export const resourceContentUrl = (sessionId, resourceId, { directory = false } = {}) =>
  `${BASE_URL}/${encodeURIComponent(sessionId)}/resources/${encodeURIComponent(resourceId)}/content${directory ? '/' : ''}`
export const resourceDownloadUrl = (sessionId, resourceId) =>
  `${resourceContentUrl(sessionId, resourceId)}?disposition=attachment`
export const invokeResourceAction = (actionUrl, payload = {}) => request(actionUrl, { method: 'POST', body: JSON.stringify(payload) })
```

The Store holds a state record per session and implements `loadCatalog`, `refreshIfNewer`, `onResourcesChanged`, `selectResource`, `selectGroup`, `activateSession`, and `clearSession`. It paginates until `next_cursor` is null, atomically replaces a catalog after all pages succeed, and never merges a response with a stale token.

- [ ] **Step 5: Remove specialized resource list methods from `session.js` and run tests**

Delete `getSessionVisualizations`, `getSessionOfficeDocuments`, and `getSessionDrawioBoard` after their consumers are moved in Tasks 12–13. Keep this commit buildable by exporting them nowhere and updating imports in the same task where needed.

```bash
cd /home/xckj/suyuan/frontend
node --test src/api/sessionResources.test.js src/stores/sessionResourceStore.test.js
```

Expected: PASS.

- [ ] **Step 6: Commit frontend resource state**

```bash
git add frontend/src/api/sessionResources.js frontend/src/api/sessionResources.test.js frontend/src/stores/sessionResourceStore.js frontend/src/stores/sessionResourceStore.test.js frontend/src/api/session.js
git commit -m "feat: add unified frontend session resource store"
```

### Task 10: Implement resource grouping and the file-products tab

**Files:**
- Create: `frontend/src/services/resourceGroups.js`
- Create: `frontend/src/services/resourceGroups.test.js`
- Create: `frontend/src/components/resources/ResourceProductsPanel.vue`
- Create: `frontend/src/components/resources/resourceProductsPanel.test.js`
- Modify: `frontend/src/components/management/taskOutputFiles.js`
- Modify: `frontend/src/components/management/TaskOutputFilesPanel.vue`
- Modify: `frontend/src/components/management/taskOutputFiles.test.js`

- [ ] **Step 1: Write failing selector tests**

```javascript
const groups = buildResourceGroups(fixtures)
assert.deepEqual(topLevelProducts(groups).map(x => x.label), ['报告.docx', '趋势图.png'])
assert.equal(topLevelProducts(groups).some(x => x.relation === 'preview'), false)
assert.equal(topLevelProducts(groups).some(x => x.role === 'attachment'), false)
assert.equal(preferredPreview(reportGroup).renderer, 'pdf')
assert.equal(targetTab(reportGroup), 'document')
assert.equal(targetTab(chartGroup), 'visualization')
assert.equal(targetTab(boardGroup), 'board')
assert.equal(targetTab(zipGroup), 'files')
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/resourceGroups.test.js src/components/resources/resourceProductsPanel.test.js
```

Expected: FAIL because grouping and the panel do not exist.

- [ ] **Step 3: Implement pure group selectors**

`buildResourceGroups()` groups by `group_id`, sorts by version/update time, identifies current primary, and indexes children by relation. `topLevelProducts()` accepts only active current primary resources with `role` in `output/report` and `kind` in `file/artifact/visual`. `preferredPreview()` chooses active preview, then rendition with a supported renderer, then the primary.

- [ ] **Step 4: Implement `ResourceProductsPanel.vue`**

The panel reads the active session from `sessionResourceStore`, renders product label/format/size/status/version, and emits no preview object. On click it calls:

```javascript
resourceStore.selectGroup(sessionId, group.group_id)
resourceStore.selectResource(sessionId, preferredPreview(group).resource_id)
emit('open-resource-tab', targetTab(group))
```

Versions and derivative formats expand beneath the main row; download uses `resource.download_url` through authenticated fetch.

- [ ] **Step 5: Reuse opaque content URLs in scheduled task output files**

Remove path and metadata URL inference from `taskOutputFiles.js`; accept only DTO `download_url`. Keep scheduled task grouping but render/download the same resource DTO shape.

- [ ] **Step 6: Run selector and panel tests**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/resourceGroups.test.js src/components/resources/resourceProductsPanel.test.js src/components/management/taskOutputFiles.test.js
```

Expected: PASS.

- [ ] **Step 7: Commit the file-products experience**

```bash
git add frontend/src/services/resourceGroups.js frontend/src/services/resourceGroups.test.js frontend/src/components/resources frontend/src/components/management/taskOutputFiles.js frontend/src/components/management/TaskOutputFilesPanel.vue frontend/src/components/management/taskOutputFiles.test.js
git commit -m "feat: add resource-backed file products tab"
```

### Task 11: Implement the renderer registry and common preview host

**Files:**
- Create: `frontend/src/services/resourceRendererRegistry.js`
- Create: `frontend/src/services/resourceRendererRegistry.test.js`
- Create: `frontend/src/components/resources/ResourcePreviewHost.vue`
- Create: `frontend/src/components/resources/renderers/PdfResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/HtmlResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/MarkdownResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/SpreadsheetResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/PresentationResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/ImageResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/ChartResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/BoardResourceRenderer.vue`
- Create: `frontend/src/components/resources/renderers/FileDetailRenderer.vue`
- Create: `frontend/src/components/resources/resourcePreviewHost.test.js`

- [ ] **Step 1: Write failing registry and host tests**

```javascript
assert.equal(rendererKey({ renderer: 'pdf' }), 'pdf')
assert.equal(rendererKey({ renderer: 'unknown' }), 'file')
assert.equal(rendererKey({ status: 'missing', renderer: 'pdf' }), 'file')
```

Source-level component tests assert renderers accept only `resource`, `group`, and `contentUrl` props; they must not import session APIs, `reactStore`, or inspect `file_path/pdf_id/html_id`.

- [ ] **Step 2: Run tests and confirm failure**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/resourceRendererRegistry.test.js src/components/resources/resourcePreviewHost.test.js
```

Expected: FAIL because registry and host do not exist.

- [ ] **Step 3: Implement the registry and preview boundary**

```javascript
export const RESOURCE_RENDERERS = Object.freeze({
  pdf: PdfResourceRenderer,
  html: HtmlResourceRenderer,
  markdown: MarkdownResourceRenderer,
  spreadsheet: SpreadsheetResourceRenderer,
  presentation: PresentationResourceRenderer,
  image: ImageResourceRenderer,
  chart: ChartResourceRenderer,
  board: BoardResourceRenderer,
  file: FileDetailRenderer
})
```

`ResourcePreviewHost` derives the selected resource/group from the resource Store, selects a component, provides loading/retry/missing/failed states, and catches renderer errors without mutating catalog data.

- [ ] **Step 4: Implement media renderers**

- PDF/image use the opaque content URL.
- HTML uses sandboxed iframe with `sandbox="allow-scripts allow-forms"`, no `allow-same-origin`, and the directory content URL supplied by the DTO.
- Markdown fetches authenticated content and passes text to `MarkdownRenderer`.
- Spreadsheet fetches content as ArrayBuffer and adapts it to the existing spreadsheet viewer/editor component without passing paths.
- Presentation renders child page resources from the group and never constructs `/api/file` URLs.
- Chart fetches JSON spec and passes it to the existing chart component.
- Board fetches XML/JSON and passes it to `DrawioBoardPanel`; board command actions refresh the resource Store.
- Fallback shows metadata, status, capabilities, versions, and the opaque download action.

- [ ] **Step 5: Run registry/host tests and component build**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/resourceRendererRegistry.test.js src/components/resources/resourcePreviewHost.test.js
npx vite build --mode standalone --outDir /tmp/suyuan-resource-plan-build
```

Expected: tests PASS and Vite exits 0. This temporary build is not deployment.

- [ ] **Step 6: Commit the renderer system**

```bash
git add frontend/src/services/resourceRendererRegistry.js frontend/src/services/resourceRendererRegistry.test.js frontend/src/components/resources
git commit -m "feat: render session resources through one preview host"
```

### Task 12: Drive live and restored conversations from the same resource Store

**Files:**
- Modify: `frontend/src/composables/reactAnalysis/useSessionManagement.js`
- Modify: `frontend/src/composables/reactAnalysis/usePanelManagement.js`
- Modify: `frontend/src/components/reactAnalysis/RightPanelContainer.vue`
- Modify: `frontend/src/components/reactAnalysis/MainLayout.vue`
- Modify: `frontend/src/views/ReactAnalysisView.vue`
- Modify: `frontend/src/views/ReactAnalysisViewRefactored.vue`
- Modify: `frontend/src/stores/reactStore.js`
- Create: `frontend/src/services/sessionResourceLifecycle.js`
- Create: `frontend/src/services/sessionResourceLifecycle.test.js`
- Create: `frontend/src/components/resources/rightPanelResources.test.js`

- [ ] **Step 1: Write failing lifecycle tests**

```javascript
await restoreConversation({ sessionId: 's1', restoreMessages, loadResources })
assert.equal(calls.restoreMessages, 1)
assert.equal(calls.loadResources, 1)
assert.equal(calls.extractResourcesFromMessages, 0)

await handleStreamEvent({ type: 'resources_changed', data: { session_id: 's1', resource_version: 2 } })
assert.equal(resourceStore.versionFor('s1'), 2)
```

Add deferred tests for switching from `s1` to `s2` before `s1` resources return, and for a higher SSE version arriving during initial restore.

- [ ] **Step 2: Write failing right-panel source tests**

Assert tabs are `files`, `document`, `visualization`, `board`, and `knowledge`; counts come from resource selectors; the file tab is available whenever tool products exist; preview tabs use `ResourcePreviewHost`; no message scan computes document/chart/board counts.

- [ ] **Step 3: Run lifecycle and right-panel tests**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/sessionResourceLifecycle.test.js src/components/resources/rightPanelResources.test.js
```

Expected: FAIL against separate lazy artifact loaders and message-derived visibility.

- [ ] **Step 4: Implement one lifecycle for new and restored sessions**

`sessionResourceLifecycle.js` exposes:

```javascript
export async function restoreSessionResources({ sessionId, expectedVersion, resourceStore, requestToken })
export async function applyResourceStreamEvent({ event, resourceStore })
export function chooseRestoredResource({ sessionId, resourceStore })
```

Session restore starts message restoration and `resourceStore.loadCatalog(sessionId)` concurrently. After catalog load, select the newest previewable top-level group. If a newer event arrived during load, refresh once more. New sessions start with an empty catalog version and use the same event handler.

- [ ] **Step 5: Replace right-panel data flow**

Add a permanent file-products tab when products exist. Document/chart/board tabs render `ResourcePreviewHost` with selector filters. Keep knowledge sources separate because they are message citations, not tool file resources. Remove message/history props from resource panels.

`reactStore` handles `resources_changed` only by delegating to `sessionResourceStore`; it does not copy resource payloads. Remove terminal `refreshDurableDocumentResources` calls and specialized lazy flags.

- [ ] **Step 6: Run lifecycle, panel, Store, and existing composer tests**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/sessionResourceLifecycle.test.js src/components/resources/rightPanelResources.test.js src/stores/sessionResourceStore.test.js src/stores/reactStoreQueue.test.js src/stores/reactStoreSteering.test.js
```

Expected: PASS.

- [ ] **Step 7: Commit unified live/restore behavior**

```bash
git add frontend/src/composables/reactAnalysis/useSessionManagement.js frontend/src/composables/reactAnalysis/usePanelManagement.js frontend/src/components/reactAnalysis/RightPanelContainer.vue frontend/src/components/reactAnalysis/MainLayout.vue frontend/src/views/ReactAnalysisView.vue frontend/src/views/ReactAnalysisViewRefactored.vue frontend/src/stores/reactStore.js frontend/src/services/sessionResourceLifecycle.js frontend/src/services/sessionResourceLifecycle.test.js frontend/src/components/resources/rightPanelResources.test.js
git commit -m "refactor: unify live and restored resource previews"
```

### Task 13: Delete the legacy frontend preview and download system

**Files:**
- Delete: files listed in the removal map above.
- Modify: `frontend/src/composables/reactAnalysis/index.js`
- Modify: `frontend/src/components/VisualizationPanel.vue` or replace its resource-facing usage with the chart renderer.
- Modify: `frontend/src/components/management/taskOutputFiles.js`
- Modify: all remaining imports found by the static scan.
- Create: `frontend/src/services/noLegacyResourceMechanisms.test.js`

- [ ] **Step 1: Write a failing frontend hard-cut scan**

Scan `frontend/src` production files and fail on:

```javascript
const forbidden = [
  'officeDocumentHistory', 'lastOfficeDocument', 'visualizationHistory',
  'extractOfficeDocumentsFromMessages', 'getSessionOfficeDocuments',
  'getSessionVisualizations', 'getSessionDrawioBoard',
  '/office-documents', '/visualizations', '/api/file/',
  '/api/office/download-word', '/api/office/download-ppt', '/api/office/download-excel',
  'pdf_preview', 'html_preview', 'markdown_preview', 'spreadsheet_preview', 'ppt_preview'
]
```

Allow explicit exceptions only in migration documentation outside `frontend/src`; do not add production allowlists.

- [ ] **Step 2: Run the scan and confirm failure**

```bash
cd /home/xckj/suyuan/frontend
node --test src/services/noLegacyResourceMechanisms.test.js
```

Expected: FAIL with current Store, panels, services, and URL construction.

- [ ] **Step 3: Delete legacy files and remove all remaining branches**

Delete the old Office document panel/services/composables and obsolete panel policy. Remove visualization extraction from messages and any path/download URL construction. Keep purely presentational chart/board components only when used beneath a resource renderer.

- [ ] **Step 4: Run the hard-cut scan and all frontend tests**

```bash
cd /home/xckj/suyuan/frontend
node --test src/**/*.test.js src/**/*.test.mjs
```

Expected: PASS. If the shell does not expand recursive globs, use the explicit package scripts plus `find src -name '*.test.js' -o -name '*.test.mjs'` to construct the same complete test list.

- [ ] **Step 5: Run a non-deployment production build**

```bash
cd /home/xckj/suyuan/frontend
npx vite build --mode standalone --outDir /tmp/suyuan-resource-hard-cut-build
```

Expected: exit 0; generated assets contain `/resources/` and none of the forbidden old endpoint strings.

- [ ] **Step 6: Commit frontend legacy removal**

```bash
git add -A frontend/src
git commit -m "refactor: remove legacy frontend preview mechanisms"
```

### Task 14: Add cross-stack new-conversation acceptance tests

**Files:**
- Create: `backend/tests/e2e/test_new_session_resource_delivery.py`
- Create: `frontend/e2e/session-resource-preview.spec.mjs`
- Modify: `frontend/package.json`
- Create: `backend/tests/test_resource_producer_inventory.py`

- [ ] **Step 1: Add a backend acceptance test for create, publish, restore, and content**

The test creates a new catalog/session, publishes a primary plus preview, restores the session, lists resources, and downloads both resources. Assert:

```python
assert restored["session"]["resource_version"] == 1
assert restored["session"]["resource_counts"]["total"] == 2
assert not contains_preview_payload(restored["session"]["conversation_history"])
assert catalog["resources"][0]["group_id"] == catalog["resources"][1]["group_id"]
assert all("locator" not in item for item in catalog["resources"])
```

- [ ] **Step 2: Add a producer inventory test**

Maintain an explicit inventory of output-capable tools and exercise each tool's result adapter or fixture. The assertion is behavioral, not a source substring check:

```python
for producer in OUTPUT_PRODUCERS:
    result = producer.fixture_result()
    declarations, rejected = normalize_tool_resources(result=result)
    assert not rejected, producer.name
    assert declarations, f"{producer.name} produced output without resources"
```

Inventory covers generic command/file tools, Office/PPT, reports, HTML artifacts, chart/image/map, board, browser downloads/screenshots, GFS downloads/processors, and analysis exports.

- [ ] **Step 3: Add Playwright new-session live/reload tests**

For each fixture type (DOCX/PDF, HTML, Markdown, spreadsheet, PPT, image, chart, board), mock or seed a resource group, emit `resources_changed`, click the file product, assert the target tab/renderer, reload, restore the same session, and assert the same `resource_id` remains selected.

Add `test:session-resources` to `frontend/package.json`:

```json
"test:session-resources": "node --test src/api/sessionResources.test.js src/stores/sessionResourceStore.test.js src/services/resourceGroups.test.js src/services/sessionResourceLifecycle.test.js src/services/noLegacyResourceMechanisms.test.js && playwright test e2e/session-resource-preview.spec.mjs"
```

- [ ] **Step 4: Run backend acceptance and producer inventory**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/e2e/test_new_session_resource_delivery.py backend/tests/test_resource_producer_inventory.py
```

Expected: PASS.

- [ ] **Step 5: Run frontend acceptance**

```bash
cd /home/xckj/suyuan/frontend
npm run test:session-resources
```

Expected: PASS for all resource types and reload scenarios.

- [ ] **Step 6: Commit acceptance coverage**

```bash
git add backend/tests/e2e/test_new_session_resource_delivery.py backend/tests/test_resource_producer_inventory.py frontend/e2e/session-resource-preview.spec.mjs frontend/package.json
git commit -m "test: cover unified resource preview hard cutover"
```

### Task 15: Run full verification, hard-cut the production database, build, and deploy

**Files:**
- No new source files expected.
- Runtime mutation: production database schema, `frontend/dist`, and Nginx reload.

- [ ] **Step 1: Verify the worktree contains no unrelated changes**

```bash
git status --short
git diff --check
```

Expected: only intentional task changes before their commits; existing unrelated `NormCraftAI/` remains untouched.

- [ ] **Step 2: Run the complete backend test suite**

```bash
cd /home/xckj/suyuan
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests backend/app
```

Expected: exit 0 with no collection errors or failures.

- [ ] **Step 3: Run all frontend test scripts and the acceptance suite**

```bash
cd /home/xckj/suyuan/frontend
npm run test:project-config
npm run test:auth
npm run test:event-tasks
npm run test:images
npm run test:agent-platform
npm run test:composer
npm run test:session-resources
```

Expected: every command exits 0.

- [ ] **Step 4: Verify hard-cut source invariants before touching production**

```bash
cd /home/xckj/suyuan
rg -n "officeDocumentHistory|lastOfficeDocument|visualizationHistory|officeDocumentRecovery|sessionDocumentResources|/api/file/|download-word|download-ppt|download-excel|/office-documents|/visualizations" frontend/src backend/app
rg -n "session_resource_manifests|data_ids|visual_ids|office_documents" backend/app --glob '*.py'
```

Expected: no production matches for legacy resource mechanisms. Domain-neutral words inside unrelated data models must be reviewed rather than blindly accepted.

- [ ] **Step 5: Apply migration 014 without creating a backup**

Use the project's configured production database connection from `/home/xckj/suyuan/backend` and execute `backend/app/db/migrations/014_hard_cutover_resource_delivery.sql` in one transaction. Do not create a dump or copy old tables. Verify:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'session_resources'
ORDER BY ordinal_position;

SELECT to_regclass('session_resource_manifests');

SELECT column_name
FROM information_schema.columns
WHERE table_name = 'sessions'
  AND column_name IN ('data_ids', 'visual_ids', 'office_documents');
```

Expected: grouped resource columns are present; `to_regclass` is null; the legacy session-column query returns zero rows.

- [ ] **Step 6: Restart the backend and verify public routes**

Restart the existing Uvicorn service using the repository's current process supervisor. Then run:

```bash
curl -fsS http://127.0.0.1:8000/openapi.json | jq -r '.paths | keys[]' | rg '/api/sessions/.*/resources'
curl -fsS http://127.0.0.1:8000/openapi.json | jq -r '.paths | keys[]' | rg '/api/file|download-word|download-ppt|download-excel|office-documents|visualizations'
```

Expected: the first command lists catalog and content paths; the second returns no matches. Domain edit/render/share action paths remain discoverable only through each resource DTO's trusted `actions` map.

- [ ] **Step 7: Build the only production frontend bundle**

```bash
cd /home/xckj/suyuan/frontend
npm run build:standalone
```

Expected: Vite build exits 0 and writes `/home/xckj/suyuan/frontend/dist`.

- [ ] **Step 8: Verify the production bundle contains only unified delivery**

```bash
grep -R "sessions/" /home/xckj/suyuan/frontend/dist/assets | grep "resources"
! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/api/file/" /home/xckj/suyuan/frontend/dist/assets
! grep -R "download-word\|download-ppt\|download-excel" /home/xckj/suyuan/frontend/dist/assets
```

Expected: unified resource strings found; every negative check exits successfully.

- [ ] **Step 9: Reload Nginx and run production smoke tests**

```bash
docker exec suyuan-nginx nginx -s reload
curl -fsS -o /dev/null http://127.0.0.1:5174/
curl -fsS -o /dev/null http://127.0.0.1:8000/openapi.json
```

Create a new production conversation and generate at least one document, chart, board, and ordinary file. For each: confirm file-products visibility, click-through renderer, authenticated download, browser refresh, and restored preview with the same resource ID.

- [ ] **Step 10: Record final verification and commit any deployment-only documentation change**

If no source change was needed, do not create an empty commit. Report exact test counts, build result, migration verification, OpenAPI route scan, bundle scan, Nginx reload result, and new-session smoke resource IDs.

---

## Plan self-review checklist

- Spec coverage: Tasks 1–8 cover model, persistence, API, live events, all producer families, actions, charts/boards, and backend deletion; Tasks 9–13 cover the sole Store, file-products tab, renderer registry, live/restore parity, and frontend deletion; Tasks 14–15 cover all stated tests and hard-cut deployment.
- No history migration or backup step is present; migration 014 deliberately replaces old resource state.
- No compatibility read, dual write, or legacy frontend fallback is introduced.
- The same names are used throughout: `group_id`, `parent_resource_id`, `relation`, `renderer`, `capabilities`, `catalog_version/resource_version`, `resources_changed`, and `sessionResourceStore`.
- Resource content is always addressed by `session_id + resource_id`; only directory artifact assets add a safe relative `asset_path` beneath that opaque resource.
