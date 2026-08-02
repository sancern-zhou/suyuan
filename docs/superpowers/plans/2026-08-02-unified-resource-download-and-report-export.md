# Unified Resource Download and Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one capability-driven download/export surface for every previewable resource and make QMD HTML/Word deliverables first-class members of the same unified resource group.

**Architecture:** Resource groups remain authoritative: primary means original download, preview means display-only, and rendition means exported deliverable. A restricted render action derives the trusted report package from the QMD resource, invokes existing Quarto renderers, attaches renditions, and returns only a catalog mutation receipt.

**Tech Stack:** FastAPI, Pydantic, Quarto, SQLAlchemy resource repository, Vue 3, Pinia, Playwright, Node test runner, pytest.

---

### Task 1: Capability-driven resource render action

**Files:**
- Modify: `backend/app/agent/resources/actions.py`
- Modify: `backend/app/api/session_resource_routes.py`
- Modify: `backend/app/services/quarto_report_renderer.py`
- Test: `backend/tests/api/test_resource_actions_refresh_catalog.py`

- [ ] Add tests proving only an active report QMD primary can render `docx`/`html`, that write authorization is required, and that the returned receipt contains `resource_version` plus `changed_resource_ids`.
- [ ] Extend `resource_action_links()` so `render` capability projects `/api/sessions/{session}/resources/{resource}/render` without exposing locator or report ID.
- [ ] Add a strict request model with `format: Literal['docx', 'html']` and a POST route that resolves a standard `reports/{id}/report.qmd`, rejects path escape/non-QMD resources, and calls the renderer off the event loop.
- [ ] Reuse `quarto_report_renderer.render_docx()` for DOCX. Add `render_share_html()` using Quarto HTML with embedded resources for a standalone downloadable HTML rendition.
- [ ] Extend `attach_rendered_file()` to accept explicit capabilities and label, attach a `rendition`, and keep stable keys for repeat exports.
- [ ] Run `pytest backend/tests/api/test_resource_actions_refresh_catalog.py -q` and commit the backend action boundary.

### Task 2: Correct QMD report group declarations

**Files:**
- Modify: `backend/app/tools/artifact_utils.py`
- Test: `backend/tests/tools/test_artifact_utils.py` or the existing artifact contract test containing `attach_document_artifact`

- [ ] Add a test asserting a QMD report group contains a markdown primary with `preview/download/render` and a directory HTML preview with `entrypoint=report.html`, relation `preview`, and the QMD parent key.
- [ ] Build report HTML previews with `directory_artifact(report_dir, entrypoint='report.html')`, then set relation/parent key for the group; do not publish `report.html` as an isolated file.
- [ ] Preserve direct QMD download and ensure HTML preview directory has preview capability but is not treated as the original download.
- [ ] Run the targeted artifact tests and commit the corrected report group contract.

### Task 3: Unified preview action bar

**Files:**
- Create: `frontend/src/components/resources/ResourcePreviewActions.vue`
- Create: `frontend/src/services/resourceDownloads.js`
- Modify: `frontend/src/components/resources/ResourcePreviewHost.vue`
- Modify: `frontend/src/components/resources/renderers/PdfResourceRenderer.vue`
- Modify: `frontend/src/api/sessionResources.js`
- Test: `frontend/src/components/resources/resourcePreviewActions.test.js`
- Test: `frontend/e2e/session-resource-preview.spec.mjs`

- [ ] Add pure tests for format labels, original selection, existing rendition selection, and render-action availability.
- [ ] Centralize authenticated Blob download in `resourceDownloads.js`, preserving the resource label/extension.
- [ ] Render a top action bar whenever the group primary has `download`; use the primary for “下载原始文件” even when a PDF/HTML preview is selected.
- [ ] For QMD groups expose “下载 QMD”, “导出 HTML”, and “导出 Word”. Invoke the trusted render action, refresh the catalog, locate the new rendition, and download it; reuse an existing rendition without rendering again.
- [ ] Keep the PDF browser toolbar and make the unified action bar explicitly label the original format, such as “下载原始 DOCX”, so saving the preview and downloading the original are distinct operations.
- [ ] Add E2E coverage for Word preview downloading DOCX, generic HTML/Markdown download visibility, QMD Word export, and restored existing rendition download.
- [ ] Run `npm run test:session-resources` and commit the frontend interaction.

### Task 4: Full verification and deployment

**Files:**
- Verify: `frontend/dist`

- [ ] Run the unified resource backend suite and all new action/report tests.
- [ ] Run `npm run test:session-resources` and `npm run build:standalone` from `/home/xckj/suyuan/frontend`.
- [ ] Verify the production bundle contains `/resources` and excludes `/office-documents`, `/visualizations`, `/api/office`, `/api/file/`, `/api/reports`, and `/api/html-artifacts`.
- [ ] Restart the backend with `/home/xckj/suyuan/backend/restart_server.sh`, reload `suyuan-nginx`, and verify direct plus gateway readiness.
- [ ] Confirm only the unrelated `NormCraftAI/` path remains untracked.
