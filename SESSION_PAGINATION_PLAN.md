# 历史对话分段加载方案

## 问题分析

当前会话恢复机制一次性加载所有消息（可能数百条），导致：
- 后端SQL查询慢（无limit/offset）
- 网络传输慢（传输完整conversation_history）
- 前端渲染卡顿（一次性渲染所有消息）
- 内存占用高

## 设计方案：游标分页 + 滚动加载

### 核心思路

```
1. 首次加载：只加载最新 N 条消息（如 30 条）
2. 滚动到顶部：触发"加载更多"，获取更早的消息
3. 游标分页：用 sequence_number 做游标，避免 offset 性能问题
```

---

## 一、后端改动

### 1.1 新增分页加载 API

**文件**: `backend/app/api/session_routes.py`

新增端点：
```
GET /api/sessions/{session_id}/messages?before={seq_num}&limit=30
```

**参数**:
- `before`: 游标，加载 sequence_number < before 的消息（加载更早的消息）
- `limit`: 每次加载数量，默认 30
- 不传 `before` 时，返回最新的 N 条消息

**返回格式**:
```json
{
  "messages": [...],           // 消息数组（按 sequence_number 升序排列）
  "has_more": true,            // 是否还有更早的消息
  "oldest_sequence": 15,       // 本次返回的最小 sequence_number
  "total_count": 200           // 总消息数
}
```

### 1.2 数据库查询优化

**文件**: `backend/app/db/session_repository.py`

新增方法：
```python
async def get_messages_before(
    self,
    session_id: str,
    before_sequence: Optional[int] = None,
    limit: int = 30
) -> Dict[str, Any]:
    """游标分页获取消息"""
    async with AsyncSession(self.engine) as session:
        stmt = (
            select(SessionMessageDB)
            .where(SessionMessageDB.session_id == session_id)
        )

        # 游标过滤
        if before_sequence is not None:
            stmt = stmt.where(SessionMessageDB.sequence_number < before_sequence)

        # 降序取 limit 条，然后升序返回
        stmt = stmt.order_by(SessionMessageDB.sequence_number.desc()).limit(limit)
        result = await session.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        # 获取总数
        total_count = await self.get_message_count(session_id)

        # 判断是否有更多
        has_more = False
        if messages:
            oldest_seq = messages[0].sequence_number
            has_more = oldest_seq > 0

        return {
            "messages": [self._to_dict(msg) for msg in messages],
            "has_more": has_more,
            "oldest_sequence": messages[0].sequence_number if messages else None,
            "total_count": total_count
        }
```

### 1.3 会话恢复 API 优化

**文件**: `backend/app/api/session_routes.py`

修改 `restore_session` 端点，**不再返回完整 conversation_history**，改为只返回会话元数据 + 最新 N 条消息：

```python
@router.post("/{session_id}/restore")
async def restore_session(session_id: str, message_limit: int = 30):
    session_manager = get_session_manager()
    session = session_manager.load_session(session_id, include_messages=False)  # 不加载消息

    # 获取最新 N 条消息
    repo = get_session_repository()
    messages_result = await repo.get_messages_before(session_id, limit=message_limit)

    session_data = session.model_dump(mode='json')
    session_data["conversation_history"] = messages_result["messages"]
    session_data["has_more_messages"] = messages_result["has_more"]
    session_data["total_message_count"] = messages_result["total_count"]

    return {
        "session": session_data,
        "can_continue": session.state in [SessionState.ACTIVE, SessionState.PAUSED]
    }
```

---

## 二、前端改动

### 2.1 新增 API 调用

**文件**: `frontend/src/api/session.js`

```javascript
/**
 * 分页加载会话消息
 */
export async function getSessionMessages(sessionId, beforeSequence, limit = 30) {
  const params = new URLSearchParams()
  if (beforeSequence) params.set('before', beforeSequence)
  if (limit) params.set('limit', limit)
  return await request(`${BASE_URL}/${sessionId}/messages?${params}`)
}
```

### 2.2 Store 状态扩展

**文件**: `frontend/src/stores/reactStore.js`

在每个模式的 state 中新增分页状态：

```javascript
pagination: {
  hasMoreMessages: false,
  totalMessageCount: 0,
  oldestSequence: null,
  loadingMore: false
}
```

新增 actions：
```javascript
// 追加更早的消息（前置插入）
prependMessages(messages) {
  this.currentState.messages = [...messages, ...this.currentState.messages]
  this.currentState.pagination.oldestSequence = messages[0]?.sequence_number
}

// 设置分页状态
setPagination(state) {
  Object.assign(this.currentState.pagination, state)
}
```

### 2.3 消息列表组件

**文件**: `frontend/src/components/ReActMessageList.vue`

新增功能：
- 在消息列表顶部添加"加载更多"按钮/触发器
- 监听滚动事件，滚到顶部时自动触发加载
- 加载中的 loading 状态

```vue
<template>
  <div class="react-message-list" ref="messagesContainer">
    <!-- 加载更多按钮 -->
    <div v-if="pagination.hasMoreMessages" class="load-more-container">
      <button
        v-if="!pagination.loadingMore"
        @click="loadMoreMessages"
        class="load-more-btn"
      >
        加载更早的消息 ({{ pagination.totalMessageCount - messages.length }} 条)
      </button>
      <div v-else class="loading-indicator">
        <span class="spinner"></span> 加载中...
      </div>
    </div>

    <!-- 原有消息列表 -->
    <div v-for="(message, index) in filteredMessages" ... >
      ...
    </div>
  </div>
</template>
```

**滚动监听逻辑**：
```javascript
onMounted(() => {
  const container = messagesContainer.value
  container.addEventListener('scroll', handleScroll)
})

function handleScroll() {
  const container = messagesContainer.value
  if (container.scrollTop <= 50 && pagination.hasMoreMessages && !pagination.loadingMore) {
    loadMoreMessages()
  }
}

async function loadMoreMessages() {
  const prevState = { scrollTop: container.scrollHeight }

  pagination.loadingMore = true
  try {
    const result = await getSessionMessages(
      store.sessionId,
      pagination.oldestSequence,
      30
    )
    store.prependMessages(result.messages)
    store.setPagination({
      hasMoreMessages: result.has_more,
      oldestSequence: result.oldest_sequence,
      loadingMore: false
    })

    // 保持滚动位置（避免跳动）
    nextTick(() => {
      container.scrollTop = container.scrollHeight - prevState.scrollTop
    })
  } catch (error) {
    pagination.loadingMore = false
  }
}
```

### 2.4 会话恢复流程

**文件**: `frontend/src/views/ReactAnalysisView.vue`

现有流程不变，restoreSession 返回的数据中新增 `has_more_messages` 和 `total_message_count`，store 自动设置分页状态。

---

## 三、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/api/session_routes.py` | 修改 | 新增 `GET /{session_id}/messages` 端点，优化 restore 返回 |
| `backend/app/db/session_repository.py` | 修改 | 新增 `get_messages_before()` 游标分页方法 |
| `backend/app/agent/session/session_manager_db.py` | 修改 | `load_session` 支持 `include_messages=False` |
| `frontend/src/api/session.js` | 修改 | 新增 `getSessionMessages()` |
| `frontend/src/stores/reactStore.js` | 修改 | 新增 pagination 状态、prependMessages action |
| `frontend/src/components/ReActMessageList.vue` | 修改 | 新增加载更多按钮、滚动监听 |

---

## 四、性能预期

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 初始加载时间 | 200消息全部传输 | 30消息 (~1/7) |
| 内存占用 | 全量 | 按需增量 |
| 首屏渲染 | 卡顿 | 流畅 |
| 滚动加载 | 不支持 | 即时响应 |

---

## 五、注意事项

1. **保持向后兼容**：restore API 仍然可用，只是返回的消息变少了
2. **消息顺序**：返回的消息始终按 sequence_number 升序排列
3. **滚动位置保持**：加载更多后需保持当前可视位置不跳动
4. **加载更多时机**：点击按钮 或 滚动到顶部（可选，避免误触发）
