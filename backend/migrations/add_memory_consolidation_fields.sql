-- 添加记忆整合追踪字段到 social_session_mappings 表
-- 执行时间：2026-03-26

ALTER TABLE social_session_mappings
ADD COLUMN IF NOT EXISTS last_consolidated_offset INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_message_count INTEGER DEFAULT 0;

-- 创建注释
COMMENT ON COLUMN social_session_mappings.last_consolidated_offset IS 'Last consolidated message offset (for incremental consolidation)';
COMMENT ON COLUMN social_session_mappings.total_message_count IS 'Total message count for this session';
