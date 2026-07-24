-- Hard cutover: the row-oriented store is the only durable session resource source.
DROP TABLE IF EXISTS session_resource_manifests;
DROP TABLE IF EXISTS session_resource_versions;
CREATE TABLE IF NOT EXISTS session_resource_versions (
    session_id VARCHAR(255) PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE IF EXISTS sessions
    DROP COLUMN IF EXISTS data_ids,
    DROP COLUMN IF EXISTS visual_ids,
    DROP COLUMN IF EXISTS office_documents;
