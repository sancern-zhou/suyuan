BEGIN;

CREATE TABLE IF NOT EXISTS conversation_catalog (
    session_id VARCHAR(255) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    owner_username VARCHAR(255) NOT NULL,
    owner_display_name VARCHAR(255) NOT NULL,
    source VARCHAR(32) NOT NULL
        CHECK (source IN ('web', 'knowledge_qa', 'social')),
    mode VARCHAR(50),
    title TEXT,
    read_only_on_web BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_conversation_catalog_owner_updated
    ON conversation_catalog(owner_user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS ix_conversation_catalog_source_updated
    ON conversation_catalog(source, updated_at DESC);

INSERT INTO conversation_catalog (
    session_id,
    owner_user_id,
    owner_username,
    owner_display_name,
    source,
    mode,
    title,
    read_only_on_web,
    created_at,
    updated_at
)
SELECT
    session_id,
    '1', 'ScGuanLy', '超级管理员',
    'web',
    mode,
    LEFT(query, 256),
    FALSE,
    created_at,
    updated_at
FROM sessions
ON CONFLICT (session_id) DO NOTHING;

UPDATE knowledge_conversation_sessions
SET user_id = '1'
WHERE user_id IS NULL;

INSERT INTO conversation_catalog (
    session_id,
    owner_user_id,
    owner_username,
    owner_display_name,
    source,
    mode,
    title,
    read_only_on_web,
    created_at,
    updated_at
)
SELECT
    id,
    user_id,
    CASE WHEN user_id = '1' THEN 'ScGuanLy' ELSE user_id END,
    CASE WHEN user_id = '1' THEN '超级管理员' ELSE user_id END,
    'knowledge_qa',
    'knowledge_qa',
    title,
    FALSE,
    created_at,
    updated_at
FROM knowledge_conversation_sessions
ON CONFLICT (session_id) DO NOTHING;

COMMIT;
