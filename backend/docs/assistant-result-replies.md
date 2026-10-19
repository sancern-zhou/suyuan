# Assistant Result Replies

Execution plans created by `manage_assistant_schedule` retain the server-derived
owner, source session and personal delivery route. Completion, failure, timeout
and cancellation enqueue a reply independent of the execution status. This does
not enable sending to arbitrary recipients or require the professional Agent to
call a broadcast tool.

The worker's existing APScheduler wakes the durable reply queue every 10 seconds.
This clock does not depend on ASSISTANT_FOLLOWUPS_ENABLED or
ASSISTANT_ANALYSIS_ENABLED: an accepted execution plan always owes its owner a
result. Existing feature flags still control creating reminders and analyses.
The worker reconciles terminal executions missing a notification after a crash.
No old conversation or task migration is provided.

Web replies append to the original conversation. The message and inbox receipt
commit in one transaction; repeat delivery cannot append a second message.
The Web checks unread replies while the page is visible, displays an unread
banner even when the assistant panel is closed, and inserts replies in the
active conversation only when it is not streaming. Opening a reply records a
read receipt. Reply persistence, provider acceptance and actual reading remain
distinct. Web notifications support execution-detail navigation; result assets
remain accessible through the execution's existing conversation/resources.

App and bound WeChat recipients reuse the existing inbox/push and single-attempt
delivery adapter. Bindings and source ownership are revalidated before sending.
A timed-out or interrupted external send becomes unknown and is not silently
replayed. Pending, rejected and unknown receipts remain visible in the owner-only
notification API. There is no exactly-once claim for external providers.

An execute plan may bind an existing matter using task_id/expected_version.
Successful execution proposes waiting_input (acceptance); failed execution
proposes blocked. It never automatically marks the matter completed. A later
result may advance its own previous progress, but cannot overwrite intervening
human edits, another plan's progress, or a completed/cancelled matter. Superseded
updates are recorded; the result reply is retained for review.

## Deployment

Apply `backend/app/db/migrations/024_create_assistant_notifications.sql` to the
matching DATABASE_URL before deploying this change. Existing assistant features
also require migrations 021 through 023. New database initialization includes
the notification model. No additional environment variable is required.
Rebuild frontend from `frontend/` using `npm run build:standalone` and restart
the matching Web/worker pair when deploying. This implementation did not change
environment files, run a production migration, or deploy services.

Local tests use temporary SQLite and fake transports. PostgreSQL concurrency,
real push/WeChat delivery and deployed multi-process operation require integration
acceptance; SQLite tests do not establish those guarantees.
