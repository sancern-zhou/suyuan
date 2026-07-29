# Realtime Document Resource Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh durable unified document resources when a live Agent run completes so the existing right panel opens automatically.

**Architecture:** Extract the existing unified-resource-to-office-document mapping into a focused module and add a testable refresh coordinator with version, in-flight, and session guards. The React store triggers this coordinator from `complete`; the existing panel watcher reacts to `lastOfficeDocument` without UI changes.

**Tech Stack:** Vue 3, Pinia, JavaScript ES modules, Node.js test runner, Vite.

---

### Task 1: Unified document resource mapper

**Files:**
- Create: `frontend/src/services/sessionDocumentResources.js`
- Create: `frontend/src/services/sessionDocumentResources.test.js`
- Modify: `frontend/src/composables/reactAnalysis/useSessionManagement.js`

- [ ] **Step 1: Write the failing mapper test**

Create a Node test that passes an XLSX unified resource containing `locator.path`,
`presentation.format`, and `presentation.preview`, then asserts the mapped document exposes
`file_path`, lowercase `format`, a truthy `pdf_preview`, and `spreadsheet_preview`.

- [ ] **Step 2: Run the mapper test and verify RED**

Run: `cd /home/xckj/suyuan/frontend && node --test src/services/sessionDocumentResources.test.js`

Expected: FAIL because `sessionDocumentResources.js` or its exported mapper does not exist.

- [ ] **Step 3: Implement the mapper**

Export `mapSessionDocumentResource(resource)` and `mapSessionDocumentResources(resources)`.
Move the mapping currently embedded in `useSessionManagement.js` into these pure functions,
preserving PDF, HTML, Markdown, SVG, and spreadsheet fields.

- [ ] **Step 4: Reuse the mapper during session recovery**

Import `mapSessionDocumentResources` in `useSessionManagement.js` and replace the inline
`response.resources.map(...)` block with:

```js
const officeDocs = mapSessionDocumentResources(response?.resources)
```

- [ ] **Step 5: Run the mapper test and verify GREEN**

Run: `cd /home/xckj/suyuan/frontend && node --test src/services/sessionDocumentResources.test.js`

Expected: PASS with zero failures.

### Task 2: Durable complete refresh coordinator

**Files:**
- Modify: `frontend/src/services/sessionDocumentResources.js`
- Modify: `frontend/src/services/sessionDocumentResources.test.js`

- [ ] **Step 1: Write failing coordinator tests**

Add tests for `refreshDurableDocumentResources(options)` covering:

```js
await refreshDurableDocumentResources({
  terminalData: { resource_durable: true, resource_version: 2 },
  sessionId: 'assistant_session_1',
  targetState,
  fetchDocuments,
  applyDocuments
})
```

Assert a new durable version fetches and applies mapped documents; the same version does not
fetch twice; a response is ignored if `targetState.sessionId` changes; and a failed request does
not mark the version applied, allowing retry.

- [ ] **Step 2: Run coordinator tests and verify RED**

Run: `cd /home/xckj/suyuan/frontend && node --test src/services/sessionDocumentResources.test.js`

Expected: FAIL because `refreshDurableDocumentResources` is not exported.

- [ ] **Step 3: Implement minimal coordinator logic**

Implement validation for `resource_durable === true`, a positive finite resource version, and a
session ID. Store applied and in-flight version metadata on `targetState`, set/clear
`lazyArtifacts.loadingOfficeDocuments`, map API resources, re-check the session ID before apply,
and log failures without throwing into the caller.

- [ ] **Step 4: Run coordinator tests and verify GREEN**

Run: `cd /home/xckj/suyuan/frontend && node --test src/services/sessionDocumentResources.test.js`

Expected: all mapper and coordinator tests PASS.

### Task 3: Connect complete events to unified resources

**Files:**
- Modify: `frontend/src/stores/reactStore.js`

- [ ] **Step 1: Import the API and coordinator**

Extend the session API import to include `getSessionOfficeDocuments`, and import
`refreshDurableDocumentResources` from the new service module.

- [ ] **Step 2: Allow document history updates on the routed target state**

Change `setOfficeDocumentHistory(documents)` to
`setOfficeDocumentHistory(documents, targetState = this.currentState)` and use `targetState`
throughout, preserving current callers.

- [ ] **Step 3: Trigger the asynchronous refresh from complete**

After processing legacy document fields, call the coordinator without awaiting it. Supply the
resolved event session ID, routed `targetState`, `getSessionOfficeDocuments`, and an apply callback
that invokes `setOfficeDocumentHistory(documents, targetState)` and updates the target state's
lazy artifact counts. Keep final-answer completion independent from refresh failures.

- [ ] **Step 4: Run focused regression tests**

Run: `cd /home/xckj/suyuan/frontend && node --test src/services/sessionDocumentResources.test.js`

Expected: PASS with zero failures.

- [ ] **Step 5: Run existing frontend Node tests**

Run: `cd /home/xckj/suyuan/frontend && node --test src/**/*.test.js src/**/*.test.mjs`

Expected: all discovered tests PASS.

### Task 4: Build and deploy

**Files:**
- Generated: `frontend/dist/**`

- [ ] **Step 1: Build the standalone frontend**

Run: `cd /home/xckj/suyuan/frontend && npm run build:standalone`

Expected: Vite exits with code 0 and writes `frontend/dist`.

- [ ] **Step 2: Verify the resource endpoint migration contract**

Run:

```bash
grep -R "resources?presentation_type=document" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/office-documents" /home/xckj/suyuan/frontend/dist/assets
! grep -R "/visualizations" /home/xckj/suyuan/frontend/dist/assets
```

Expected: the first command finds the unified endpoint; both legacy endpoint checks return no
matches.

- [ ] **Step 3: Reload Nginx**

Run: `docker exec suyuan-nginx nginx -s reload`

Expected: exit code 0 with a successful reload notice.

- [ ] **Step 4: Inspect the final diff and status**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only scoped source/test changes plus the pre-existing untracked
`NormCraftAI/` and generated ignored build output.
