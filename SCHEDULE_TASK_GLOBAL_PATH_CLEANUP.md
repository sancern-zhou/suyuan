# 定时任务全局路径清理总结

## 修复时间
2026-04-28

## 问题背景

用户创建定时任务后，任务被写入全局路径 `backend_data_registry/social/heartbeat/HEARTBEAT.md`，但系统没有全局 HeartbeatService 读取这个文件，导致任务永远不会被执行。

**根本原因**：
1. `set_current_bot_account()` 没有被调用
2. `get_current_bot_account()` 返回 `None`
3. `schedule_task` 工具回退到 `user_id="global"`
4. 任务写入全局路径，但没有服务读取

## 修复内容

### 1. ✅ 扩展 `message_bus_singleton.py`
**文件**: `backend/app/social/message_bus_singleton.py`

```python
# 新增全局变量
_current_bot_account = None

# 新增函数
def set_current_bot_account(bot_account: str):
    """设置当前 bot_account（用于 social 模式）"""
    global _current_bot_account
    _current_bot_account = bot_account

def get_current_bot_account():
    """获取当前 bot_account"""
    return _current_bot_account

# 更新 clear_message_bus
def clear_message_bus():
    """清除全局 MessageBus 实例和上下文"""
    global _message_bus_instance, _current_chat_id, _current_channel, _current_bot_account
    # ... 包含 _current_bot_account 的清理
```

### 2. ✅ 修改 `AgentBridge._process_message`
**文件**: `backend/app/social/agent_bridge.py`

```python
# 设置 bot_account 到上下文
from app.social.message_bus_singleton import set_current_chat_id, set_current_channel, set_current_bot_account
set_current_chat_id(msg.chat_id)
set_current_channel(msg.channel)
set_current_bot_account(bot_account)  # ✅ 新增
```

### 3. ✅ 清理 `schedule_task/tool.py` 全局路径逻辑
**文件**: `backend/app/tools/social/schedule_task/tool.py`

**删除的内容**：
- ❌ `heartbeat_service` 参数（不再需要）
- ❌ `user_id = "global"` 默认值
- ❌ 降级到全局路径的逻辑
- ❌ `_write_to_heartbeat_file()` 方法

**修改后的逻辑**：
```python
# ✅ 强制要求用户上下文
if not self.user_heartbeat_manager:
    return {
        "status": "failed",
        "success": False,
        "summary": "定时任务功能需要用户登录才能使用"
    }

# ✅ 必须获取到有效的用户上下文
if not current_chat_id or not current_channel:
    return {
        "status": "failed",
        "success": False,
        "summary": "无法获取用户上下文，请确保在社交模式下使用此功能"
    }

# ✅ 使用真实 bot_account 构造 user_id
user_id = f"{current_channel}:{current_bot_account or 'default'}:{current_chat_id}"

# ✅ 只使用用户专属 HeartbeatService（不允许降级）
heartbeat = await self.user_heartbeat_manager.get_user_heartbeat(user_id)
heartbeat.add_task(...)
```

### 4. ✅ 删除全局 HEARTBEAT.md 文件
```bash
rm -f /home/xckj/suyuan/backend/backend_data_registry/social/heartbeat/HEARTBEAT.md
```

### 5. ✅ 其他 user_id 解析修复
**文件**: `backend/app/social/agent_bridge.py`
**文件**: `backend/app/social/subagent_manager.py`

```python
# ✅ 使用 rsplit(":", 2) 正确解析包含 ":" 的 channel
parts = user_id.rsplit(":", 2)
channel, bot_account, sender_id = parts
```

## 修复效果

### 修复前（❌ 有漏洞）
```
schedule_task 写入:
  user_id = "global"（因为 get_current_bot_account() 返回 None）
  → backend_data_registry/social/heartbeat/HEARTBEAT.md（全局路径）

HeartbeatService 读取:
  用户专属 HeartbeatService 读取用户专属路径
  → backend_data_registry/social/heartbeat/weixin_auto_mo427atx_userA/HEARTBEAT.md

结果：两个路径不一致，任务永远不会被执行 ❌
```

### 修复后（✅ 一致）
```
schedule_task 写入:
  user_id = "weixin:auto_mo427atx:auto_mo427atx:o9cq..."（使用真实 bot_account）
  → backend_data_registry/social/heartbeat/weixin_auto_mo427atx_auto_mo427atx_o9cq.../HEARTBEAT.md

HeartbeatService 读取:
  用户专属 HeartbeatService 读取同一路径
  → backend_data_registry/social/heartbeat/weixin_auto_mo427atx_auto_mo427atx_o9cq.../HEARTBEAT.md

结果：路径完全一致，任务正常执行 ✅
```

## 验证清单

- [x] `message_bus_singleton.py` 增加 `bot_account` 管理
- [x] `AgentBridge._process_message` 设置 `bot_account` 上下文
- [x] `schedule_task` 工具使用真实 `bot_account` 构造 `user_id`
- [x] `schedule_task` 工具删除全局路径降级逻辑
- [x] `schedule_task` 工具删除 `_write_to_heartbeat_file` 方法
- [x] 删除全局 HEARTBEAT.md 文件
- [x] `AgentBridge._on_heartbeat_notify` 使用 `rsplit(":", 2)` 解析
- [x] `SubagentManager` 使用 `rsplit(":", 2)` 提取 bot_account

## 用户操作建议

**重启服务**（让修改生效）：
```bash
# 如果使用 --reload 模式，修改会自动生效
# 否则需要重启后端服务
```

**重新创建定时任务**（旧任务在全局路径中，已失效）：
1. 删除旧的定时任务（如果需要）
2. 重新创建任务（使用修复后的代码）
3. 新任务会写入用户专属路径

## 注意事项

1. **不再支持全局路径**：所有定时任务都必须关联用户
2. **强制用户登录**：非社交模式下无法使用定时任务功能
3. **路径一致性**：`schedule_task` 写入路径 = `HeartbeatService` 读取路径
4. **bot_account 传递**：通过 `message_bus_singleton` 在工具调用间传递

## 相关文件

- `backend/app/social/message_bus_singleton.py` - bot_account 上下文管理
- `backend/app/social/agent_bridge.py` - 设置 bot_account 上下文
- `backend/app/tools/social/schedule_task/tool.py` - 定时任务创建工具
- `backend/app/social/user_heartbeat_manager.py` - 用户心跳管理器
- `backend/app/social/heartbeat_service.py` - 心跳服务实现
