-- Independent per-user inbox for scheduled report results.
CREATE TABLE IF NOT EXISTS social_report_results (
    report_id VARCHAR(255) PRIMARY KEY,
    owner_user_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    execution_id VARCHAR(255) NOT NULL,
    task_name VARCHAR(500) NOT NULL,
    report_type VARCHAR(100) NOT NULL DEFAULT 'scheduled_report',
    title VARCHAR(500) NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'success',
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP NULL,
    attachments JSON NOT NULL,
    metadata_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_social_report_owner_generated
    ON social_report_results(owner_user_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS ix_social_report_owner_type_generated
    ON social_report_results(owner_user_id, report_type, generated_at DESC);
