# 定时任务多用户隔离修复 - 实施总结

## 实施完成状态

### 已完成的核心组件

#### 1. UserHeartbeatManager (新增)
- **文件**: `backend/app/social/user_heartbeat_manager.py`
- **功能**:
  - LRU缓存管理（最多100个用户）
  - 用户专属工作空间初始化
  - 线程安全（asyncio.Lock）
  - 支持回调函数（on_execute, on_notify）
- **用户ID格式**: `{channel}:{bot_account}:{sender_id}`

#### 2. HeartbeatService 改造
- **文件**: `backend/app/social/heartbeat_service.py`
- **修改**:
  - 添加 `user_id` 参数（默认 "global"）
  - 更新日志记录包含 user_id
  - 在执行结果中传递 user_id 给通知回调

#### 3. AgentBridge 改造
- **文件**: `backend/app/social/agent_bridge.py`
- **修改**:
  - 替换 `self.heartbeat` 为 `self.user_heartbeat_manager`
  - 实现 `_on_heartbeat_notify` 发送通知到 MessageBus
  - 支持解析 user_id 格式并提取 channel/chat_id
  - 移除全局 HeartbeatService 启动（改为按用户启动）

#### 4. ScheduleTaskTool 改造
- **文件**: `backend/app/tools/social/schedule_task/tool.py`
- **修改**:
  - 添加 `user_heartbeat_manager` 参数支持
  - 从 message_bus_singleton 获取当前 chat_id 和 channel
  - 构造用户专属 user_id
  - 支持降级到直接写入文件

#### 5. UserHeartbeatSingleton (新增)
- **文件**: `backend/app/social/user_heartbeat_singleton.py`
- **功能**:
  - 全局单例存储 UserHeartbeatManager
  - 供 ScheduleTaskTool 访问

### 目录结构

```
backend_data_registry/social/heartbeat/
├── HEARTBEAT.md                    # 全局任务（向后兼容）
├── HEARTBEAT.md.bak                # 备份文件（需手动创建）
├── HEARTBEAT.md.clean              # 清洁版本模板
├── weixin_default_user123/         # 用户专属目录（示例）
│   └── HEARTBEAT.md
└── qq_qqbot_user456/               # 用户专属目录（示例）
    └── HEARTBEAT.md
```

## 通知机制实现

### 通知流程

1. **心跳触发**: HeartbeatService 定期检查任务
2. **执行任务**: 调用 `_on_heartbeat_execute` 回调
3. **生成结果**: 返回执行结果（包含 summary）
4. **发送通知**: 调用 `_on_heartbeat_notify` 回调
5. **解析用户ID**: 从 user_id 提取 channel 和 chat_id
6. **推送消息**: 通过 MessageBus 发送 OutboundMessage

### 通知消息格式

```
【定时任务通知】

{任务执行结果摘要}
```

## 向后兼容性

1. **全局任务保留**: user_id="global" 使用原有 HEARTBEAT.md
2. **降级方案**: ScheduleTaskTool 在没有 UserHeartbeatManager 时直接写入文件
3. **现有数据**: 全局 HEARTBEAT.md 中的任务保留

## 测试验证

### 单元测试（建议添加）

```python
# backend/tests/social/test_user_heartbeat_manager.py

@pytest.mark.asyncio
async def test_user_heartbeat_isolation():
    """测试用户心跳隔离"""
    manager = UserHeartbeatManager()

    heartbeat1 = await manager.get_user_heartbeat("weixin:bot1:user123")
    heartbeat2 = await manager.get_user_heartbeat("weixin:bot1:user456")

    assert heartbeat1.workspace != heartbeat2.workspace
    assert "weixin_bot1_user123" in str(heartbeat1.workspace)
    assert heartbeat1.heartbeat_file != heartbeat2.heartbeat_file

@pytest.mark.asyncio
async def test_global_mode_compatibility():
    """测试全局模式向后兼容"""
    manager = UserHeartbeatManager()
    global_heartbeat = await manager.get_user_heartbeat("global")

    assert global_heartbeat.workspace == manager.base_workspace
```

### 集成测试（建议添加）

```python
# backend/tests/social/test_heartbeat_integration.py

@pytest.mark.asyncio
async def test_end_to_end_task_creation():
    """端到端测试：任务创建"""
    bridge = AgentBridge(..., enable_heartbeat=True)
    await bridge.start()

    inbound_msg = InboundMessage(
        channel="weixin",
        sender_id="user123",
        chat_id="user123",
        content="创建一个每天早上9点的空气质量报告任务"
    )

    await bridge._process_message(inbound_msg)

    user_file = Path("backend_data_registry/social/heartbeat/weixin_default_user123/HEARTBEAT.md")
    assert user_file.exists()
    content = user_file.read_text()
    assert "空气质量报告" in content
```

## 手动测试流程

1. **启动服务**
```bash
cd backend && python -m uvicorn app.main:app --reload
```

2. **创建任务**
- 通过微信发送："创建一个每5分钟发送测试消息的任务"

3. **验证隔离**
```bash
ls backend_data_registry/social/heartbeat/
# 应该看到用户专属目录创建
```

4. **验证通知**
- 等待任务执行
- 确认收到通知消息

## 待办事项

### 高优先级（必须）

- [ ] 清理现有 HEARTBEAT.md 文件（替换为 HEARTBEAT.md.clean）
- [ ] 测试通知机制是否正常工作
- [ ] 验证用户隔离是否有效

### 中优先级（推荐）

- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 添加任务管理 API（查询、删除任务）

### 低优先级（可选）

- [ ] 实现任务迁移工具（全局→用户）
- [ ] 集成 SimpleScheduler（更强大的调度能力）
- [ ] 添加任务执行历史记录

## 数据清理建议

### 清理 HEARTBEAT.md

当前 HEARTBEAT.md 包含 176 个重复任务，建议清理：

```bash
# 1. 备份现有文件（需要 sudo 权限）
sudo cp backend_data_registry/social/heartbeat/HEARTBEAT.md \
        backend_data_registry/social/heartbeat/HEARTBEAT.md.bak

# 2. 替换为清洁版本
sudo cp backend_data_registry/social/heartbeat/HEARTBEAT.md.clean \
        backend_data_registry/social/heartbeat/HEARTBEAT.md
```

### 清理用户目录

定期清理不活跃用户目录：

```bash
# 查看所有用户目录
ls backend_data_registry/social/heartbeat/

# 删除不活跃用户目录（谨慎操作）
sudo rm -rf backend_data_registry/social/heartbeat/weixin_default_inactive_user
```

## 故障排查

### 问题：通知未发送

**检查点**:
1. user_id 格式是否正确（包含 3 个部分）
2. MessageBus 是否正常工作
3. 通知回调是否正确实现

**调试命令**:
```python
# 检查 user_id
parts = user_id.split(":")
assert len(parts) >= 3, f"Invalid user_id: {user_id}"

# 检查通知日志
logger.info("heartbeat_notification", response=response, user_id=user_id)
```

### 问题：任务未创建

**检查点**:
1. UserHeartbeatManager 是否正确初始化
2. message_bus_singleton 是否正确设置 chat_id 和 channel
3. 文件权限是否正确

**调试命令**:
```bash
# 检查目录权限
ls -la backend_data_registry/social/heartbeat/

# 检查文件内容
cat backend_data_registry/social/heartbeat/*/HEARTBEAT.md
```

## 文件变更清单

### 新增文件
- `backend/app/social/user_heartbeat_manager.py` - 用户心跳管理器
- `backend/app/social/user_heartbeat_singleton.py` - 全局单例
- `backend_data_registry/social/heartbeat/HEARTBEAT.md.clean` - 清洁模板

### 修改文件
- `backend/app/social/heartbeat_service.py` - 添加 user_id 参数
- `backend/app/social/agent_bridge.py` - 集成 UserHeartbeatManager
- `backend/app/tools/social/schedule_task/tool.py` - 支持用户专属任务

### 待清理文件
- `backend_data_registry/social/heartbeat/HEARTBEAT.md` - 需要替换为清洁版本

## 总结

本次实施完成了定时任务系统的多用户隔离改造，实现了：

1. ✅ 完全的用户级任务隔离
2. ✅ LRU 缓存优化（最多 100 个用户）
3. ✅ 通知机制实现
4. ✅ 向后兼容性保留
5. ✅ 降级方案支持

核心架构遵循 UserMemoryManager 模式，确保了代码一致性和可维护性。
