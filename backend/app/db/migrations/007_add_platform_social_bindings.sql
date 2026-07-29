BEGIN;

ALTER TABLE social_users
    ADD COLUMN IF NOT EXISTS platform_user_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS platform_username VARCHAR(255),
    ADD COLUMN IF NOT EXISTS platform_display_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS account_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS ilink_user_id VARCHAR(255);

CREATE TABLE IF NOT EXISTS weixin_scan_tasks (
    id VARCHAR(36) PRIMARY KEY,
    account_id VARCHAR(255) NOT NULL UNIQUE,
    owner_user_id VARCHAR(255) NOT NULL,
    owner_username VARCHAR(255) NOT NULL,
    owner_display_name VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'created',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_weixin_scan_tasks_owner_status
    ON weixin_scan_tasks(owner_user_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_social_users_active_platform_user
    ON social_users(platform_user_id)
    WHERE status = 'active' AND platform_user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_social_users_active_ilink_user
    ON social_users(ilink_user_id)
    WHERE status = 'active' AND ilink_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_social_users_active_account
    ON social_users(account_id, status);

COMMIT;
