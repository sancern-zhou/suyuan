CREATE TABLE IF NOT EXISTS session_resource_manifests (
    session_id VARCHAR(255) PRIMARY KEY,
    resource_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_session_resource_manifests_updated_at
    ON session_resource_manifests (updated_at);
