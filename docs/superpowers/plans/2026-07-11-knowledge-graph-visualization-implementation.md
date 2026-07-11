# Knowledge Base G6 Graph Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild a full, knowledge-base-scoped interactive graph canvas with AntV G6, complete snapshot loading, evidence inspection, and in-place graph fact management.

**Architecture:** Add an atomic knowledge-base graph revision and a cursor-based snapshot API that transfers every selected entity and relation without the existing 200-item cap. The Vue knowledge-base graph tab collects one consistent snapshot, renders it through an API-independent G6 canvas component, and delegates evidence plus mutations to a separate detail panel using the existing fact APIs.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL, pytest, Vue 3, Pinia, AntV G6, Vite, Node test runner.

---

## File map

- `backend/app/knowledge_base/models.py`: persistent `graph_revision` on each knowledge base.
- `backend/app/knowledge_base/graph_revision.py`: one atomic revision bump function shared by ingestion and manual mutations.
- `backend/app/knowledge_base/graph_snapshot.py`: stable cursor encoding and snapshot page queries.
- `backend/app/api/knowledge_graph_routes.py`: snapshot and mention endpoints; revision bumps for manual mutations.
- `backend/app/knowledge_base/graph_repository.py`: revision bump inside extraction/removal/merge fact transactions.
- `backend/app/alembic/versions/add_knowledge_graph_revision.py`: idempotent schema migration.
- `frontend/src/api/knowledgeBase.js`: snapshot iteration and mention requests with abort signals.
- `frontend/src/stores/knowledgeBaseStore.js`: complete snapshot state, request generation, loading progress and cancellation.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphCanvas.vue`: independent G6 lifecycle and graph events.
- `frontend/src/components/management/knowledge-base/knowledgeGraphData.js`: pure graph normalization, colors, filters and degree calculation.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphToolbar.vue`: search, filters, labels, layout, fullscreen and progress.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphDetailPanel.vue`: evidence and fact mutation UI.
- `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`: orchestration only.

### Task 1: Add the atomic graph revision

**Files:**
- Create: `backend/app/knowledge_base/graph_revision.py`
- Create: `backend/app/alembic/versions/add_knowledge_graph_revision.py`
- Modify: `backend/app/knowledge_base/models.py`
- Modify: `backend/app/knowledge_base/graph_schemas.py`
- Modify: `backend/app/knowledge_base/graph_repository.py`
- Modify: `backend/app/knowledge_base/graph_build_service.py`
- Modify: `backend/app/api/knowledge_graph_routes.py`
- Test: `backend/tests/knowledge_base/test_graph_revision.py`

- [ ] **Step 1: Write failing revision tests**

Add SQLite-compatible tests proving an atomic bump returns the new value and that two sequential fact transactions produce revisions 1 and 2.

```python
@pytest.mark.asyncio
async def test_bump_graph_revision_is_monotonic(session_factory, knowledge_base):
    async with session_factory() as session, session.begin():
        assert await bump_graph_revision(session, knowledge_base.id) == 1
    async with session_factory() as session, session.begin():
        assert await bump_graph_revision(session, knowledge_base.id) == 2
```

- [ ] **Step 2: Run the focused test and verify RED**

Run `/root/miniconda3/envs/backend_py311/bin/python -m pytest backend/tests/knowledge_base/test_graph_revision.py -q`.

Expected: FAIL because `graph_revision` and `bump_graph_revision` do not exist.

- [ ] **Step 3: Add the model and migration**

Add `graph_revision = Column(BigInteger, nullable=False, default=0, server_default="0")` to `KnowledgeBase`. The migration must use `ADD COLUMN IF NOT EXISTS`, backfill null values, set default/not-null, and be safe when executed repeatedly.

- [ ] **Step 4: Implement the atomic bump**

Use a single SQL update in the caller's transaction:

```python
async def bump_graph_revision(session, kb_id: str) -> int:
    statement = (
        update(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id)
        .values(graph_revision=KnowledgeBase.graph_revision + 1,
                graph_updated_at=datetime.utcnow())
        .returning(KnowledgeBase.graph_revision)
    )
    revision = await session.scalar(statement)
    if revision is None:
        raise ValueError(f"Knowledge base not found: {kb_id}")
    return int(revision)
```

- [ ] **Step 5: Wire bumps into every fact mutation transaction**

Call the helper once per transaction after successful graph changes in extraction upsert, chunk contribution removal, entity merge, manual entity/relation create-update-archive and `GraphBuildService.reset_graph`. Extend `GraphEntityUpdate` with optional `entity_type`; when name, canonical name or type changes, revalidate the `(kb_id, entity_type, normalized_name)` identity and return HTTP 409 on conflict. Do not bump for read operations, build-task status changes or Outbox retries.

- [ ] **Step 6: Run revision and graph repository tests**

Run the focused test plus `backend/tests/knowledge_base/test_graph_repository.py`. Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Commit only the revision model, migration, helper, mutation wiring and tests with message `feat: 增加知识库图谱版本号`.

### Task 2: Implement a complete consistent snapshot API

**Files:**
- Create: `backend/app/knowledge_base/graph_snapshot.py`
- Modify: `backend/app/knowledge_base/graph_schemas.py`
- Modify: `backend/app/api/knowledge_graph_routes.py`
- Test: `backend/tests/knowledge_base/test_graph_snapshot.py`
- Test: `backend/tests/api/test_knowledge_graph_snapshot_routes.py`

- [ ] **Step 1: Write failing cursor and pagination tests**

Create more than 200 entities, including an isolated node, a self-loop and parallel relations. Iterate snapshot pages and assert every requested entity and valid relation is returned exactly once.

```python
while True:
    page = await repository.page(kb_id, statuses, cursor, page_size=50,
                                 expected_revision=revision)
    entities.extend(page.entities)
    relations.extend(page.relations)
    if page.next_cursor is None:
        break
    cursor = page.next_cursor
assert len({item.id for item in entities}) == 205
```

- [ ] **Step 2: Verify RED**

Run both new test modules. Expected: FAIL because the repository and `/snapshot` route do not exist.

- [ ] **Step 3: Implement opaque cursor helpers**

Encode URL-safe base64 JSON containing `phase`, `last_id` and `revision`; decode with strict validation and return HTTP 400 for malformed cursors. Pages traverse entities ordered by ID, then relations ordered by ID. A relation is included only when its own status and both endpoint statuses are selected.

- [ ] **Step 4: Implement snapshot paging**

Define a `GraphSnapshotPage` result containing entities, relations, cursor, revision and totals. `page_size` controls the combined records per response and is bounded from 100 to 2000, but iteration has no total record limit.

- [ ] **Step 5: Enforce revision consistency**

The first page reads the current `KnowledgeBase.graph_revision`. Every later page compares the cursor revision and explicit `snapshot_version` with the current value before querying; mismatch raises a domain error mapped to HTTP 409 with detail code `graph_snapshot_changed`.

- [ ] **Step 6: Add the route**

Add:

```python
@router.get("/snapshot", response_model=GraphSnapshotResponse)
async def get_graph_snapshot(kb_id: str,
                             review_statuses: list[ReviewStatus] = Query(
                                 default=["candidate", "confirmed", "published"]),
                             cursor: str | None = None,
                             snapshot_version: int | None = None,
                             page_size: int = Query(1000, ge=100, le=2000),
                             db: AsyncSession = Depends(get_db),
                             user_id: str | None = Header(default=None, alias="X-User-Id")):
    await _readable_kb(db, kb_id, user_id)
    return await GraphSnapshotRepository(db).page(
        kb_id=kb_id,
        statuses=set(review_statuses),
        cursor=cursor,
        expected_revision=snapshot_version,
        page_size=page_size,
    )
```

- [ ] **Step 7: Test isolation, statuses and 409 behavior**

Assert a user cannot read an unauthorized KB, a cursor from KB A cannot read KB B, default statuses exclude rejected/archived/merged, history mode includes them, and a revision bump between pages produces 409.

- [ ] **Step 8: Commit Task 2**

Commit with message `feat: 增加知识库全量图谱快照接口`.

### Task 3: Add entity and relation evidence endpoints

**Files:**
- Modify: `backend/app/knowledge_base/graph_schemas.py`
- Modify: `backend/app/api/knowledge_graph_routes.py`
- Test: `backend/tests/api/test_knowledge_graph_mentions_routes.py`

- [ ] **Step 1: Write failing mention response tests**

For both entity and relation mentions, assert the response contains `document_id`, `filename`, `document_content_generation`, `chunk_id`, `chunk_content_generation`, `chunk_index`, `content`, `evidence_text`, offsets, page, confidence, extractor and `stale`.

- [ ] **Step 2: Verify RED**

Run `/root/miniconda3/envs/backend_py311/bin/python -m pytest backend/tests/api/test_knowledge_graph_mentions_routes.py -q`. Expected: 404 because mention routes do not exist.

- [ ] **Step 3: Implement shared mention serialization**

Join mention to `Document` and `KnowledgeChunk`, ordered by document and chunk index. Set `stale` when document and chunk content generations differ. Never substitute current document text for a stale mention.

- [ ] **Step 4: Implement both routes with ownership checks**

Add `/entities/{entity_id}/mentions` and `/relations/{relation_id}/mentions`; return 404 before querying mentions when the record does not belong to `kb_id`. Use readable-KB permission for evidence viewing.

- [ ] **Step 5: Run tests and commit**

Expected: mention tests PASS. Commit with message `feat: 增加图谱事实证据接口`.

### Task 4: Add complete snapshot loading to the frontend API and store

**Files:**
- Modify: `frontend/src/api/knowledgeBase.js`
- Modify: `frontend/src/stores/knowledgeBaseStore.js`
- Create: `frontend/src/stores/knowledgeGraphSnapshot.js`
- Test: `frontend/src/stores/knowledgeGraphSnapshot.test.mjs`

- [ ] **Step 1: Write failing pure-loader tests**

Test that the loader follows all cursors, appends entities and relations, reports totals, passes the first snapshot version to later pages, discards partial results on failure, retries from page one once on `graph_snapshot_changed`, and honors `AbortSignal`.

- [ ] **Step 2: Verify RED with Node**

Run `node --test frontend/src/stores/knowledgeGraphSnapshot.test.mjs`. Expected: module-not-found failure.

- [ ] **Step 3: Implement the pure snapshot collector**

Export:

```javascript
export async function collectGraphSnapshot(fetchPage, { statuses, signal, onProgress }) {
  // collect every page; one full restart on graph_snapshot_changed
  // return only after next_cursor is null
  return { snapshotVersion, entities, relations, entityTotal, relationTotal }
}
```

- [ ] **Step 4: Add API methods with AbortSignal**

Add `getKnowledgeGraphSnapshotPage`, `getKnowledgeGraphEntityMentions` and `getKnowledgeGraphRelationMentions`. Extend the shared request wrapper only as needed to pass `signal` to `fetch`.

- [ ] **Step 5: Replace capped store loading**

`loadGraph(kbId, { includeHistory })` must create a request generation and `AbortController`, load status plus the complete snapshot, update progress, and publish arrays only after completion. A late or aborted request must not mutate current store state.

- [ ] **Step 6: Run tests and commit**

Run the Node test and existing knowledge-base contract tests. Commit with message `feat: 前端加载完整知识库图谱快照`.

### Task 5: Build pure G6 graph data transformation

**Files:**
- Create: `frontend/src/components/management/knowledge-base/knowledgeGraphData.js`
- Create: `frontend/src/components/management/knowledge-base/knowledgeGraphData.test.mjs`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Write failing normalization tests**

Cover isolated nodes, self-loops, parallel edges, degree counts, deterministic type colors, active type filtering and search matches. Preserve original entity/relation objects under `data.original`.

- [ ] **Step 2: Verify RED**

Run `node --test frontend/src/components/management/knowledge-base/knowledgeGraphData.test.mjs`. Expected: module-not-found failure.

- [ ] **Step 3: Implement pure transformations**

Export `toG6Data`, `stableTypeColor`, `filterGraphData`, `findEntityMatches` and `neighborIds`. Generate unique edge IDs from relation IDs; never collapse self-loops or multiple relations between the same endpoints.

- [ ] **Step 4: Add AntV G6 dependency**

Run `npm install @antv/g6@^5` in `frontend`, preserving the project's npm lockfile. Do not copy Yuxi's Ant Design, Milvus or graph index dependencies.

- [ ] **Step 5: Run pure tests and commit**

Commit with message `feat: 增加 G6 图谱数据转换`.

### Task 6: Implement the independent G6 canvas and toolbar

**Files:**
- Create: `frontend/src/components/management/knowledge-base/KnowledgeGraphCanvas.vue`
- Create: `frontend/src/components/management/knowledge-base/KnowledgeGraphToolbar.vue`
- Create: `frontend/src/components/management/knowledge-base/knowledge-graph-canvas-contract.test.mjs`

- [ ] **Step 1: Write failing component contract tests**

Assert the canvas imports `Graph` from `@antv/g6`, accepts `nodes`, `edges`, `showRelationLabels`, and emits `node-click`, `relation-click`, `canvas-click`, `ready`. Assert toolbar emits search, type-filter, label, fit, layout, fullscreen, history and refresh events.

- [ ] **Step 2: Verify RED**

Run `node --test frontend/src/components/management/knowledge-base/knowledge-graph-canvas-contract.test.mjs`. Expected: missing component failure.

- [ ] **Step 3: Implement G6 lifecycle**

Create one graph instance in `onMounted`, update data in watchers, destroy it in `onUnmounted`, and use `ResizeObserver`. Configure force layout, circle nodes, curved directed edges, self-loop style, parallel edge offset, drag element, drag canvas, zoom canvas, hover activate and click select.

- [ ] **Step 4: Implement focus and public controls**

Expose `fitView()`, `relayout()`, `focusNode(id)` and `clearFocus()`. Node click highlights one-hop neighbors; canvas click clears selection. At low zoom hide ordinary node and relation labels without removing graph elements.

- [ ] **Step 5: Implement toolbar UI**

Render search, multi-select type controls, label/history toggles, fit, layout, fullscreen and refresh actions. Show loaded/total entity and relation counts plus loading/layout status.

- [ ] **Step 6: Run contract and production build**

Run the contract test followed by `npm run build`. Expected: PASS and Vite build exit 0.

- [ ] **Step 7: Commit Task 6**

Commit with message `feat: 增加知识库 G6 图谱画布`.

### Task 7: Implement evidence and in-canvas fact management

**Files:**
- Create: `frontend/src/components/management/knowledge-base/KnowledgeGraphDetailPanel.vue`
- Create: `frontend/src/components/management/knowledge-base/knowledge-graph-detail-contract.test.mjs`
- Modify: `frontend/src/api/knowledgeBase.js`

- [ ] **Step 1: Write failing detail panel contracts**

Assert entity and relation views show attributes, review status and evidence; stale evidence disables document jump. Assert confirm, reject, edit, merge and delete emit explicit events and destructive actions require confirmation state.

- [ ] **Step 2: Verify RED**

Run the detail contract test. Expected: missing component failure.

- [ ] **Step 3: Implement read and evidence states**

On selection change, abort the prior mention request, show loading/error/empty states, and render document, chunk index, evidence text, confidence and stale warning. Emit `open-document-chunk` only for non-stale evidence.

- [ ] **Step 4: Implement mutation forms**

Entity editing covers name, canonical name, aliases, description, type, attributes and review status permitted by the existing schema. Relation editing covers type, description, attributes and review status. Use explicit submit/cancel states and disable duplicate requests.

- [ ] **Step 5: Implement merge target mode and confirmations**

Emit `begin-merge` with source entity; the tab routes the next canvas entity click to target selection. Display source/target before emitting `confirm-merge`. Reject, archive/delete and merge require a second click or modal confirmation.

- [ ] **Step 6: Run tests, build and commit**

Commit with message `feat: 增加图谱证据与可视化管理面板`.

### Task 8: Integrate the workbench into KnowledgeGraphTab

**Files:**
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphTab.vue`
- Modify: `frontend/src/components/management/knowledge-base/KnowledgeGraphReview.vue`
- Modify: `frontend/src/stores/knowledgeBaseStore.js`
- Create: `frontend/src/components/management/knowledge-base/knowledge-graph-tab-visualization.test.mjs`

- [ ] **Step 1: Write failing integration contracts**

Assert `KnowledgeGraphTab` renders toolbar, canvas, detail panel, status and graph chat; passes current `kbId`; never references the deleted `CognitiveMapPanel`; waits for complete snapshot before setting canvas data; and reloads after graph build terminal status or successful mutation.

- [ ] **Step 2: Verify RED**

Run the new integration test. Expected: missing imports and orchestration failure.

- [ ] **Step 3: Replace the 30-line relationship summary**

Remove the text-only `graphLinks.slice(0, 30)` list and compose the new workbench. Keep the existing status and Graph Agent chat. The existing review list may remain as a secondary compact view but must use the same complete snapshot arrays.

- [ ] **Step 4: Wire filters, selection and canvas controls**

Compute visible G6 data from full arrays and toolbar filters. Route search matches to `focusNode`; route canvas selection to detail; preserve coordinates for local mutations; reset all selection and merge state when `kbId` changes.

- [ ] **Step 5: Wire mutations and document jumps**

Use existing entity/relation update/delete/merge APIs, then apply returned facts locally and trigger a background snapshot validation. Add an explicit `open-document-chunk` event to `KnowledgeGraphTab` and `KnowledgeBasePanel`; its payload is `{ documentId, chunkId }`, and the panel loads that document's chunks then scrolls/selects the matching chunk.

- [ ] **Step 6: Wire build completion refresh**

Observe graph build task transitions. On `queued/running` to any terminal state, call one complete snapshot reload for the current `kbId`; guard against late results and repeated terminal polling.

- [ ] **Step 7: Run frontend tests and build**

Run all knowledge graph Node contract tests and `npm run build`. Expected: PASS.

- [ ] **Step 8: Commit Task 8**

Commit with message `feat: 集成知识库图谱可视化工作台`.

### Task 9: End-to-end regression and migration verification

**Files:**
- Verify all files above.

- [ ] **Step 1: Run backend graph suites**

Run:

```bash
/root/miniconda3/envs/backend_py311/bin/python -m pytest \
  backend/tests/knowledge_base \
  backend/tests/api/test_knowledge_graph_snapshot_routes.py \
  backend/tests/api/test_knowledge_graph_mentions_routes.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run frontend graph suites**

Run all `knowledgeGraph*.test.mjs` and `knowledge-graph-*.test.mjs` files with `node --test`. Expected: zero failures.

- [ ] **Step 3: Run production build**

Run `npm run build` in `frontend`. Expected: Vite build exit 0.

- [ ] **Step 4: Run idempotent migration twice**

Execute the new migration twice using `/root/miniconda3/envs/backend_py311/bin/python -m app.alembic.versions.add_knowledge_graph_revision` from `backend`. Expected: both runs exit 0 and `knowledge_bases.graph_revision` remains non-null.

- [ ] **Step 5: Perform a real-data smoke check**

For knowledge base `b31d82d1-59ca-451c-a46c-d41a92a0d8e6`, iterate the snapshot API, compare returned totals with database counts for selected statuses, open one entity and one relation evidence response, then verify the UI renders the same totals without a 200-record cap.

- [ ] **Step 6: Review diff and final commit**

Run `git diff --check`, ensure no independent cognitive-map route or storage mechanism was introduced, and commit any verification-only corrections separately.
