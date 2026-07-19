# Draw.io Deferred Agent Visual Review Design

## Goal

Show an Agent-generated draw.io board in the frontend as soon as its XML has passed deterministic validation and been persisted, while moving screenshot rendering into a separate Agent step. The Agent should normally inspect the resulting screenshot before accepting or revising the candidate, but this is a workflow convention rather than a backend-enforced quality gate.

This design supersedes the synchronous rendering and mandatory screenshot gate described in `2026-07-18-board-sync-version-quality-design.md`. It does not change the existing manual-edit synchronization, immutable version history, or optimistic-concurrency design.

## Confirmed Product Decisions

- `create_drawio_board` must not wait for Playwright or PNG generation.
- A valid candidate XML is returned to the frontend immediately and becomes the visible preview.
- Screenshot rendering is performed by a separate board-mode tool after candidate creation.
- The screenshot is returned to the Agent as a multimodal attachment for visual inspection.
- Prompts and tool descriptions direct the Agent to render, inspect, revise when needed, and then accept.
- The backend does not forbid acceptance merely because screenshot rendering is pending, failed, or absent.
- Screenshot failure does not remove or hide an otherwise valid candidate XML.
- Candidate and accepted lifecycle semantics remain distinct; previewing a candidate does not silently mark it accepted.
- During an Agent run, the board remains read-only, including while a candidate preview is visible.

## Scope

Included:

- splitting candidate creation from screenshot rendering;
- immediate candidate preview in the frontend;
- a dedicated idempotent screenshot-rendering tool;
- persistence of screenshot status, reference, renderer metadata, and errors;
- multimodal delivery of a completed screenshot to the Agent;
- prompt-level guidance for the normal visual-review flow;
- preservation of Agent autonomy when accepting or revising a candidate;
- focused backend, runtime, and frontend tests.

Excluded:

- Celery or another durable screenshot job queue;
- frontend screenshot polling or completion notifications;
- self-hosting diagrams.net or browser pooling;
- making screenshots visible as ordinary chat attachments before the Agent requests rendering;
- changing manual board edits or version-history restoration;
- a mandatory server-side visual-review completion guard.

## Architecture

The existing synchronous operation is separated into two explicit tools:

```text
create_drawio_board
  -> normalize and validate XML
  -> run deterministic structural diagnostics
  -> persist candidate with render_status=pending
  -> return candidate XML reference immediately
  -> frontend previews candidate

render_drawio_board_candidate
  -> load the persisted candidate XML
  -> render PNG through DrawioQualityService
  -> persist screenshot result
  -> return screenshot as a multimodal attachment
  -> Agent visually inspects and chooses accept or edit
```

This is deferred rendering, not a detached background job. The first tool result is emitted over the existing SSE stream before the Agent enters its next planning iteration. Consequently the frontend can display the XML while the later screenshot tool blocks only the continuing Agent run.

## Candidate Creation

`create_drawio_board` retains XML normalization and deterministic checks that do not require a browser. Invalid XML, duplicate IDs, missing endpoints, invalid geometry, and other deterministic structural errors continue to return a structured failure before persistence.

For valid XML, the tool creates a candidate with:

```json
{
  "lifecycle_status": "candidate",
  "quality_status": "pending",
  "render_status": "pending",
  "requires_visual_review": true,
  "preview_candidate": true,
  "candidate_version_id": "candidate-id",
  "xml_ref": {
    "kind": "drawio_board_xml",
    "read_url": "/api/file/..."
  }
}
```

`requires_visual_review` is an instruction and UI state, not an acceptance prohibition. The tool does not create a screenshot attachment and does not instantiate Playwright.

The deterministic report may be stored separately from the eventual renderer result. `quality_status=pending` means visual review has not been completed; it does not mean the XML is invalid.

## Deferred Screenshot Tool

Add the board-mode-only tool:

```text
render_drawio_board_candidate(candidate_version_id)
```

The tool must:

1. Resolve the candidate through the current session and board context.
2. Reject access to candidates belonging to another board or session.
3. Read XML only from the persisted immutable candidate artifact.
4. Return an existing successful screenshot immediately when one already exists.
5. Otherwise invoke `DrawioQualityService` and persist the result.
6. Return the PNG as a multimodal attachment so it enters the next Agent iteration.

Successful output includes:

```json
{
  "render_status": "completed",
  "quality_status": "passed | warning",
  "quality_report": {},
  "screenshot_ref": {},
  "candidate_version_id": "candidate-id",
  "requires_visual_review": true
}
```

Rendering failure returns a structured, retryable result and persists:

```json
{
  "render_status": "failed",
  "quality_status": "failed",
  "render_error": "...",
  "candidate_version_id": "candidate-id"
}
```

Failure does not reject or delete the candidate. A later call may retry. Rendering remains idempotent after success.

## Agent Workflow and Autonomy

The board prompt and tool descriptions describe the normal flow:

1. Call `create_drawio_board` to create or edit a candidate.
2. Call `render_drawio_board_candidate` for that candidate.
3. Inspect the returned screenshot and deterministic report.
4. If the result is satisfactory, call `accept_drawio_board_candidate`.
5. If it is unsatisfactory, edit the candidate and render the replacement.

This flow is guidance, not a hard state-machine gate. The following enforcement is intentionally removed or not introduced:

- acceptance does not require `screenshot_ref`;
- acceptance does not require `quality_status` to be `passed` or `warning`;
- screenshot failure does not automatically reject a candidate;
- completion is not blocked solely because screenshot rendering was skipped or failed.

Existing authorization, board ownership, candidate identity, Agent-run identity, and optimistic-revision checks remain enforced. Agent autonomy applies only to the visual-quality decision, not to data integrity or access control.

The runtime should expose render status in board context and provide concise observations such as:

- `候选画板已显示，建议调用 render_drawio_board_candidate 完成视觉检查。`
- `截图渲染失败；可以重试、继续修改，或根据当前上下文自主决定是否接受。`

## Frontend Preview Behavior

When a successful draw.io result contains `preview_candidate=true`, the frontend must:

- load XML from the inline payload or `xml_ref`;
- set it as the visible board XML immediately;
- set the active board and candidate identifiers;
- retain `lifecycle_status=candidate` and `quality_status=pending`;
- avoid adding it to accepted history as the current committed version;
- show a non-blocking status such as `Agent 正在进行视觉检查`;
- keep the editor read-only until the Agent run reaches a terminal state.

When the candidate is accepted, the existing accepted result promotes the same XML into committed history and clears the pending preview state. When a replacement candidate is generated, the frontend replaces the preview only if its revision and run ordering are current.

A render failure updates status messaging but leaves the candidate XML visible. The screenshot is supporting evidence for the Agent and version record; it is not required for draw.io rendering in the frontend.

## Persistence

Add or consistently store the following candidate metadata:

```text
render_status       pending | rendering | completed | failed
screenshot_ref      nullable artifact reference
render_error        nullable structured/string error
quality_status      pending | passed | warning | failed
quality_report      deterministic and renderer diagnostics
```

If adding database columns is disproportionate, `render_status` and `render_error` may initially live inside `quality_report`, while the tool contract exposes them as top-level fields. The service layer remains responsible for atomic screenshot-result updates.

## Error Handling

- Invalid XML fails `create_drawio_board`; no preview candidate is emitted.
- Candidate persistence failure fails creation and produces no frontend preview.
- Screenshot timeout or Chromium failure affects only the render tool result.
- A failed screenshot remains retryable and does not erase the XML preview.
- A stale or foreign candidate ID is a non-retryable render-tool error.
- Repeated rendering of an already completed candidate returns the stored screenshot.
- If the Agent accepts before rendering, the existing acceptance path is allowed and the accepted version may have no screenshot.
- If rendering completes after acceptance through a retry, the screenshot may be attached to the same immutable version metadata without changing its XML or revision.

## Testing Strategy

### Backend tests

- `create_drawio_board` returns before invoking any renderer.
- A valid candidate is persisted with pending render status and an XML reference.
- Deterministic XML failures still prevent candidate creation.
- `render_drawio_board_candidate` loads persisted XML and returns a multimodal attachment.
- Successful render results are persisted and reused idempotently.
- Failed rendering persists failure details without rejecting or deleting the candidate.
- Foreign-board and foreign-session candidate IDs are rejected.
- `accept_drawio_board_candidate` remains valid without a screenshot or completed render status.
- The board-mode tool registry includes the render tool and other modes do not.
- Runtime board context retains candidate, render, and screenshot fields without treating them as mandatory gates.

### Frontend tests

- A candidate with `preview_candidate=true` becomes visible immediately.
- The preview remains lifecycle `candidate` and is not shown as accepted history.
- Missing `screenshot_ref` does not prevent XML rendering.
- Render failure leaves the visible XML unchanged.
- Accepted output promotes the preview into committed current history.
- Replacement candidates respect revision and event ordering.
- The board remains read-only during the continuing Agent run and unlocks on every terminal path.

### Integration timing test

Use a deliberately slow fake renderer:

1. Start a board-mode request.
2. Assert the `create_drawio_board` tool result and XML reference arrive before the fake renderer completes.
3. Assert the frontend can apply that result immediately.
4. Allow the render tool to finish and verify that its screenshot enters the Agent's next multimodal iteration.
5. Verify that the Agent can accept either before or after render completion.

## Acceptance Criteria

1. `create_drawio_board` does not launch Chromium or wait for PNG export.
2. A valid candidate appears in the frontend after candidate persistence, independently of screenshot duration.
3. The Agent can call a separate render tool and receive the screenshot as a multimodal attachment.
4. The documented normal flow tells the Agent to inspect the screenshot before accepting or revising.
5. Screenshot absence or failure does not create a backend acceptance or completion prohibition.
6. Invalid XML and access-control violations remain hard failures.
7. Candidate preview and accepted version state remain distinguishable in the UI and version history.
