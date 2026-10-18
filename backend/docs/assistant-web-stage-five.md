# Web assistant integration

The existing Web assistant entry now uses the shared social runtime. Its public
UI ID remains `assistant` for existing history and navigation; request bodies
and the authenticated `/api/agent/analyze` adapter normalize it to `social`.
Restoring social metadata selects the assistant entry. Other professional modes
retain their direct entrypoints and request modes. No Android changes are included.

## Common runtime and compatibility

Social retains the former assistant's office tools through the existing registry,
including project-specific selections and final project disable rules. Narrow
specialist delegation remains governed by existing primary-mode restrictions.
The obsolete shared mode-memory editor is hidden for this personal assistant.
Web memory uses a filesystem-safe hash of authenticated auth source and user ID;
client-supplied user IDs cannot choose personal memory. Professional mode memory
behavior remains unchanged.

Web sessions remain in the existing Web conversation store. Sharing an agent
runtime does not migrate App history, merge accounts, or unify personal memory
between clients. Such migration needs an explicit account mapping contract later.

## Matters, suggestions, and reminders

The chat toolbar opens a personal assistant panel with three views:

- Matters: list/detail/history, feedback, resume, completion with evidence,
  cancellation, stopping followups, and explicit continuation in the source chat.
- Suggestions: acceptance/dismissal and explicit continuation. Acceptance records
  a choice with `execution_state=not_started`; it does not silently run a task.
- Reminders: persisted inbox records and navigation to the related matter.

The authenticated `/api/assistant` API reuses existing task/coaching/followup
services. Reads scope by project and authenticated owner. Mutations additionally
require the original conversation to be Web-owned by that same user; even admin
read access cannot mutate someone else's assistant. Buttons create a fresh,
bounded human-request scope and use optimistic versions. Tool availability still
controls operations. Account changes discard late frontend responses.

The Web recipient is a server-derived owner hash, not a client-selected address.
Reminder delivery validates both source type and exact owner, then commits
`inbox_saved` to the durable outbox. This means a record is available in the Web
panel, not that browser/system push was sent. The visible panel refreshes every
30 seconds when idle, and after a chat completes. It does not poll while editing
feedback, and paginated lists can be refreshed explicitly.

## Local rollout boundary

No deployment, real database migration, worker activation, production environment
change, model call, Android integration, or real external message is performed.
Existing installations need migrations 021 through 024 in their own database.
Reminder/analysis feature flags retain their current defaults; the panel does not
enable them. A later integration run must validate configured Web/worker pairs,
real account identity, real model behavior, database concurrency, and inbox
delivery before the App migration.

## Validation

Backend coverage includes authenticated Web SSE ingress, ownership and project
isolation, mutation/version conflicts, disabled capabilities, choice-only
acceptance, and real reminder state transitions using temporary SQLite storage.
Frontend tests cover request/restore aliases and existing account/session rules.
Playwright covers desktop/mobile panel actions and explicit suggestion continuation
with intercepted API responses; it is not a live backend/model end-to-end test.

Run browser tests from `frontend/` with
`npx playwright test e2e/web-assistant.spec.mjs --workers=1`.
Set `PLAYWRIGHT_CHANNEL=chrome` to use installed Chrome instead of downloading
Playwright Chromium. Build only with `npm run build:standalone` in `frontend/`.
