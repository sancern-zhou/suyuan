CREATE TABLE IF NOT EXISTS drawio_boards (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT 'Draw.io Board',
    current_version_id VARCHAR(36),
    revision INTEGER NOT NULL DEFAULT 0,
    draft_xml_ref JSONB,
    draft_sha256 VARCHAR(64),
    draft_revision INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_drawio_boards_session_id ON drawio_boards(session_id);

CREATE TABLE IF NOT EXISTS drawio_board_versions (
    id VARCHAR(36) PRIMARY KEY,
    board_id VARCHAR(36) NOT NULL REFERENCES drawio_boards(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    parent_version_id VARCHAR(36),
    restored_from_version_id VARCHAR(36),
    source VARCHAR(32) NOT NULL,
    lifecycle_status VARCHAR(24) NOT NULL,
    xml_ref JSONB NOT NULL,
    xml_sha256 VARCHAR(64) NOT NULL,
    screenshot_ref JSONB,
    quality_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    quality_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    agent_run_id VARCHAR(255),
    summary TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMP,
    CONSTRAINT uq_drawio_board_version_number UNIQUE (board_id, version_number)
);

CREATE INDEX IF NOT EXISTS ix_drawio_board_versions_board_id ON drawio_board_versions(board_id);
CREATE INDEX IF NOT EXISTS ix_drawio_board_versions_xml_sha256 ON drawio_board_versions(xml_sha256);
CREATE INDEX IF NOT EXISTS ix_drawio_board_versions_agent_run_id ON drawio_board_versions(agent_run_id);
CREATE INDEX IF NOT EXISTS ix_drawio_board_versions_history
    ON drawio_board_versions(board_id, lifecycle_status, version_number);
