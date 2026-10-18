# Assistant matters: first implementation package

## Scope

Social conversations can register an explicitly delegated matter, query its current
state, record user feedback, wait for missing inputs, resume, complete with a result
description, or cancel. Registration is not a durable background execution request.
This package does not add automatic wakeups, event subscriptions, cross-user action
grants, push navigation or an App UI. App chat accepts the social mode for API clients;
existing professional-mode defaults remain unchanged.

## Database preparation

New tables live in DATABASE_URL alongside application/social records. They do not
belong in the optional separate SESSION_DATABASE_URL. A clean schema gets the tables
through app.db.prepare_database. Managed existing deployments can apply
backend/app/db/migrations/021_create_assistant_tasks.sql using their normal migration
procedure before enabling the updated service. Startup schema initialization remains
opt-in. Do not change environment files or enable schema creation on every web worker.

There is no file fallback, no 24-hour cleanup and no cascade from conversation expiry.
If the database is unavailable, operations fail explicitly; a client should query
again after recovery instead of assuming a write failed or repeating side effects.

## Tool and API

manage_assistant_tasks is added only to social, including project overrides, and can
be excluded by project disabled_tools. Its shared behavior contract is appended to
both the generic and project-specific social prompt. Owner identity comes from the
authoritative conversation catalog; project identity comes from server settings.

App reads require the standard App token:

- GET /api/social/app/assistant/tasks?limit=20
- GET /api/social/app/assistant/tasks/{task_id}

The create operation saves goal, completion_criteria, the original current user
message and its session/request origin. Same request/session/goal creates one matter.
Changes require the version returned by get/list. Waiting and blocking require a
next_step; completing requires a result_summary. Completion records the Agent's stated
delivery evidence; it is not an independent validation of the generated report.
Terminal matters cannot be reopened implicitly. Feedback is an audit event containing
the actual user input; it does not pretend a new field data source was connected.

## Authorization and concurrency

Authority starts only at App/interactive social ingress and ends in finally. Tools
cannot supply an owner, project or authorization flag. A background heartbeat or
different child session cannot use the originating request. The lifetime object is
also revoked for inherited asyncio contexts when the original turn ends.

Database uniqueness handles creation races; version-conditional UPDATE handles
changes. Task state and audit event commit together. This establishes the user-request
boundary only, not a general permission to send messages or execute external actions.
Future worker execution must have its own persisted grants and run lifecycle.

## Validation and next package

Tests use a separate SQLite database and actual SQLAlchemy statements to cover restart
persistence, duplicate/concurrent creates, competing terminal changes, cross-project
and cross-owner reads/writes, audit failures, feedback provenance and scope cleanup.
App HTTP tests cover auth, ownership and database error responses; transport tests
check authority lifetime. These do not replace PostgreSQL or App/WeChat live E2E.

Local validation on 2026-10-18 (backend_py311): 49 passed, 1 deselected in the
assistant-matters, App gateway, bound-social routing, social-tool and exam-bridge
selection. The deselected existing exam tool-list assertion omits edit_file even
though the baseline registry includes it. Broader collection is blocked by existing
missing xarray (lifecycle suite) and a removed ResourceBatchResult import (legacy
multimodal suite). New module lint checks pass. No production schema or service was
changed; PostgreSQL and real-channel E2E remain outstanding.

Next package: connect durable runs and triggers to the existing worker/scheduler,
including cancellation checks, leases and outbox. Keep the distinction between a
registered matter, an accepted execution and a verified delivered result.

Upstream adaptation and MIT notice: backend/docs/third_party/nanobot-assistant-tasks.md.
