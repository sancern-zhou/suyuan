# 多用户记忆隔离和自动整合 - 部署指南

## 概述

本次更新实现了完整的单平台多机器人记忆隔离和自动整合机制，确保每个机器人账号的每个用户拥有独立的长期记忆和对话历史。

## 实施的功能

### 1. 用户级记忆隔离
- ✅ 每个机器人账号的每个用户拥有独立的记忆空间
- ✅ 记忆隔离键格式：`{channel}:{bot_account}:{sender_id}`
- ✅ 用户专属目录：`backend_data_registry/social/memory/{channel}_{bot_account}_{sender_id}/`

### 2. Token 自动触发整合
- ✅ Session 历史 token 数超过 80% 上下文窗口时自动触发
- ✅ 距离上次整合超过 10 条消息时自动触发
- ✅ 增量整合：避免重复整合相同内容

### 3. Session 偏移量追踪
- ✅ `last_consolidated_offset`：上次整合的消息偏移量
- ✅ `total_message_count`：总消息数
- ✅ 持久化存储：JSON 文件和 PostgreSQL 数据库

### 4. 心跳服务完善
- ✅ 定时任务执行：调用 Agent 执行 HEARTBEAT.md 中的任务
- ✅ 任务结果通知：主动推送结果到订阅用户

### 5. 机器人账号识别
- ✅ BaseChannel 添加 `bot_account` 属性
- ✅ WeixinChannel 保存并返回 `ilink_bot_id`
- ✅ ChannelManager 注册 channels 到 AgentBridge

## 文件修改清单

### 新增文件
- `backend/app/social/user_memory_manager.py` - 用户记忆管理器
- `backend/app/tools/social/__init__.py` - 社交工具包初始化
- `scripts/clear_global_memory.py` - 清空全局记忆脚本
- `backend/migrations/add_memory_consolidation_fields.sql` - 数据库迁移脚本

### 修改文件
- `backend/app/social/agent_bridge.py` - 集成 UserMemoryManager 和自动整合逻辑
- `backend/app/social/memory_store.py` - 支持用户隔离和增量整合
- `backend/app/social/session_mapper.py` - 偏移量追踪
- `backend/app/social/models.py` - 数据库模型扩展
- `backend/app/channels/base.py` - 添加 bot_account 属性
- `backend/app/channels/weixin.py` - 保存和返回 bot_id
- `backend/app/channels/manager.py` - Channel 注册到 AgentBridge
- `backend/app/social/message_bus.py` - 添加 agent_bridge 引用
- `backend/app/main.py` - 设置 agent_bridge 和传递给 ChannelManager
- `backend/app/tools/social/remember_fact/tool.py` - 使用 UserMemoryManager
- `backend/app/tools/social/search_history/tool.py` - 使用 UserMemoryManager

## 部署步骤

### 1. 备份数据

```bash
# 备份社交数据
cp -r backend_data_registry/social backend_data_registry/social_backup_$(date +%Y%m%d_%H%M%S)
```

### 2. 清空全局记忆（可选）

```bash
# 运行清空脚本（会自动备份）
python scripts/clear_global_memory.py
```

### 3. 数据库迁移

```bash
# 进入后端目录
cd backend

# 执行迁移脚本
python -c "
from app.db.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # 添加新字段
    conn.execute(text('''
        ALTER TABLE social_session_mappings
        ADD COLUMN IF NOT EXISTS last_consolidated_offset INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS total_message_count INTEGER DEFAULT 0
    '''))
    conn.commit()
    print('Database migration completed')
"
```

或手动执行 SQL：

```sql
ALTER TABLE social_session_mappings
ADD COLUMN IF NOT EXISTS last_consolidated_offset INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_message_count INTEGER DEFAULT 0;
```

### 4. 重启服务

```bash
# 停止现有服务
pkill -f "uvicorn app.main:app"

# 启动服务
cd backend && python -m uvicorn app.main:app --reload
```

### 5. 验证功能

```bash
# 测试工具导入
cd backend
python -c "from app.tools.social.remember_fact.tool import RememberFactTool; from app.tools.social.search_history.tool import SearchHistoryTool; print('Import successful')"

# 查看日志
tail -f backend/logs/app.log | grep -E "user_memory|memory_consolidation"
```

## 验证测试

### 测试场景 1：单平台多机器人记忆隔离

```bash
# 1. 机器人A（wxid_abc）的用户123456发送消息
"记住我喜欢 PM2.5 数据分析"

# 2. 机器人B（wxid_def）的用户123456发送消息
"记住我喜欢 VOCs 数据分析"

# 3. 验证：两个用户的记忆独立
# 机器人A的用户123456搜索"PM2.5"应该找到
# 机器人B的用户123456搜索"VOCs"应该找到
# 机器人A的用户123456搜索"VOCs"应该找不到
```

### 测试场景 2：自动记忆整合

```bash
# 1. 用户连续发送 15 条消息
for i in range(15):
    send_message(f"消息 {i}")

# 2. 验证：第 11 条消息后触发整合
# 查看日志应显示 "memory_consolidation_triggered"
```

### 测试场景 3：Token 超限触发

```bash
# 1. 用户发送大量长文本
long_message = "测试内容" * 1000
for i in range(20):
    send_message(long_message)

# 2. 验证：自动触发整合
# 查看日志应显示 "memory_consolidation_triggered"
```

## 预期效果

- ✅ **单平台多机器人支持**：每个机器人账号的每个用户拥有独立记忆
- ✅ **跨平台用户隔离**：不同平台的用户记忆完全隔离
- ✅ **Token 自动整合**：超过 80% 上下文窗口或新增 10 条消息时自动触发
- ✅ **偏移量追踪**：避免重复整合相同内容
- ✅ **心跳服务完善**：定时任务正常执行和通知
- ✅ **并发安全**：多用户同时对话互不干扰
- ✅ **持久化存储**：记忆内容保存到磁盘，重启后恢复

## 故障排除

### 问题 1：工具导入失败

```bash
# 清理 Python 缓存
find backend/app/tools/social -name "__pycache__" -type d -exec rm -rf {} +
find backend/app/tools/social -name "*.pyc" -delete

# 重新测试
cd backend && python -c "from app.tools.social.remember_fact.tool import RememberFactTool; print('OK')"
```

### 问题 2：数据库迁移失败

```bash
# 检查数据库连接
python -c "
from app.db.database import engine
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print('Database connection OK')
"

# 手动执行 SQL
psql -h localhost -U your_user -d your_database -f backend/migrations/add_memory_consolidation_fields.sql
```

### 问题 3：记忆未自动整合

```bash
# 检查日志
tail -f backend/logs/app.log | grep -E "memory_consolidation|token_budget"

# 检查 session 映射
python -c "
import asyncio
from app.social.session_mapper import SessionMapper

async def check():
    mapper = SessionMapper()
    await mapper.load()
    info = await mapper.get_mapping_info('weixin:wxid_abc:123456')
    print(info)

asyncio.run(check())
"
```

## 注意事项

1. **数据备份**：部署前务必备份社交数据
2. **清空记忆**：建议清空现有全局记忆，所有用户从空白开始
3. **监控日志**：部署后密切关注日志，观察记忆整合是否正常触发
4. **性能监控**：Token 计算和记忆整合可能影响性能，需要监控响应时间

## 回滚方案

如果出现问题，可以按以下步骤回滚：

```bash
# 1. 停止服务
pkill -f "uvicorn app.main:app"

# 2. 恢复备份
rm -rf backend_data_registry/social
cp -r backend_data_registry/social_backup_* backend_data_registry/social

# 3. 回滚代码
git checkout HEAD~1

# 4. 重启服务
cd backend && python -m uvicorn app.main:app --reload
```

## 相关文档

- `backend/docs/multi_user_memory_architecture.md` - 架构设计文档
- `backend/docs/user_memory_api.md` - API 接口文档
- `CLAUDE.md` - 项目指南（包含社交模式说明）
