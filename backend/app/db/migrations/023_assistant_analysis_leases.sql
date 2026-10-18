-- Apply after 022 to DATABASE_URL before enabling assistant analysis.
BEGIN;
ALTER TABLE assistant_triggers ADD COLUMN IF NOT EXISTS last_result_hash VARCHAR(64);
ALTER TABLE assistant_runs ADD COLUMN IF NOT EXISTS lease_token VARCHAR(36);
ALTER TABLE assistant_runs ADD COLUMN IF NOT EXISTS lease_until TIMESTAMP;
CREATE UNIQUE INDEX IF NOT EXISTS uq_assistant_running_task
    ON assistant_runs(task_id) WHERE state = 'running';
COMMIT;
