-- Guangdong data-ops guardrails (idempotent; run once per environment via psql).
-- Mirrors projects/jiangsu-ops/data-ops/sync/setup_agent_guardrails.sql.
--
-- 用法（密码经变量传入，不落盘）:
--   psql -v agent_reader_password=... -v app_user=suyuan -f setup_agent_guardrails.sql
--
-- 注意: 需以超级用户（或 CREATEROLE 角色）执行；建的元数据表归属会转给 app_user，
-- 使同步引擎/dq_check（以应用账号连接）可读写。
--
-- 角色: agent_reader 只读、仅 guangdong_mart、15s 语句超时 —— 语义层(Cube)与
-- 智能体 SQL 护栏同权限，语义层不引入任何新数据库权限。

-- 1. 只读角色 ----------------------------------------------------------------
-- 注意: psql 变量 :'...' 在 dollar-quoted 块内不插值，改用 \gexec 顶层拼接。
SELECT format('CREATE ROLE agent_reader LOGIN PASSWORD %L', :'agent_reader_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') \gexec

GRANT USAGE ON SCHEMA guangdong_mart TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA guangdong_mart TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA guangdong_mart
    GRANT SELECT ON TABLES TO agent_reader;
ALTER ROLE agent_reader SET statement_timeout = '15s';
ALTER ROLE agent_reader SET default_transaction_read_only = on;

-- 1b. 元数据表归属转给应用账号（sync 引擎/dq_check 以应用账号读写） -------------
ALTER TABLE guangdong_sync.query_audit  OWNER TO :'app_user';
ALTER TABLE guangdong_sync.dq_results   OWNER TO :'app_user';

-- 2. 审计表 ------------------------------------------------------------------
-- guangdong_sync.query_audit: fetcher 时代为窄表(tool, sql_text, row_count, status)。
-- 2026-10-24 data-ops 化后语义层指标查询需要完整审计结构，幂等补列。
CREATE TABLE IF NOT EXISTS guangdong_sync.query_audit (
    id            bigserial PRIMARY KEY,
    tool          text NOT NULL,
    sql_text      text,
    row_count     integer,
    status        text,
    user_id       text,
    agent_mode    text,
    dataset       text,
    params        jsonb,
    truncated     boolean,
    duration_ms   integer,
    error         text,
    created_at    timestamp default now()
);
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS user_id text;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS agent_mode text;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS dataset text;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS params jsonb;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS truncated boolean;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS duration_ms integer;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS error text;
ALTER TABLE guangdong_sync.query_audit ADD COLUMN IF NOT EXISTS created_at timestamp default now();

-- 3. DQ 结果表（dq_check.py 也会自建，这里统一归属） -------------------------
CREATE TABLE IF NOT EXISTS guangdong_sync.dq_results (
    check_name  text,
    table_name  text,
    status      text,
    detail      text,
    checked_at  timestamp default now()
);
CREATE INDEX IF NOT EXISTS idx_dq_results_table
    ON guangdong_sync.dq_results (table_name, checked_at);
