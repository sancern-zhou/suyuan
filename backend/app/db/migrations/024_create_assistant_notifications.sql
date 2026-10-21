-- Apply to DATABASE_URL before deploying assistant result replies.
BEGIN;
CREATE TABLE IF NOT EXISTS assistant_notifications (
    message_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL,
    owner_user_id VARCHAR(255) NOT NULL,
    source_session_id VARCHAR(255) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    data JSON NOT NULL,
    state VARCHAR(24) NOT NULL DEFAULT 'pending',
    lease_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_assistant_notifications_owner
    ON assistant_notifications(project_id, owner_user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_assistant_notifications_delivery
    ON assistant_notifications(project_id, state);
COMMIT;
