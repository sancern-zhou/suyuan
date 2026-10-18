# Personal assistant reminders: local implementation

This increment connects saved assistant matters to durable owner-only reminders.
It does not run scheduled LLM analysis, scrape WeChat history, contact other users,
or implement the coach experience. Existing scheduled tasks and social heartbeats
are not migrated, imported or executed by this queue.

## Flow and authorization

Authenticated App/social ingress captures the current personal delivery address
in the turn-local AssistantRequest. The LLM cannot supply an owner or recipient.
manage_assistant_followups resolves the owner through the conversation catalog.
Creating a plan and disabling plans require a live human request and the current
matter version. A new background event cannot grant authority. Plan records keep
the source session, request and original human message.

Supported plans: now, once (ISO8601 with optional IANA timezone), interval (minutes),
and five-field APScheduler cron. Default timezone is Asia/Shanghai; cron weekday
numbers follow APScheduler (Monday = 0); prefer weekday names when appropriate.
Plan instructions are literal reminder text, never instructions for an LLM.
Listing returns up to 50 latest plans, occurrences and notifications per matter.

One 5-second APScheduler job on the existing worker scheduler materializes due
occurrences and prepares notifications transactionally. Unique occurrence keys and
conditional updates prevent duplicate work. Repeating plans coalesce downtime to
one occurrence and advance to the next future slot, retaining interval cadence.
One-shot plans more than 24 hours late are recorded as expired rather than sent.
Short-lived delivery tasks keep the clock free of external I/O; shutdown stops
new admissions and cancels the local delivery task.

Cancellation, completion, or an edit to goal/completion criteria revokes existing
plans and unsent messages in the same transaction as the matter edit. Other edits
(feedback/next step) do not change the granted scope. A stopped plan never revives
on replay of its original request. Disabling all reminders also versions/audits
the matter. Reminder execution does not complete or otherwise advance the matter.

## Delivery semantics

App reminders use the existing durable broadcast inbox and best-effort push.
WeChat reminders require a currently active platform-user binding matching the
captured bot and sender. Both paths recheck source-conversation ownership. Other
channels have no delivery adapter in this increment and are rejected.

Before external I/O the outbox claim is committed with a unique fencing token and
90-second lease. Admission checks task/plan validity again and holds the task row
lock across bounded (30 seconds) I/O. A cancellation committed before admission
blocks sending; one committed afterwards cannot recall an admitted message.
SQLite tests use a no-op write for the equivalent transaction fence.

Notification states:

- pending: queued, no external attempt admitted yet.
- sending: one claimed attempt, outcome not recorded yet.
- inbox_saved: App inbox persisted; this does not mean push delivery or reading.
- provider_accepted: WeChat adapter accepted the send; this is not a read receipt.
- rejected: ownership, binding or supported-channel validation failed.
- cancelled: revoked before the send was admitted.
- unknown: timeout, ambiguous failure, or worker interruption during sending.

Unknown attempts are never automatically replayed. Existing channel retries are
disabled only for these reminders via internal delivery metadata; the channel
also checks the expected bot before sending. Provider-internal retry behavior is
outside this queue's guarantees. This is not an exactly-once delivery claim.
To retry an uncertain reminder the user must explicitly request a new one, after
checking the inbox/channel to avoid duplication.

## Configuration and validation boundary

ASSISTANT_FOLLOWUPS_ENABLED defaults to false: the reminder tool is hidden and the
worker clock is not registered. Future rollout requires the same enabled value
on the corresponding web and worker, the project's scheduled tasks enabled, and
migration 021 then 022 applied to DATABASE_URL. Normal database initialization also
registers these SQLAlchemy models. No environment file was changed, no application
service started, and no non-test database migrated during local implementation.

Local tests use temporary SQLite databases, mocked push/WeChat adapters and isolated
settings. They cover owner/project denial, replay, concurrent claims, coalescing,
clock drift, audit/outbox rollback, cancellation ordering, restart uncertainty and
single-attempt transport. PostgreSQL row-lock behavior, actual WeChat/App delivery,
push, and deployed worker lifecycle still need integration acceptance before enablement.

## Upstream provenance

Reference checkout: HKUDS/nanobot b702ac633f149ada9ea123a8bfda5871d7ef6033.
assistant_schedule.definition_hash adapts cron/binding.py binding_revision: hash
editable scope, exclude runtime state. Here scope is goal/completion criteria;
plan fields are immutable after creation. The existing APScheduler implementation
is reused for cron parsing, not nanobot's croniter timer or Agent runtime. See
third_party/nanobot-assistant-tasks.md for the retained MIT notice. Transactional
SQLAlchemy queues and outbox/delivery fencing are local integration code and are
not claimed to be copied or validated by upstream tests.
