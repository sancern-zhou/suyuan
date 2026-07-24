CREATE TABLE IF NOT EXISTS session_resources (
    session_id VARCHAR(255) NOT NULL,
    resource_key VARCHAR(255) NOT NULL,
    resource_id VARCHAR(64) NOT NULL UNIQUE,
    kind VARCHAR(32) NOT NULL,
    role VARCHAR(32) NOT NULL,
    logical_key VARCHAR(255),
    label VARCHAR(512) NOT NULL,
    locator JSONB NOT NULL,
    presentation_type VARCHAR(32),
    presentation JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_name VARCHAR(255) NOT NULL,
    run_id VARCHAR(255) NOT NULL,
    turn_sequence INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, resource_key)
);

CREATE INDEX IF NOT EXISTS ix_session_resources_session_updated
    ON session_resources(session_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS ix_session_resources_session_presentation
    ON session_resources(session_id, presentation_type, status);

CREATE TABLE IF NOT EXISTS session_resource_versions (
    session_id VARCHAR(255) PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
