# 历史对话存储机制问题分析与修复方案

## 问题分析

### 当前问题

用户报告：历史对话一直显示未完成，但用户已经切换页面，永远无法继续完成对话。

### 根本原因

**数据库查询结果**：
```
会话状态：ACTIVE（活跃）
消息数量：0
数据ID数量：0
可视化ID数量：0
```

**代码分析**：
1. `backend/app/agent/react_agent.py:357` - **唯一**调用 `save_session()` 的地方
2. 只在同步 `office_documents` 时才保存会话
3. **对话消息没有自动保存机制**

**问题流程**：
```
1. 用户发起查询
   ↓
2. 创建session记录（sessions表）- 立即保存
   ↓
3. 对话进行中...（消息只在内存中）
   ↓
4. 用户切换页面/刷新浏览器 ❌
   ↓
5. 对话中断，消息丢失！
   ↓
6. sessions表有记录，但session_messages表为空
   ↓
7. 历史对话显示"会话为空"
```

## 修复方案

### 方案1：前端页面关闭前保存（推荐，快速修复）

**实现位置**：`frontend/src/views/ReactAnalysisView.vue`

**核心逻辑**：
```javascript
// 在页面关闭/刷新前，调用后端保存接口
window.addEventListener('beforeunload', async () => {
  if (store.currentState.sessionId && store.currentState.messages.length > 0) {
    // 使用 navigator.sendBeacon 发送保存请求
    // (同步请求，确保在页面关闭前完成)
    navigator.sendBeacon('/api/sessions/save-current', JSON.stringify({
      session_id: store.currentState.sessionId,
      messages: store.currentState.messages,
      state: 'paused'  // 标记为暂停状态
    }))
  }
})
```

**优点**：
- ✅ 改动最小，只改前端
- ✅ 立即生效，无需数据库迁移
- ✅ 捕获大部分页面关闭场景

**缺点**：
- ❌ 无法处理浏览器崩溃等异常情况
- ❌ `beforeunload` 事件限制较多（不支持异步请求）
- ❌ 需要使用 `sendBeacon` API

---

### 方案2：后端定期自动保存（推荐，彻底解决）

**实现位置**：`backend/app/agent/react_agent.py`

**核心逻辑**：
```python
# 在 react_loop.run() 中，每N次迭代自动保存一次
async def run(self, ...):
    iteration_count = 0
    save_interval = 5  # 每5次迭代保存一次

    async for event in loop:
        iteration_count += 1

        # 定期保存会话消息
        if iteration_count % save_interval == 0:
            await self._auto_save_session(actual_session_id)

        yield event

async def _auto_save_session(self, session_id):
    """自动保存会话消息"""
    try:
        session = await session_manager.load_session(session_id)
        if session:
            # 更新对话历史
            session.conversation_history = memory_manager.session.get_messages_for_llm()
            session.state = SessionState.ACTIVE  # 保持活跃状态
            await session_manager.save_session(session)
            logger.info("session_auto_saved", session_id=session_id)
    except Exception as e:
        logger.warning("session_auto_save_failed", session_id=session_id, error=str(e))
```

**优点**：
- ✅ 彻底解决问题，消息不会丢失
- ✅ 即使浏览器崩溃也能恢复部分对话
- ✅ 支持断点续传功能

**缺点**：
- ❌ 改动较大，需要修改后端核心逻辑
- ❌ 增加数据库写入频率

---

### 方案3：前端心跳机制（推荐，平衡方案）

**实现位置**：
- 前端：`frontend/src/views/ReactAnalysisView.vue`
- 后端：`backend/app/api/session_routes.py`

**核心逻辑**：

**前端**：
```javascript
// 每30秒发送一次心跳，自动保存会话
const SAVE_INTERVAL = 30000  // 30秒

let saveTimer = null

const startAutoSave = () => {
  saveTimer = setInterval(async () => {
    if (store.currentState.sessionId && store.currentState.isAnalyzing) {
      await saveCurrentSession()
    }
  }, SAVE_INTERVAL)
}

const stopAutoSave = () => {
  if (saveTimer) {
    clearInterval(saveTimer)
    saveTimer = null
  }
}

const saveCurrentSession = async () => {
  try {
    await fetch('/api/sessions/auto-save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: store.currentState.sessionId,
        messages: store.currentState.messages,
        state: store.currentState.isComplete ? 'completed' : 'active'
      })
    })
  } catch (error) {
    console.warn('自动保存失败:', error)
  }
}

onMounted(() => {
  startAutoSave()
})

onUnmounted(() => {
  stopAutoSave()
  // 页面卸载时保存一次
  saveCurrentSession()
})
```

**后端**：
```python
@router.post("/auto-save")
async def auto_save_session(request: Request):
    """自动保存会话消息"""
    data = await request.json()
    session_id = data.get("session_id")
    messages = data.get("messages", [])
    state = data.get("state", "active")

    session_manager = get_session_manager()
    session = await session_manager.load_session(session_id)

    if session:
        session.conversation_history = messages
        session.state = SessionState(state)
        await session_manager.save_session(session)

    return {"status": "ok"}
```

**优点**：
- ✅ 定期保存，不会丢失太多消息
- ✅ 改动适中，前后端都需要修改
- ✅ 支持断点续传
- ✅ 可以控制保存频率

**缺点**：
- ❌ 增加网络请求频率
- ❌ 需要前后端配合修改

---

## 推荐实施计划

### 第一阶段：快速修复（方案1）

**目标**：解决页面关闭时消息丢失问题

**实施步骤**：
1. 前端添加 `beforeunload` 事件监听
2. 使用 `navigator.sendBeacon` 发送保存请求
3. 后端添加 `/api/sessions/save-current` 接口

**预计工作量**：1-2小时

---

### 第二阶段：彻底解决（方案3）

**目标**：实现定期自动保存，支持断点续传

**实施步骤**：
1. 前端实现心跳机制（每30秒保存一次）
2. 后端添加 `/api/sessions/auto-save` 接口
3. 优化保存逻辑，避免重复保存

**预计工作量**：3-4小时

---

## 长期优化建议

1. **消息队列机制**：使用消息队列缓冲消息，定期批量写入数据库
2. **本地存储备份**：使用 `localStorage` 备份消息，页面恢复时同步到服务器
3. **增量保存**：只保存新增的消息，减少数据传输量
4. **状态同步**：实现WebSocket实时同步，支持多设备同时访问

---

## 总结

**当前问题**：
- ❌ 对话消息只在正常完成时保存
- ❌ 用户中途切换页面，消息永久丢失
- ❌ 历史对话显示"会话为空"

**推荐方案**：
- ✅ **短期**：方案1（页面关闭前保存）
- ✅ **长期**：方案3（定期自动保存）

**预期效果**：
- ✅ 对话消息不再丢失
- ✅ 历史对话可以正常恢复
- ✅ 支持断点续传功能
