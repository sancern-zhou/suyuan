-- Apply to DATABASE_URL, not SESSION_DATABASE_URL. No jobs or permissions created.
BEGIN;
CREATE TABLE IF NOT EXISTS assistant_coaching_owners (
    project_id VARCHAR(100) NOT NULL,
    owner_user_id VARCHAR(255) NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (project_id, owner_user_id)
);
CREATE TABLE IF NOT EXISTS assistant_suggestions (
    suggestion_id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL,
    owner_user_id VARCHAR(255) NOT NULL,
    dedup_key VARCHAR(64) NOT NULL,
    capability_id VARCHAR(255) NOT NULL,
    capability_revision VARCHAR(64) NOT NULL,
    goal TEXT NOT NULL,
    reason TEXT NOT NULL,
    suggested_prompt TEXT NOT NULL,
    missing_inputs JSON NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'pending',
    version INTEGER NOT NULL DEFAULT 1,
    source_session_id VARCHAR(255) NOT NULL,
    source_request_id VARCHAR(128) NOT NULL,
    source_user_message TEXT NOT NULL,
    decision_session_id VARCHAR(255),
    decision_request_id VARCHAR(128),
    decision_user_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    CONSTRAINT uq_assistant_suggestion_dedup UNIQUE (project_id, owner_user_id, dedup_key)
);
COMMIT;
