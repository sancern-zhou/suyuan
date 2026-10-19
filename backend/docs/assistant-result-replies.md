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

Web and App use the same account-owned SQL conversations, including messages,
resource references and pending questions. App no longer writes channel JSON
transcripts. Company logins share the platform user ID; device accounts share
only through an explicit bind_user_id, never through a matching display name.
New App conversations are writable from Web. Existing transcripts are not migrated.

Replies append to the original conversation. When the business and session
databases differ, the transcript commits before the outbox acknowledgement;
notification_id deduplication makes replay safe after a crash. Execution
reconciliation also reads the session database instead of joining across databases.
Both clients poll every five seconds while visible, refresh idle assistant
conversations, and show unread counts in conversation history. A read watermark
advances only after rendering, never beyond persisted messages. Reading on one
surface clears the other surface's unread count on its next refresh. There is
no separate reply banner or notification tab. Result assets remain available
through the execution's existing conversation/resources.

Tasks created from Web or App target their shared conversation by default,
without requiring a separate notification channel or push configuration.
Explicit external-channel recipients retain the single-attempt delivery adapter.
Bindings and source ownership are revalidated before sending.
A timed-out or interrupted external send becomes unknown and is not silently
replayed. Pending, rejected and unknown receipts remain visible in the owner-only
notification API. There is no exactly-once claim for external providers.

An execute plan may bind an existing matter using task_id/expected_version.
Successful execution proposes waiting_input (acceptance); failed execution
proposes blocked. It never automatically marks the matter completed. A later
result may advance its own previous progress, but cannot overwrite intervening
human edits, another plan's progress, or a completed/cancelled matter. Superseded
updates are recorded; the result reply is retained for review.

## Temporary Old App Compatibility

Old clients may continue creating and using new SQL conversations without an
APK update. No pre-upgrade channel session is migrated or made writable.
Their create request omits mode, so its SQL draft keeps mode unset until the
first turn atomically binds query/expert/knowledge. A bound mode cannot change.
File-only uploads use the account's DB-backed current-session mapping. If the
user switches conversations before sending, server-authorized attachment
resource groups (including previews) are copied to the selected conversation;
other accounts' attachments are rejected and retry reuses existing resources.
Old history lists only modes those clients understand, excluding assistant.

New clients send X-App-Conversation-Version: 2, explicit create/upload modes,
and upload session_id. They retain strict session-scoped attachment validation
and do not use the compatibility mapping. The header selects request handling,
never authorization. No feature flag or additional SQL migration is needed.

After the App rollout, remove app/social/app_client_compat.py and its gateway
hooks, restore required explicit create/upload modes, remove the temporary
Android header and transition tests. Preserve conversations whose draft mode
was already bound; no transcript conversion is necessary. Empty unbound drafts
can be discarded with the normal session cleanup. Local compatibility tests use
old HTTP payloads with actual temporary SQL/file storage and a fake Agent;
they do not replace deployed PostgreSQL and physical old-APK acceptance.

## Deployment

Apply `backend/app/db/migrations/024_create_assistant_notifications.sql` to the
matching DATABASE_URL before deploying this change. Existing assistant features
also require migrations 021 through 023. New database initialization includes
the notification model. Apply migration 025_create_conversation_reads.sql to
SESSION_DATABASE_URL (or DATABASE_URL when unset), where sessions and the
conversation catalog live. No additional environment variable is required.
Rebuild frontend from `frontend/` using `npm run build:standalone` and restart
the matching Web/worker pair when deploying. This implementation did not change
environment files, run a production migration, or deploy services.

Local tests use temporary SQLite and fake transports. PostgreSQL concurrency,
real push/WeChat delivery and deployed multi-process operation require integration
acceptance; SQLite tests do not establish those guarantees.
