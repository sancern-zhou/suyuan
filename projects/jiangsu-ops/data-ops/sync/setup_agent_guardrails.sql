-- ============================================================
-- Agent 数据访问护栏（确定性, 数据库层强制）
-- agent_reader: 只读, 仅 jiangsu_mart schema, 15s 语句超时, 强制只读事务
-- query_audit : Agent 查询审计表（由应用账号写入）
-- 运行: psql -v agent_reader_password="<实际密码>" -f setup_agent_guardrails.sql
-- 密码不落仓库; 已建过角色的库上重跑, 下方 WHERE NOT EXISTS 使建号语句不执行
-- ============================================================

SELECT format('CREATE ROLE agent_reader LOGIN PASSWORD %L', :'agent_reader_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader')
\gexec

ALTER ROLE agent_reader SET default_transaction_read_only = on;
ALTER ROLE agent_reader SET statement_timeout = '15s';
ALTER ROLE agent_reader SET idle_in_transaction_session_timeout = '30s';

GRANT USAGE ON SCHEMA jiangsu_mart TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA jiangsu_mart TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA jiangsu_mart GRANT SELECT ON TABLES TO agent_reader;

-- 审计表: 应用侧工具每次查询写入一条
CREATE TABLE IF NOT EXISTS jiangsu_sync.query_audit (
    audit_id     bigserial PRIMARY KEY,
    queried_at   timestamp DEFAULT now(),
    user_id      text,
    agent_mode   text,
    tool         text,
    dataset      text,
    params       jsonb,
    rows_returned integer,
    truncated    boolean,
    duration_ms  integer,
    error        text
);
CREATE INDEX IF NOT EXISTS ix_qa_dataset_time ON jiangsu_sync.query_audit (dataset, queried_at DESC);
