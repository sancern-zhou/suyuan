# Unified Session Resources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all duplicated session resource, document preview, and visualization persistence with one explicit, row-oriented `session_resources` mechanism.

**Architecture:** Tools return a top-level `resources` contract. The shared Agent runtime normalizes and accumulates those entries once, then atomically upserts the latest resource rows before terminal events. A single authorized API and a single Pinia resource map serve model context, composer selection, document previews, visualizations, and restore counts. Legacy Session fields, transcript extraction, compatibility inference, and old restore endpoints are removed without migration reads.

**Tech Stack:** Python 3.11, Pydantic, SQLAlchemy async/PostgreSQL JSONB, FastAPI, pytest, Vue 3, Pinia, Vitest.

---

## File Map

- Create `backend/app/agent/resources/contracts.py`: explicit resource and presentation Pydantic contracts.
- Create `backend/app/agent/resources/resource_service.py`: validation, key derivation, upsert, query, delete, and version coordination.
- Create `backend/app/db/migrations/009_create_session_resources.sql`: row-oriented resource schema.
- Modify `backend/app/db/models_session.py`: add resource row/version ORM models; remove old Session resource columns.
- Modify `backend/app/agent/resources/normalizer.py`: accept only explicit `resources`.
- Modify `backend/app/agent/resources/runtime.py`: accumulate normalized resources and flush via the new service.
- Modify `backend/app/agent/react_agent.py`: remove legacy projections and office-document capture; use one runtime resource path.
- Modify `backend/app/api/session_routes.py`: replace artifact endpoints and restore metadata with unified resource queries.
- Modify `backend/app/conversations/adapters.py` and `backend/app/agent/session/session_manager_db.py`: stop loading old fields and expose resource counts.
- Modify `backend/app/agent/session/models.py` and `conversation_persistence.py`: remove old resource fields/parameters.
- Modify producing tools under `backend/app/tools/`: emit explicit `resources` entries with stable logical keys and presentations.
- Modify `frontend/src/api/session.js`: expose one filtered resource endpoint.
- Modify `frontend/src/stores/reactStore.js`: replace legacy histories with one resource map.
- Modify `frontend/src/composables/reactAnalysis/useSessionManagement.js`: restore and lazy-load through unified resources.
- Modify `frontend/src/components/OfficeDocumentPanel.vue` and visualization consumers: use filtered resource projections.
- Create backend and frontend contract, persistence, API, restore, and end-to-end tests.

## Task 1: Add the canonical contracts and failing tests

**Files:**
- Create: `backend/app/agent/resources/contracts.py`
- Create: `backend/tests/agent/resources/test_contracts.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_document_resource_requires_logical_key():
    with pytest.raises(ValueError, match="logical_key"):
        ResourceDeclaration.model_validate({
            "kind": "file",
            "role": "report",
            "label": "report",
            "locator": {"path": "/tmp/report.html"},
            "presentation_type": "document",
            "presentation": {"format": "html", "preview": {"type": "html", "url": "/p"}},
        })


def test_resource_key_is_stable_and_file_can_have_document_presentation():
    resource = ResourceDeclaration.model_validate({
        "kind": "file", "logical_key": "upload:file-1", "role": "attachment",
        "label": "report.docx", "locator": {"path": "/tmp/report.docx"},
        "presentation_type": "document",
        "presentation": {"format": "pdf", "preview": {"type": "pdf", "url": "/p"}},
    })
    assert resource.resource_key() == "upload:file-1"


def test_legacy_top_level_fields_are_not_accepted():
    with pytest.raises(ValidationError):
        ResourceDeclaration.model_validate({"file_path": "/tmp/old.docx"})
```

- [ ] **Step 2: Run the tests and verify RED**

Run from `backend/`:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_contracts.py
```

Expected: FAIL because the canonical contracts do not exist.

- [ ] **Step 3: Implement the contracts**

Define strict Pydantic models for `ResourceDeclaration`, `ResourceLocator`,
`DocumentPresentation`, and `VisualizationPresentation`. Validate exactly one locator
identity, require `logical_key` for `presentation_type in {document, visualization}`,
enforce allowlisted metadata and bounded JSON size, and derive `resource_key` from
`logical_key` or `kind + canonical locator`.

- [ ] **Step 4: Run the tests and verify GREEN**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_contracts.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/resources/contracts.py backend/tests/agent/resources/test_contracts.py
git commit -m "feat: define unified session resource contracts"
```

## Task 2: Create the row-oriented store and service

**Files:**
- Create: `backend/app/db/migrations/009_create_session_resources.sql`
- Modify: `backend/app/db/models_session.py`
- Create: `backend/app/agent/resources/resource_service.py`
- Create: `backend/tests/agent/resources/test_resource_service.py`

- [ ] **Step 1: Write failing service tests**

Test that `upsert_run_resources()` inserts resources, replaces the same logical key,
keeps distinct keys, increments one session version per transaction, returns filtered
pagination, and deletes idempotently. Test that an invalid declaration is rejected
without writing and that empty input never clears existing rows.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_resource_service.py
```

- [ ] **Step 3: Add the schema and ORM models**

Create `session_resources` with `(session_id, resource_key)` primary key, unique
`resource_id`, typed string columns, JSONB locator/presentation/metadata, status and
timestamps. Create `session_resource_versions(session_id primary key, version,
updated_at)`. Do not add a foreign key to transcript tables.

- [ ] **Step 4: Implement transactional service methods**

Implement:

```python
async def upsert_run_resources(session_id, run_id, resources) -> ResourceBatchResult
async def list_resources(session_id, *, kind=None, presentation_type=None, role=None,
                         status="active", limit=100, cursor=None) -> ResourcePage
async def resource_counts(session_id) -> ResourceCounts
async def delete_resource(session_id, resource_key) -> bool
async def delete_session_resources(session_id) -> bool
```

Use one transaction, lock the version row, reject stale run ownership before calling
the service, replace matching rows, increment once, and commit before returning.

- [ ] **Step 5: Run service tests GREEN and commit**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_resource_service.py
git add backend/app/db/migrations/009_create_session_resources.sql backend/app/db/models_session.py backend/app/agent/resources/resource_service.py backend/tests/agent/resources/test_resource_service.py
git commit -m "feat: add unified session resource store"
```

## Task 3: Make runtime capture explicit resources exactly once

**Files:**
- Modify: `backend/app/agent/resources/normalizer.py`
- Modify: `backend/app/agent/resources/runtime.py`
- Modify: `backend/app/agent/react_agent.py`
- Create: `backend/tests/agent/resources/test_runtime_unified_resources.py`

- [ ] **Step 1: Write failing runtime tests**

Cover explicit `data.resources`, one resource from a tool result followed by a
document SSE event without a second capture, all four terminal outcomes, stale-run
rejection, and durability metadata ordering.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_runtime_unified_resources.py
```

- [ ] **Step 3: Remove compatibility normalization**

Replace nested/top-level inference in `normalizer.py` with validation of only the
explicit `resources` list. `RunReferenceAccumulator.capture()` handles successful
`tool_result` events only; document/HTML transport events are emitted from the same
normalized declarations and are never recaptured.

- [ ] **Step 4: Flush through `SessionResourceService`**

In `ReActAgent.analyze`, accumulate each successful result and call
`upsert_run_resources()` before yielding complete, incomplete, interrupted, or fatal
events. Remove `_capture_office_document`, `derive_legacy_views`, and all
`_session_store[session_id]["office_documents"]` writes. Include only committed
resource version/durability fields in terminal events.

- [ ] **Step 5: Run tests and commit**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_runtime_unified_resources.py
git add backend/app/agent/resources/normalizer.py backend/app/agent/resources/runtime.py backend/app/agent/react_agent.py backend/tests/agent/resources/test_runtime_unified_resources.py
git commit -m "feat: persist explicit resources once at runtime boundary"
```

## Task 4: Convert resource-producing tools to the explicit contract

**Files:**
- Modify: `backend/app/tools/resource_refs.py`
- Modify: resource-producing tools in `backend/app/tools/report/`, `backend/app/tools/office/`, `backend/app/tools/utility/`, `backend/app/tools/visualization/`, and upload handling.
- Create: `backend/tests/tools/test_resource_contract_coverage.py`

- [ ] **Step 1: Add contract coverage tests**

Test report, HTML artifact, Office read/edit, present artifact, spreadsheet, chart,
upload, and data-producing tools. Assert every successful resource-producing result
has explicit `resources`, stable logical keys, and no legacy-only fields.

- [ ] **Step 2: Implement builders**

Update `build_file_ref`, `build_artifact_ref`, and visualization builders to produce
`ResourceDeclaration` dictionaries with `logical_key`, locator, role, and bounded
presentation descriptors. Presenting a selected upload preserves its logical key.

- [ ] **Step 3: Migrate all producers and verify**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/test_resource_contract_coverage.py
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/tools/resource_refs.py backend/app/tools/artifact_utils.py \
  backend/app/tools/report/report_package/tool.py backend/app/tools/html_artifact/tool.py \
  backend/app/tools/report/read_docx/tool.py backend/app/tools/utility/present_artifact_tool.py \
  backend/app/tools/utility/read_file_tool.py backend/app/tools/utility/execute_python_tool.py \
  backend/app/tools/visualization/create_report_chart/tool.py \
  backend/app/tools/office/read_pptx_tool.py backend/app/tools/office/ppt_master_tool.py \
  backend/tests/tools/test_resource_contract_coverage.py
git commit -m "feat: emit explicit unified resource declarations"
```

## Task 5: Remove legacy Session persistence and add unified API

**Files:**
- Modify: `backend/app/agent/session/models.py`
- Modify: `backend/app/db/models_session.py`
- Modify: `backend/app/agent/session/session_manager_db.py`
- Modify: `backend/app/agent/session/conversation_persistence.py`
- Modify: `backend/app/conversations/adapters.py`
- Modify: `backend/app/api/session_routes.py`
- Create: `backend/tests/api/test_unified_session_resources.py`

- [ ] **Step 1: Write failing API tests**

Test authorized filtered resource queries, counts in restore, cursor pagination,
absence of `/office-documents` and `/visualizations`, and rejection of transcript-only
legacy payloads.

- [ ] **Step 2: Verify RED**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/api/test_unified_session_resources.py
```

- [ ] **Step 3: Remove old model and persistence fields**

Delete `data_ids`, `visual_ids`, `office_documents`, and visualization metadata
handling from Session, SessionDB, adapters, session manager, and persistence service.
Remove message artifact extraction and all process-memory fallback reads.

- [ ] **Step 4: Implement the unified endpoint and restore counts**

Add one authorized `/resources` route that passes filters to `SessionResourceService`.
Make restore query `resource_counts()` and return counts without presentation payloads.
Delete the two dedicated artifact routes.

- [ ] **Step 5: Run backend API tests and commit**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/api/test_unified_session_resources.py
git add backend/app/agent/session/models.py backend/app/agent/session/session_manager_db.py \
  backend/app/agent/session/conversation_persistence.py backend/app/db/models_session.py \
  backend/app/conversations/adapters.py backend/app/api/session_routes.py \
  backend/tests/api/test_unified_session_resources.py
git commit -m "feat: expose one unified session resource API"
```

## Task 6: Switch frontend to one resource map

**Files:**
- Modify: `frontend/src/api/session.js`
- Modify: `frontend/src/stores/reactStore.js`
- Modify: `frontend/src/composables/reactAnalysis/useSessionManagement.js`
- Modify: `frontend/src/components/OfficeDocumentPanel.vue` and visualization consumers.
- Create: `frontend/src/stores/unifiedResourceStore.test.mjs`

- [ ] **Step 1: Write failing frontend tests**

Test one upsert path for SSE and restore, document/visual/file computed filters,
latest logical-key replacement, session isolation, and non-durable resources not
surviving refresh.

- [ ] **Step 2: Verify RED**

```bash
node --test frontend/src/stores/unifiedResourceStore.test.mjs
```

- [ ] **Step 3: Implement API and store**

Add `getSessionResources(sessionId, filters)` and replace legacy histories with
`sessionResourcesById`, counts, filter loading state, and one `upsertSessionResource`
action. Derive document, visualization, and selectable-file lists from the map.

- [ ] **Step 4: Update recovery and panels**

Restore counts from the session response, lazy-load through `/resources` filters,
write real-time normalized resource events through the same upsert action, and make
OfficeDocumentPanel consume `presentation_type=document` only.

- [ ] **Step 5: Run frontend tests and commit**

```bash
node --test frontend/src/stores/unifiedResourceStore.test.mjs
git add frontend/src/api/session.js frontend/src/stores/reactStore.js frontend/src/composables/reactAnalysis/useSessionManagement.js frontend/src/components/OfficeDocumentPanel.vue frontend/src/stores/unifiedResourceStore.test.mjs
git commit -m "feat: use one frontend session resource store"
```

## Task 7: Hard-cutover schema cleanup and lifecycle tests

**Files:**
- Create: `backend/app/db/migrations/010_drop_legacy_session_resources.sql`
- Modify: session deletion workflows and cleanup jobs.
- Create: `backend/tests/agent/resources/test_resource_lifecycle.py`

- [ ] **Step 1: Write failing lifecycle tests**

Assert old columns and old manifest table are absent, true conversation deletion
removes resource rows, deletion is retry-safe, and old message/metadata fixtures do
not restore resources.

- [ ] **Step 2: Add destructive hard-cutover migration**

Drop `session_resource_manifests`, `sessions.data_ids`, `sessions.visual_ids`, and
`sessions.office_documents`; remove `visualizations` JSON keys. Do not backfill.

- [ ] **Step 3: Route all deletion paths through resource deletion**

After authorization and transcript deletion, call `delete_session_resources()` and
log each lifecycle stage. Make repeated deletion idempotent.

- [ ] **Step 4: Run lifecycle tests and commit**

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/agent/resources/test_resource_lifecycle.py
git add backend/app/db/migrations/010_drop_legacy_session_resources.sql \
  backend/app/agent/session/models.py backend/app/agent/session/session_manager_db.py \
  backend/app/agent/session/conversation_persistence.py backend/app/db/models_session.py \
  backend/app/api/session_routes.py backend/app/conversations/adapters.py \
  backend/tests/agent/resources/test_resource_lifecycle.py
git commit -m "feat: remove legacy session resource persistence"
```

## Task 8: Full verification and handoff

- [ ] **Step 1: Run focused backend tests**

```bash
cd backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q \
  tests/agent/resources \
  tests/api/test_unified_session_resources.py \
  tests/tools/test_resource_contract_coverage.py
```

- [ ] **Step 2: Run frontend tests and build**

```bash
node --test frontend/src/auth/*.test.mjs frontend/src/components/management/*.test.js \
  frontend/src/components/inputBoxAttachments.test.js \
  frontend/src/components/inputBoxCommandPalette.test.js \
  frontend/src/components/inputBoxPlaceholder.test.js \
  frontend/src/components/inputBoxSelectionDraft.test.js \
  frontend/src/services/reactRequestBody.test.js \
  frontend/src/services/reactApi-map-context.test.mjs \
  frontend/src/services/streamAcceptance.test.js \
  frontend/src/stores/reactStoreQueue.test.js frontend/src/stores/reactStoreSteering.test.js
npm run build
```

- [ ] **Step 3: Run static contract searches**

```bash
rg -n "office_documents|visual_ids|data_ids|metadata\.visualizations|/office-documents|/visualizations|derive_legacy_views|_extract_office_documents" backend frontend
```

Expected: no production references remain; only intentional migration/test assertions
may mention removed names.

- [ ] **Step 4: Verify database schema and end-to-end flow**

Against the configured database, verify `session_resources` and
`session_resource_versions` exist, old tables/columns do not, and a newly generated
document and visualization survive a page refresh and service restart.

- [ ] **Step 5: Commit only verified changes**

```bash
git status --short
git diff --check
git log --oneline -10
```
