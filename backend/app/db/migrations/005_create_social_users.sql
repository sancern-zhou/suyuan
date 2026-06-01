-- Migration 005: Create social_users table
-- Description: Minimal social user profiles and binding-code onboarding
-- Date: 2026-05-31

CREATE TABLE IF NOT EXISTS social_users (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'pending_bind',
    bind_code VARCHAR(20) UNIQUE,
    social_user_id VARCHAR(255) UNIQUE,
    channel VARCHAR(80),
    bot_account VARCHAR(200),
    sender_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    bound_at TIMESTAMP,
    last_seen_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_social_users_status ON social_users(status);
CREATE INDEX IF NOT EXISTS idx_social_users_bind_code ON social_users(bind_code);
CREATE INDEX IF NOT EXISTS idx_social_users_social_user_id ON social_users(social_user_id);
CREATE INDEX IF NOT EXISTS idx_social_users_sender
    ON social_users(channel, bot_account, sender_id);

COMMENT ON TABLE social_users IS 'Minimal social user profiles for binding-code onboarding';
COMMENT ON COLUMN social_users.status IS 'User status: pending_bind/active/disabled';
COMMENT ON COLUMN social_users.bind_code IS 'One-time binding code shown after admin creates user';
COMMENT ON COLUMN social_users.social_user_id IS 'Bound social identity: {channel}:{bot_account}:{sender_id}';
