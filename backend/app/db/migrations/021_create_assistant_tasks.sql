-- Long-lived assistant matters. Apply to DATABASE_URL, not SESSION_DATABASE_URL.
BEGIN;

CREATE TABLE IF NOT EXISTS assistant_tasks (
    task_id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL,
    owner_user_id VARCHAR(255) NOT NULL,
    source_session_id VARCHAR(255) NOT NULL,
    request_key VARCHAR(64) NOT NULL,
    goal TEXT NOT NULL,
    completion_criteria TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ready',
    next_step TEXT NOT NULL DEFAULT '',
    result_summary TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_assistant_task_request UNIQUE (project_id, owner_user_id, request_key)
);

CREATE INDEX IF NOT EXISTS ix_assistant_tasks_owner_updated
    ON assistant_tasks (project_id, owner_user_id, updated_at);

CREATE TABLE IF NOT EXISTS assistant_task_events (
    event_id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL REFERENCES assistant_tasks(task_id),
    version INTEGER NOT NULL,
    kind VARCHAR(32) NOT NULL,
    source_session_id VARCHAR(255) NOT NULL,
    source_request_id VARCHAR(128) NOT NULL,
    user_message TEXT NOT NULL,
    changes JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_assistant_task_event_version UNIQUE (task_id, version)
);

COMMIT;
