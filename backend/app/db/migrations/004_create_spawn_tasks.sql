-- Migration 004: Create spawn_tasks table
-- Description: Table for storing background subagent task status
-- Date: 2026-03-28

CREATE TABLE IF NOT EXISTS spawn_tasks (
    task_id VARCHAR(100) PRIMARY KEY,
    social_user_id VARCHAR(200) NOT NULL,
    task TEXT NOT NULL,
    label VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    progress FLOAT DEFAULT 0.0,
    result TEXT,
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    origin_channel VARCHAR(50) NOT NULL,
    origin_chat_id VARCHAR(200) NOT NULL,
    origin_sender_id VARCHAR(200) NOT NULL,
    bot_account VARCHAR(200)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_spawn_tasks_status ON spawn_tasks(status);
CREATE INDEX IF NOT EXISTS idx_spawn_tasks_user ON spawn_tasks(social_user_id);
CREATE INDEX IF NOT EXISTS idx_spawn_tasks_created ON spawn_tasks(created_at);

-- Create index for composite query (user + status)
CREATE INDEX IF NOT EXISTS idx_spawn_tasks_user_status ON spawn_tasks(social_user_id, status);
