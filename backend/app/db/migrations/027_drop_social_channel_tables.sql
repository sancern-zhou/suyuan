-- 对话社交渠道（个人微信/QQ）退役：删除渠道绑定相关表。
-- social_session_mappings 保留（广播 inbox 会话映射仍在使用）。
DROP TABLE IF EXISTS weixin_scan_tasks;
DROP TABLE IF EXISTS social_users;
