# Unified Resource Download, Layout, and Excel Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make resource downloads reliable, align file-product actions, and restore editable multi-sheet Excel previews whose saves create unified resource versions.

**Architecture:** Browser downloads use signed resource links directly. Spreadsheet edits are serialized with SheetJS and posted to a resource-scoped `save` action; the resource service atomically supersedes the active spreadsheet primary and publishes a new primary in the same group. No filesystem locator or legacy Office API crosses the frontend boundary.

**Tech Stack:** Vue 3, Pinia, SheetJS, Playwright, FastAPI, SQLAlchemy, pytest.

---

### Task 1: Reliable native downloads and stable product actions

**Files:**
- Modify: `frontend/src/components/resources/ResourcePreviewActions.vue`
- Modify: `frontend/src/components/resources/ResourceProductsPanel.vue`
- Modify: `frontend/src/services/resourceDownloads.js`
- Test: `frontend/e2e/session-resource-preview.spec.mjs`

- [ ] Add a Playwright test that waits for a download after clicking `下载原始 Excel`, and a QMD/HTML-rendition fixture that asserts the product `打开` and `下载` controls share one fixed action column.
- [ ] Run `npx playwright test e2e/session-resource-preview.spec.mjs` and verify the new assertions fail against the current async button and auto-placed grid.
- [ ] Render ordinary downloads as `<a :href="resource.download_url" :download="downloadFileName(resource)">`; retain async buttons only for QMD render actions. Give each product an explicit `.product-actions` column containing `打开` and the download link. Delay removal of dynamically created anchors used after QMD exports.
- [ ] Re-run the Playwright file and verify it passes.

### Task 2: Same-group spreadsheet replacement in the resource service

**Files:**
- Modify: `backend/app/agent/resources/resource_service.py`
- Modify: `backend/app/db/session_resources_repository.py`
- Test: `backend/tests/agent/resources/test_resource_service.py`

- [ ] Add an in-memory service test publishing an editable spreadsheet, replacing its primary file, and asserting the group ID is unchanged, the version increments, the old resource is superseded, the new locator points at the edited file, and the catalog version increments.
- [ ] Run the focused pytest and verify failure because `replace_primary_file` does not exist.
- [ ] Implement `SessionResourceService.replace_primary_file(session_id, run_id, resource_id, path)` with canonical materialization and matching in-memory/repository transactions. Restrict replacement to an active primary; atomically supersede the active group and insert a new primary with `stable_resource_id(..., next_version, resource_key)`.
- [ ] Re-run the focused service tests and verify they pass.

### Task 3: Unified spreadsheet save action

**Files:**
- Modify: `backend/app/agent/resources/actions.py`
- Modify: `backend/app/api/session_resource_routes.py`
- Modify: `backend/app/api/upload_routes.py`
- Test: `backend/tests/api/test_session_resource_catalog.py`
- Create: `backend/tests/api/test_session_resource_save.py`

- [ ] Add tests proving an editable spreadsheet DTO exposes only a unified `/resources/{id}/save` action, uploaded spreadsheets receive `edit`, and save rejects non-spreadsheets while returning a replacement receipt for valid XLS/XLSX payloads.
- [ ] Run those tests and verify the missing action/route failures.
- [ ] Project `actions.save` only for resources with `edit` and `renderer=spreadsheet`; externalize it in the DTO. Add `POST /{session_id}/resources/{resource_id}/save` using authenticated session write access, `UploadFile`, format/size checks, a temporary file, and `replace_primary_file`. Add `edit` to uploaded spreadsheet declarations.
- [ ] Re-run the focused API/upload tests and verify they pass.

### Task 4: Interactive unified spreadsheet renderer

**Files:**
- Create: `frontend/src/services/spreadsheetResourceApi.js`
- Create: `frontend/src/services/spreadsheetResourceApi.test.js`
- Modify: `frontend/src/components/resources/renderers/SpreadsheetResourceRenderer.vue`
- Modify: `frontend/src/components/resources/ResourcePreviewHost.vue`
- Modify: `frontend/src/stores/sessionResourceStore.js`
- Test: `frontend/e2e/session-resource-preview.spec.mjs`

- [ ] Add service tests for multipart save requests and Playwright coverage for sheet switching, cell editing, save receipt handling, catalog refresh, and the new active resource selection.
- [ ] Run the focused frontend tests and verify failures against the static first-sheet renderer.
- [ ] Implement workbook state with sheet tabs, editable cell inputs, row/column headers, reload and save controls. Serialize edited sheets with SheetJS, call `resource.actions.save`, refresh the catalog by receipt version, and select the new resource in the same group.
- [ ] Re-run focused frontend tests and verify they pass.

### Task 5: Regression, build, and deployment

**Files:**
- Verify all files above.

- [ ] Run the focused backend resource suite under `/root/miniconda3/envs/backend_py311`.
- [ ] Run `npm run test:session-resources` in `frontend`.
- [ ] Run `npm run build:standalone` in `frontend`.
- [ ] Verify `dist/assets` contains `resources?presentation_type=document` and contains neither `/office-documents` nor `/visualizations`.
- [ ] Reload `suyuan-nginx`, restart the backend using the repository's existing process method, and verify health plus runtime logs.
- [ ] Commit only the files belonging to this change; leave the pre-existing dirty backend context files and `NormCraftAI/` untouched.
