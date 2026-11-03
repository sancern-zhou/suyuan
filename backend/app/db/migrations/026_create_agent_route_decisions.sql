-- Delegation route-decision audit (assistant single-door plan, stage A).
-- One row per top-level delegation; see app/agent/workflow/route_decisions.py.
-- Apply after 025 to DATABASE_URL (not SESSION_DATABASE_URL). Clean schemas
-- also get this table via init_db create_all.
BEGIN;
CREATE TABLE IF NOT EXISTS agent_route_decisions (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(255),
    user_identifier VARCHAR(255),
    parent_mode VARCHAR(64),
    target_modes JSON NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    reason_values JSON NOT NULL DEFAULT '{}'::json,
    route_hint VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_agent_route_decisions_session_created
    ON agent_route_decisions(session_id, created_at);
CREATE INDEX IF NOT EXISTS ix_agent_route_decisions_reason
    ON agent_route_decisions(reason_code);
COMMIT;
