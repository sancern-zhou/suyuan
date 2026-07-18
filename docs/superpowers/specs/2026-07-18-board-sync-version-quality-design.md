# Board Sync, Version History, and Visual Quality Design

## Goal

Make board-mode editing reliable and auditable by guaranteeing that an Agent request uses the user's latest manual draw.io XML, moving version history to a server-side immutable model, and requiring every Agent-generated XML candidate to pass deterministic validation plus screenshot-based visual review before it becomes the current board.

This design extends the existing board-mode XML quality gate and replaces the current frontend-only version history as the authoritative history. It preserves the existing rule that the visible current XML is authoritative, but moves authority at request boundaries to a committed server version.

## Confirmed Product Decisions

- If the editor cannot synchronously export the latest XML before send, block the send. Never fall back to stale XML.
- Create an immutable version after every successful Agent generation or modification.
- Before an Agent request, create a `manual` version when the synchronized XML differs from the current committed version.
- Autosave updates a draft but does not create history versions.
- Restoring history creates a new `restore` version and never rewrites old history.
- Retain all versions, candidate XML, screenshots, and quality reports. No automatic retention policy is introduced in this phase.
- During an Agent run, the board editor is read-only.
- Hard validation failures prevent delivery. Non-fatal visual warnings may be delivered after at most two autonomous repair rounds, with a visible warning.
- A rendering failure blocks delivery because screenshot review is part of the quality contract.

## Scope

Included:

- a strict frontend XML synchronization handshake before send;
- server-side board, draft, and immutable version state;
- optimistic concurrency using a board revision;
- lazy history loading and history restoration for old conversations;
- migration of legacy `metadata.drawio_board` state;
- deterministic XML validation and visual diagnostics;
- server-side draw.io rendering to screenshot;
- multimodal Agent review with at most two repair rounds;
- candidate, accepted, and rejected version lifecycle;
- explicit frontend progress and error states;
- focused unit, integration, rendering, and end-to-end tests.

Excluded:

- real-time collaborative editing or automatic merge of concurrent edits;
- event-sourced replay of every individual cell operation;
- automatic deletion or archival of versions;
- multiple active boards in one board-mode conversation;
- changing the existing single-page draw.io XML contract;
- a new general-purpose graph layout engine.

## Architecture

The first release keeps one active board per board-mode conversation. Four components own distinct responsibilities:

1. `DrawioBoardBridge` owns communication with the embedded editor and returns a Promise for the latest exported XML.
2. `BoardVersionService` owns drafts, immutable versions, revision checks, history queries, and restore operations.
3. `DrawioQualityService` owns deterministic validation, screenshot rendering, and machine-readable quality diagnostics.
4. The Agent runtime owns the candidate review loop, retry budget, screenshot injection, and completion guard.

The frontend Store remains the reactive view state, but it is not the durable source of version history. Conversation metadata becomes a lightweight index containing `board_id`, `current_version_id`, and `revision` rather than full XML.

## Data Model

### Board

```text
id                    string/uuid, primary key
session_id            string, unique for the active board
title                 string
current_version_id    nullable version reference
revision              integer, monotonically increasing for accepted versions
draft_xml_ref         nullable artifact reference
draft_sha256          nullable string
draft_revision        integer, monotonically increasing for draft saves
created_at            timestamp
updated_at            timestamp
```

`revision` changes only when an accepted manual, Agent, or restore version becomes current. Draft saves change `draft_revision`, not `revision`.

### BoardVersion

```text
id                         string/uuid, primary key
board_id                   board reference
version_number             integer, monotonically increasing per board
parent_version_id          nullable version reference
restored_from_version_id   nullable version reference
source                     agent | manual | restore | legacy_import
lifecycle_status           candidate | accepted | rejected
xml_ref                    immutable artifact reference
xml_sha256                 string
screenshot_ref             nullable immutable artifact reference
quality_status             pending | passed | warning | failed
quality_report             structured JSON
agent_run_id               nullable string
summary                    nullable string
created_at                 timestamp
accepted_at                nullable timestamp
```

Every candidate is retained. Only an `accepted` version can become `Board.current_version_id`. The history UI shows accepted versions by default and groups candidate/rejected quality attempts under the related Agent run.

Version numbers are allocated by the server. Frontend-generated version numbers and the current tool-level constant `version=1` no longer determine history order.

## Strict XML Synchronization

### Bridge contract

`DrawioBoardBridge.exportCurrentXml()` provides a single-flight request:

```text
Promise<{ xml, sha256Candidate, exportedAt }>
```

The bridge must:

- require the iframe to be initialized;
- allow only one XML export request at a time;
- accept messages only when `event.source` is the active iframe window;
- accept messages only from the configured diagrams.net origin;
- accept only the expected XML export/save response shape;
- reject malformed or empty XML;
- time out after five seconds;
- clean up the pending resolver on success, failure, timeout, or component unmount.

The diagrams.net protocol does not need to echo an application request ID if the bridge enforces single-flight operation and matches the expected response type. Internal request IDs should still be logged and attached to frontend diagnostics.

### Send transaction

For an existing board, sending follows this strict order:

```text
1. Set UI state to syncing.
2. Await exportCurrentXml().
3. Update the Store with the returned XML.
4. Compute/confirm its SHA-256.
5. Compare it with the current accepted version hash.
6. If different, commit a manual version using base_revision.
7. Await the committed version_id and revision.
8. Set the editor read-only.
9. Send the Agent request with board_id, version_id, revision, and selected_cells.
```

Any failure in steps 2 through 7 blocks the Agent request. The query and attachments remain in the input so the user can retry.

The first request that creates a board has no iframe or current XML, so it skips synchronization and allows the Agent to create the first candidate.

### Concurrent edits

Version commits include `base_revision`. If it differs from `Board.revision`, the service returns HTTP 409 with `board_version_conflict`. The frontend blocks send and asks the user to load the latest version. There is no silent overwrite or automatic XML merge.

The editor remains read-only from successful pre-send commit until the Agent run completes, fails, is cancelled, or times out. Every terminal path must release read-only state.

## API Contracts

```text
PUT  /api/boards/{board_id}/draft
POST /api/boards/{board_id}/versions/manual
GET  /api/boards/{board_id}/versions
GET  /api/boards/{board_id}/versions/{version_id}
POST /api/boards/{board_id}/restore
```

### Draft save

Draft saves are debounced and update `draft_xml_ref`, `draft_sha256`, and `draft_revision`. They do not create `BoardVersion` records and do not advance `Board.revision`.

### Manual version commit

```json
{
  "base_revision": 11,
  "xml": "<mxfile>...</mxfile>",
  "xml_sha256": "optional-client-hash"
}
```

The server recalculates the hash. If it equals the current accepted version hash, the endpoint returns the current version without creating a duplicate. Otherwise it creates and accepts a `manual` version atomically and increments `Board.revision`.

### Restore

```json
{
  "base_revision": 12,
  "version_id": "historical-version-id"
}
```

Restore creates a new accepted version with `source=restore`, `parent_version_id` set to the previous current version, and `restored_from_version_id` set to the selected historical version. Artifact blobs may be reused because they are immutable.

### Agent request

For an existing board, `board_context` becomes a compact reference:

```json
{
  "board_id": "board-123",
  "version_id": "version-12",
  "revision": 12,
  "selected_cells": []
}
```

The backend verifies that the version belongs to the board and that the revision is current, then loads XML from the immutable artifact. Client-supplied full XML is retained only as a temporary backward-compatibility path during migration.

## Version History and Session Restore

Session restore returns the lightweight board index and a `has_board_versions` indicator. Version history is loaded lazily through the board API.

The history UI shows:

- version number and title;
- source label: AI generation, manual edit, restore, or legacy import;
- creation time and summary;
- quality status badge;
- screenshot thumbnail when available;
- current-version indicator;
- an expandable list of candidate/rejected quality attempts from the same Agent run.

Selecting a version loads its metadata and preview. Restoring requires confirmation and creates a new accepted version. It never moves the current pointer directly to an old immutable row.

## Legacy Migration

Migration is lazy and idempotent:

```text
1. Restore a legacy session.
2. Detect metadata.drawio_board.current_xml without a board_id.
3. Acquire a per-session migration lock/transaction.
4. Create Board if absent.
5. Store XML as an immutable artifact.
6. Create the first accepted source=legacy_import version.
7. Set current_version_id and revision=1.
8. Write the lightweight board index back to conversation metadata.
```

A uniqueness constraint on `Board.session_id` and an idempotency check prevent duplicate migration. Legacy fields remain readable for one compatibility period and are not deleted by this implementation.

## Quality Pipeline

### Candidate lifecycle

`create_drawio_board` produces a candidate, not an immediately current version:

```text
candidate XML
  -> immutable candidate artifact and candidate version row
  -> deterministic hard validation
  -> server-side screenshot rendering
  -> deterministic visual diagnostics
  -> multimodal Agent review
  -> accept candidate or generate a repaired candidate
```

Every candidate receives a `BoardVersion` row with `lifecycle_status=candidate` before validation, so failed attempts remain auditable. A candidate with a hard failure becomes `rejected` and cannot be accepted. When the Agent accepts a candidate, the version service atomically marks it `accepted`, advances `Board.current_version_id`, increments `Board.revision`, and rejects any older pending candidate in the same run.

### Hard validation

The existing draw.io quality gate remains the base. Blocking checks include:

- XML parseability and the supported mxfile structure;
- unique and non-empty cell IDs;
- valid parent, source, and target references;
- finite, positive vertex geometry;
- valid relative edge geometry;
- nodes completely outside the canvas;
- material full-node overlap that makes either node unusable;
- empty required labels or deterministic label overflow beyond defined limits.

Hard failure returns a structured error and does not update the current board.

### Rendering

`DrawioQualityService` uses a pinned, self-hosted diagrams.net build with headless Chromium. Frontend and backend must use the same pinned editor build so screenshot output reflects what users see. The renderer runs with bounded time, memory, canvas dimensions, and network access. The screenshot and renderer metadata are stored as immutable artifacts.

A render attempt has a 20-second timeout and is retried once. If both attempts fail, the service sets `quality_status=failed`, rejects the candidate, and prevents delivery.

### Quality report

The report has stable issue codes and serializable metrics:

```json
{
  "status": "passed | warning | failed",
  "errors": [],
  "warnings": [],
  "metrics": {
    "vertex_count": 0,
    "edge_count": 0,
    "overlap_count": 0,
    "edge_crossing_count": 0,
    "orphan_count": 0,
    "canvas_utilization": 0.0
  },
  "renderer": {
    "version": "pinned-build-id",
    "width": 0,
    "height": 0
  }
}
```

Diagnostics cover node spacing and overlap, text clipping and small fonts, edge crossings and edges through nodes, contrast, alignment consistency, canvas utilization, isolated nodes, and overall screenshot readability.

### Agent review loop

After candidate creation, the runtime injects the screenshot and quality report into the next model iteration. Completion is blocked while a candidate is awaiting review.

The Agent must either:

- explicitly accept the candidate with `accept_drawio_board_candidate(candidate_version_id, expected_board_revision)`; or
- call `create_drawio_board` again using the candidate XML as authoritative context.

`accept_drawio_board_candidate` is a board-mode-only tool backed by `BoardVersionService`. It rejects candidates from another board or run, candidates that failed hard validation, and stale `expected_board_revision` values. This explicit action keeps acceptance out of prompt-only conventions and gives the completion guard an observable terminal event.

The runtime, not the prompt, counts repair rounds. The initial candidate may be followed by at most two autonomous repaired candidates. After the budget is exhausted:

- remaining hard errors prevent acceptance and fail the run without changing the current board;
- non-fatal warnings may be accepted, but the accepted version retains `quality_status=warning` and the final user message summarizes the remaining warning.

All candidate attempts are retained and grouped by `agent_run_id`.

## Frontend State and UX

The frontend uses explicit states:

```text
editing
syncing
committing_manual_version
agent_running_readonly
validating
rendering
agent_reviewing
loading_final_version
editing
```

Required behavior:

- the send button shows `正在同步画板` during the synchronization barrier;
- synchronization and commit errors preserve the draft query and attachments;
- a read-only overlay prevents editor changes during the Agent run;
- progress text distinguishes validation, rendering, and Agent review;
- final accepted XML is loaded before the UI reports the board as ready;
- a failed final XML fetch offers a retry action using the retained version reference;
- every terminal path releases read-only state.

## Error Contract

Stable error codes:

```text
board_editor_not_ready
board_sync_timeout
board_sync_invalid_xml
board_manual_commit_failed
board_version_conflict
board_render_failed
board_quality_failed
board_version_load_failed
```

Rules:

- synchronization or manual commit failure blocks send;
- conflict blocks send and asks the user to load the latest accepted version;
- cancellation, Agent failure, or timeout marks pending candidates rejected and preserves the previous current version;
- exhausted hard-quality failures do not commit a current version;
- exhausted non-fatal warnings may commit with a visible warning;
- render failure blocks delivery;
- final-version load failure does not delete or roll back the server version and exposes retry.

## Testing

### Frontend unit tests

- iframe origin and source validation;
- single-flight XML export success, malformed response, timeout, and unmount cleanup;
- no Agent request after any synchronization or manual commit failure;
- enforced ordering: sync, manual commit, then Agent request;
- query and attachment preservation after blocked send;
- read-only state during the run and release on every terminal event;
- version history loading, candidate expansion, and restore confirmation.

### Backend unit tests

- board/version repository invariants and server-assigned version numbers;
- optimistic revision conflict returns 409;
- identical hash does not create a duplicate manual version;
- restore creates a new immutable version and leaves history untouched;
- valid candidate lifecycle transitions and forbidden transitions;
- deterministic quality issue codes and metrics;
- render failure rejects a candidate;
- legacy migration is idempotent.

### Integration tests

- first Agent request creates a board and accepted version through the quality loop;
- an immediate send after manual editing uses the synchronized latest XML;
- an Agent can inspect a screenshot and make up to two repairs;
- cancellation, hard-quality failure, and render failure preserve the previous accepted version;
- restored conversations expose all accepted versions and quality records;
- concurrent tabs produce an explicit revision conflict.

### Rendering and end-to-end tests

- use the pinned self-hosted diagrams.net build and Chromium;
- maintain representative architecture, process, data-flow, decision-tree, layered-system, timeline, and comparison-matrix fixtures;
- compare screenshots with bounded pixel tolerance;
- verify frontend and backend rendering equivalence;
- enforce time and memory limits for large-board synchronization and rendering.

Tests and migrations run in the project environment:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest ...
```

Frontend tests continue to use the repository's Node/Vite commands.

## Rollout Order

1. Introduce board/version persistence and legacy migration behind the existing response contract.
2. Add the strict frontend synchronization barrier and compact Agent board reference.
3. Switch history restore to the server version APIs.
4. Add deterministic candidate lifecycle and validation.
5. Add the pinned renderer, screenshot artifacts, and Agent review completion guard.
6. Enable the full quality gate after focused integration and rendering tests pass.

Each stage keeps the prior accepted board readable. The quality stage must not be enabled in production until renderer health checks and failure handling are operational.

## Success Criteria

- A manual edit followed by immediate send always reaches the Agent as the committed latest XML.
- Any synchronization failure prevents the Agent request.
- All accepted historical versions remain queryable after conversation restore, including source, screenshot, and quality report.
- Restore creates a new version and never mutates history.
- Concurrent commits never silently overwrite one another.
- No Agent-generated XML becomes current without hard validation and successful screenshot rendering.
- The runtime enforces visual review and the two-repair budget independently of prompt compliance.
- Cancellation, timeout, hard failure, and rendering failure preserve the previous accepted version.
