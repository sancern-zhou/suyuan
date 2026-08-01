BEGIN;

DROP TABLE IF EXISTS session_resource_manifests;
DROP TABLE IF EXISTS session_resources;
DROP TABLE IF EXISTS session_resource_versions;

CREATE TABLE session_resource_versions (
    session_id VARCHAR(255) PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_resources (
    resource_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    group_id VARCHAR(64) NOT NULL,
    parent_resource_id VARCHAR(64)
        REFERENCES session_resources(resource_id) ON DELETE CASCADE,
    resource_key VARCHAR(255) NOT NULL,
    relation VARCHAR(32) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    role VARCHAR(32) NOT NULL,
    label VARCHAR(512) NOT NULL,
    locator JSONB NOT NULL,
    format VARCHAR(64) NOT NULL,
    media_type VARCHAR(255) NOT NULL,
    renderer VARCHAR(64) NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    tool_name VARCHAR(255) NOT NULL DEFAULT '',
    run_id VARCHAR(255) NOT NULL,
    turn_sequence INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, group_id, version, resource_key)
);

CREATE INDEX ix_session_resources_catalog
    ON session_resources(session_id, status, updated_at DESC);
CREATE INDEX ix_session_resources_group
    ON session_resources(session_id, group_id, version);

ALTER TABLE IF EXISTS sessions
    DROP COLUMN IF EXISTS data_ids,
    DROP COLUMN IF EXISTS visual_ids,
    DROP COLUMN IF EXISTS office_documents;

COMMIT;
