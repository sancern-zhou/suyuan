CREATE TABLE IF NOT EXISTS scheduled_task_results (
    execution_id VARCHAR(255) PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL,
    task_name VARCHAR(255) NOT NULL DEFAULT '',
    session_id VARCHAR(255),
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    city VARCHAR(120),
    station_id VARCHAR(120),
    station_name VARCHAR(255),
    pollutant VARCHAR(120),
    conclusion TEXT,
    conclusion_source VARCHAR(64),
    broadcast_message TEXT,
    broadcast_image_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    image_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    document_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_package_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    report_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    trigger_type VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    event_id VARCHAR(240),
    event_type VARCHAR(120),
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

ALTER TABLE scheduled_task_results
    ADD COLUMN IF NOT EXISTS broadcast_message TEXT,
    ADD COLUMN IF NOT EXISTS broadcast_image_paths JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS ix_scheduled_task_results_task_id
    ON scheduled_task_results (task_id);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_results_status
    ON scheduled_task_results (status);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_results_station_id
    ON scheduled_task_results (station_id);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_results_pollutant
    ON scheduled_task_results (pollutant);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_results_task_completed
    ON scheduled_task_results (task_id, completed_at);
CREATE INDEX IF NOT EXISTS ix_scheduled_task_results_completed
    ON scheduled_task_results (completed_at);
