-- Shared conversation board: user-published conversation snapshots.
-- New deployments get this table via Base.metadata.create_all; run this
-- manually only when upgrading an existing database.
CREATE TABLE IF NOT EXISTS social_shared_conversations (
    share_id VARCHAR(64) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    owner_username VARCHAR(255) NOT NULL DEFAULT '',
    owner_display_name VARCHAR(255) NOT NULL DEFAULT '',
    source_session_id VARCHAR(255) NOT NULL,
    source_kind VARCHAR(32) NOT NULL DEFAULT 'social',
    mode VARCHAR(64) NOT NULL DEFAULT '',
    title VARCHAR(500) NOT NULL,
    first_question TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    snapshot JSON NOT NULL,
    attachments JSON NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    removed_by VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_social_shared_status_created
    ON social_shared_conversations(status, created_at);
CREATE INDEX IF NOT EXISTS ix_social_shared_owner
    ON social_shared_conversations(owner_user_id);
