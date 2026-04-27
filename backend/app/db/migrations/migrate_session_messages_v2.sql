-- 迁移脚本：session_messages 表适配 Anthropic 原生格式
--
-- 变更内容：
-- 1. 新增 role 列（user/assistant），存储 Anthropic 角色
-- 2. 将 message_type (PostgreSQL ENUM) 重命名为 msg_type (VARCHAR)，语义类型扩展（新增 tool_result）
-- 3. 将 content 从 TEXT 改为 JSONB，支持 Anthropic content blocks 列表
--
-- 执行方式：
--   psql -U postgres -d weather_db -f migrate_session_messages_v2.sql
-- 或通过 Python：
--   async with engine.connect() as conn: await conn.execute(text(open(sql_path).read()))

BEGIN;

-- =============================================
-- Step 1: 新增 role 列
-- =============================================
ALTER TABLE session_messages ADD COLUMN IF NOT EXISTS role VARCHAR(20);

-- 从旧的 message_type 推导 role
-- 注意：PostgreSQL ENUM 值比较时需要显式类型转换
UPDATE session_messages SET role = 'user' WHERE message_type::text = 'user';
UPDATE session_messages SET role = 'assistant' WHERE message_type::text IN ('final', 'thought', 'action', 'observation');
UPDATE session_messages SET role = 'assistant' WHERE role IS NULL;

ALTER TABLE session_messages ALTER COLUMN role SET NOT NULL;

-- =============================================
-- Step 2: 将 message_type 从 ENUM 改为 VARCHAR
-- =============================================
-- 先删除旧索引
DROP INDEX IF EXISTS ix_session_messages_type_timestamp;

-- PostgreSQL 不支持直接 ALTER ENUM 列为 VARCHAR，
-- 需要先添加新列，复制数据，删除旧列，重命名新列
ALTER TABLE session_messages ADD COLUMN IF NOT EXISTS msg_type VARCHAR(30);

-- 复制数据（ENUM 转为文本）
UPDATE session_messages SET msg_type = message_type::text;

ALTER TABLE session_messages ALTER COLUMN msg_type SET NOT NULL;

-- 删除旧列
ALTER TABLE session_messages DROP COLUMN message_type;

-- =============================================
-- Step 3: 将 content 从 TEXT 转为 JSONB
-- =============================================
-- 策略：将现有 TEXT 内容转为 JSON 字符串存储在 JSONB 中
-- 纯文本内容 → 存为 JSON 字符串（JSONB 中带引号的字符串）
-- 空值 → NULL
ALTER TABLE session_messages ALTER COLUMN content TYPE JSONB USING
    CASE
        WHEN content IS NULL THEN NULL
        ELSE to_jsonb(content)
    END;

-- =============================================
-- Step 4: 创建新索引
-- =============================================
CREATE INDEX IF NOT EXISTS ix_session_messages_role_timestamp ON session_messages(role, timestamp);
CREATE INDEX IF NOT EXISTS ix_session_messages_type_timestamp ON session_messages(msg_type, timestamp);

-- =============================================
-- Step 5: 清理旧的 PostgreSQL ENUM 类型
-- =============================================
-- 删除已不再使用的 messagetype 枚举类型
DROP TYPE IF EXISTS messagetype;

-- =============================================
-- Step 6: 更新注释
-- =============================================
COMMENT ON COLUMN session_messages.role IS 'Anthropic 角色：user / assistant';
COMMENT ON COLUMN session_messages.msg_type IS '语义类型：user / thought / action / observation / tool_result / final';
COMMENT ON COLUMN session_messages.content IS '消息内容（JSONB）：支持纯文本字符串和 Anthropic content blocks 列表';

COMMIT;
