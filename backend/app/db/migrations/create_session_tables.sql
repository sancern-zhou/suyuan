-- 创建会话表
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    query TEXT NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    mode VARCHAR(50),
    current_step VARCHAR(255),
    current_expert VARCHAR(100),
    data_ids JSONB,
    visual_ids JSONB,
    office_documents JSONB,
    error JSONB,
    metadata JSONB
);

-- 创建会话消息表（兼容 Anthropic 原生 content blocks 格式）
CREATE TABLE IF NOT EXISTS session_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,              -- Anthropic 角色：user / assistant
    msg_type VARCHAR(30) NOT NULL,          -- 语义类型：user/thought/action/observation/tool_result/final
    content JSONB,                          -- 消息内容：支持纯文本字符串和 Anthropic content blocks 列表
    data JSONB,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    sequence_number INTEGER NOT NULL
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_sessions_session_id ON sessions(session_id);
CREATE INDEX IF NOT EXISTS ix_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS ix_sessions_created_at ON sessions(created_at);
CREATE INDEX IF NOT EXISTS ix_sessions_state_created ON sessions(state, created_at);
CREATE INDEX IF NOT EXISTS ix_sessions_mode_created ON sessions(mode, created_at);

CREATE INDEX IF NOT EXISTS ix_session_messages_session_id ON session_messages(session_id);
CREATE INDEX IF NOT EXISTS ix_session_messages_sequence_number ON session_messages(sequence_number);
CREATE INDEX IF NOT EXISTS ix_session_messages_session_sequence ON session_messages(session_id, sequence_number);
CREATE INDEX IF NOT EXISTS ix_session_messages_role_timestamp ON session_messages(role, timestamp);
CREATE INDEX IF NOT EXISTS ix_session_messages_type_timestamp ON session_messages(msg_type, timestamp);

-- 创建更新时间戳触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE sessions IS '会话主表，存储会话基本信息和元数据';
COMMENT ON TABLE session_messages IS '会话消息表，存储每条消息的详细信息';
COMMENT ON COLUMN sessions.state IS '会话状态：active/paused/completed/failed/archived';
COMMENT ON COLUMN session_messages.role IS 'Anthropic 角色：user / assistant';
COMMENT ON COLUMN session_messages.msg_type IS '语义类型：user / thought / action / observation / tool_result / final';
COMMENT ON COLUMN session_messages.content IS '消息内容（JSONB）：支持纯文本字符串和 Anthropic content blocks 列表';
