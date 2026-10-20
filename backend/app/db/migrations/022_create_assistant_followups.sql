-- Personal reminders. Apply after 021 to DATABASE_URL (not SESSION_DATABASE_URL).
BEGIN;
CREATE TABLE IF NOT EXISTS assistant_triggers (
    trigger_id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL REFERENCES assistant_tasks(task_id),
    request_key VARCHAR(64) NOT NULL UNIQUE,
    kind VARCHAR(16) NOT NULL,
    action VARCHAR(16) NOT NULL,
    instructions TEXT NOT NULL,
    schedule JSON NOT NULL,
    next_at TIMESTAMP,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    definition_hash VARCHAR(64) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    grant_session_id VARCHAR(255) NOT NULL,
    grant_request_id VARCHAR(128) NOT NULL,
    grant_message TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_assistant_trigger_due ON assistant_triggers(enabled, next_at);
CREATE TABLE IF NOT EXISTS assistant_runs (
    run_id VARCHAR(36) PRIMARY KEY,
    trigger_id VARCHAR(36) NOT NULL REFERENCES assistant_triggers(trigger_id),
    task_id VARCHAR(36) NOT NULL REFERENCES assistant_tasks(task_id),
    occurrence_key VARCHAR(100) NOT NULL,
    state VARCHAR(24) NOT NULL DEFAULT 'queued',
    task_version INTEGER,
    attempts INTEGER NOT NULL DEFAULT 0,
    result JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    CONSTRAINT uq_assistant_run_occurrence UNIQUE(trigger_id, occurrence_key)
);
CREATE INDEX IF NOT EXISTS ix_assistant_run_queue ON assistant_runs(state, created_at);
CREATE TABLE IF NOT EXISTS assistant_outbox (
    message_id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL UNIQUE REFERENCES assistant_runs(run_id),
    task_id VARCHAR(36) NOT NULL REFERENCES assistant_tasks(task_id),
    trigger_id VARCHAR(36) NOT NULL REFERENCES assistant_triggers(trigger_id),
    recipient VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    state VARCHAR(24) NOT NULL DEFAULT 'pending',
    lease_token VARCHAR(36),
    lease_until TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_assistant_outbox_pending ON assistant_outbox(state, available_at);
COMMIT;
