# 知识问答连续对话优化方案

## 一、背景与目标

### 1.1 现状分析

当前知识问答 (`/api/knowledge-qa/stream`) 存在以下限制：

| 问题 | 描述 |
|------|------|
| 无会话记忆 | 每次请求都是独立对话，不记录历史 |
| 上下文丢失 | 追问时无法理解"它"、"这个"等指代 |
| 来源断裂 | 历史回答的来源信息无法追溯 |
| 会话管理缺失 | 无会话列表、无过期清理 |

### 1.2 优化目标

1. **连续对话**：支持多轮问答，理解上下文和指代
2. **历史存储**：PostgreSQL 持久化对话历史
3. **来源追溯**：保留每轮回答的参考来源
4. **会话管理**：支持会话列表、归档、删除
5. **智能清理**：自动过期清理，节省存储

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                              │
│  KnowledgeQAView.vue                                            │
│  - 传递 session_id                                               │
│  - 恢复历史对话                                                  │
│  - 显示来源信息                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     后端 API (FastAPI)                           │
│  routers/knowledge_qa.py                                        │
│  - 会话管理 (创建/获取/归档/删除)                                │
│  - 流式问答 (集成对话历史)                                       │
│  - 历史查询接口                                                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     服务层                                        │
│  knowledge_base/conversation_store.py                          │
│  - 对话存储服务 (PostgreSQL)                                    │
│  - 会话生命周期管理                                              │
│  - RAG 上下文构建                                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     数据层 (PostgreSQL)                          │
│  knowledge_conversation_sessions  - 会话表                      │
│  knowledge_conversation_turns     - 轮次表                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、数据库设计

### 3.1 ER 图

```
knowledge_conversation_sessions (会话表)
┌────────────────────────────────────────────────────────────┐
│ id: String(36)           PK  ←───→  session_id (FK)        │
│ title: String(256)       会话标题(首轮问题)                  │
│ status: Enum             ACTIVE/ARCHIVED/EXPIRED           │
│ knowledge_base_ids: JSON 使用的知识库列表                    │
│ total_turns: Integer     总轮次数                           │
│ last_query: Text         最后问题                           │
│ user_id: String(36)      用户ID(支持多用户)                 │
│ created_at: DateTime     创建时间                           │
│ updated_at: DateTime     更新时间                           │
│ expires_at: DateTime     过期时间                           │
└────────────────────────────────────────────────────────────┘
                              │ 1:N
                              ▼
knowledge_conversation_turns (轮次表)
┌────────────────────────────────────────────────────────────┐
│ id: String(36)           PK                                │
│ session_id: String(36)   FK → sessions.id                  │
│ turn_index: Integer      轮次序号(从1开始)                  │
│ role: String(20)         user / assistant                  │
│ content: Text            对话内容                           │
│ sources: JSON            参考来源(assistant)                │
│ sources_count: Integer   来源数量                           │
│ query_metadata: JSON     查询元数据(user)                   │
│ created_at: DateTime     创建时间                           │
└────────────────────────────────────────────────────────────┘
```

### 3.2 表结构详情

#### knowledge_conversation_sessions

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | 会话ID |
| title | VARCHAR(256) | - | 会话标题 |
| status | VARCHAR(20) | INDEX | ACTIVE/ARCHIVED/EXPIRED |
| knowledge_base_ids | JSON | - | 知识库ID列表 |
| total_turns | INTEGER | DEFAULT 0 | 总轮次数 |
| last_query | TEXT | - | 最后问题 |
| user_id | VARCHAR(36) | INDEX | 用户ID |
| created_at | DATETIME | INDEX | 创建时间 |
| updated_at | DATETIME | - | 更新时间 |
| expires_at | DATETIME | INDEX | 过期时间 |

#### knowledge_conversation_turns

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | VARCHAR(36) | PK | 轮次ID |
| session_id | VARCHAR(36) | FK → sessions | 会话ID |
| turn_index | INTEGER | NOT NULL | 轮次序号 |
| role | VARCHAR(20) | NOT NULL | user/assistant |
| content | TEXT | NOT NULL | 对话内容 |
| sources | JSON | DEFAULT [] | 参考来源 |
| sources_count | INTEGER | DEFAULT 0 | 来源数量 |
| query_metadata | JSON | DEFAULT {} | 查询元数据 |
| created_at | DATETIME | INDEX | 创建时间 |

### 3.3 索引设计

```sql
-- 会话表索引
CREATE INDEX idx_kcs_user_time ON knowledge_conversation_sessions(user_id, created_at DESC);
CREATE INDEX idx_kcs_status_time ON knowledge_conversation_sessions(status, updated_at DESC);
CREATE INDEX idx_kcs_expires ON knowledge_conversation_sessions(expires_at);

-- 轮次表索引
CREATE INDEX idx_kct_session_index ON knowledge_conversation_turns(session_id, turn_index);
CREATE INDEX idx_kct_created_at ON knowledge_conversation_turns(created_at DESC);
```

---

## 四、核心组件设计

### 4.1 对话存储服务 (conversation_store.py)

**位置**: `backend/app/knowledge_base/conversation_store.py`

**核心类**: `ConversationStore`

| 方法 | 功能 |
|------|------|
| `get_or_create_session()` | 获取或创建会话 |
| `add_turn()` | 添加对话轮次 |
| `get_recent_turns()` | 获取最近轮次 |
| `get_all_turns()` | 获取所有轮次 |
| `build_history_for_rag()` | 构建RAG格式历史 |
| `build_messages_for_llm()` | 构建LLM消息格式 |
| `archive_session()` | 归档会话 |
| `delete_session()` | 删除会话 |
| `list_user_sessions()` | 列出用户会话 |
| `_cleanup_expired_sessions()` | 清理过期会话 |

**配置参数**:

```python
{
    "session_ttl_hours": 12,      # 会话过期时间
    "max_turns_per_session": 50   # 每会话最大轮次
}
```

### 4.2 会话管理 API

**位置**: `backend/app/routers/knowledge_qa.py`

#### 新增接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/knowledge-qa/history/{session_id}` | 获取会话历史 |
| GET | `/api/knowledge-qa/history/{session_id}/recent` | 获取最近轮次 |
| DELETE | `/api/knowledge-qa/history/{session_id}` | 删除会话 |
| POST | `/api/knowledge-qa/history/{session_id}/archive` | 归档会话 |
| GET | `/api/knowledge-qa/history/list` | 列出用户会话 |

#### 修改接口

| 接口 | 修改内容 |
|------|----------|
| `POST /api/knowledge-qa/stream` | 支持 session_id 参数，集成对话历史 |

### 4.3 RAG Prompt 增强

**原有 Prompt**:

```
你是一个专业的知识问答助手。根据参考资料回答问题。
## 用户问题: {query}
## 参考资料: {contexts}
## 开始回答:
```

**增强后 Prompt**:

```
你是一个专业的知识问答助手。请根据参考资料和对话历史回答用户的问题。

## 回答要求
1. 优先使用参考资料中的信息进行回答
2. 如果参考资料中没有相关信息，请明确说明
3. 给出答案时，可以引用具体的参考资料来源
4. 保持回答简洁、准确、专业
5. 如果涉及多个来源的信息，请综合分析后给出答案

## 对话历史（重要 - 用户可能在追问）
=== 对话历史 ===
User: 问题1
Assistant: 回答1
User: 问题2
Assistant: 回答2

## 当前问题
{query}

## 参考资料
{contexts}

## 开始回答:
```

---

## 五、分阶段实施计划

### 第一阶段：数据库与模型 (预计 0.5 天)

#### 任务清单

| 序号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 1.1 | 创建对话模型文件 | `app/knowledge_base/models.py` | **已完成** |
| 1.2 | 创建数据库迁移脚本 | `app/alembic/versions/add_knowledge_conversation.py` | **已完成** |
| 1.3 | 注册模型到 Base | `app/knowledge_base/models.py` | **已完成** |
| 1.4 | 运行迁移创建表 | 数据库 | 待实施 |

#### 产出物

- [x] `knowledge_conversation_sessions` 表
- [x] `knowledge_conversation_turns` 表
- [x] 数据库迁移脚本

---

### 第二阶段：对话存储服务 (预计 0.5 天)

#### 任务清单

| 序号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 2.1 | 创建 conversation_store.py | `app/knowledge_base/conversation_store.py` | **已完成** |
| 2.2 | 实现会话CRUD方法 | 同上 | **已完成** |
| 2.3 | 实现 RAG 上下文构建 | 同上 | **已完成** |
| 2.4 | 实现过期清理逻辑 | 同上 | **已完成** |
| 2.5 | 添加单例获取函数 | 同上 | **已完成** |

#### 核心代码结构

```python
class ConversationStore:
    async def get_or_create_session(...) -> tuple[str, List, bool]
    async def add_turn(...) -> ConversationTurn
    async def get_recent_turns(...) -> List[ConversationTurn]
    def build_history_for_rag(...) -> str
    def build_messages_for_llm(...) -> List[Dict]
    async def archive_session(...) -> bool
    async def delete_session(...) -> bool
    async def _cleanup_expired_sessions(...)
```

#### 产出物

- [x] 对话存储服务类
- [ ] 单元测试（可选）

---

### 第三阶段：API 改造 (预计 0.5 天)

#### 任务清单

| 序号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 3.1 | 导入对话存储服务 | `routers/knowledge_qa.py` | **已完成** |
| 3.2 | 修改流式问答接口 | `POST /api/knowledge-qa/stream` | **已完成** |
| 3.3 | 添加会话管理接口 | GET/DELETE /history/* | **已完成** |
| 3.4 | 修改 Prompt 构建 | `build_rag_prompt()` | **已完成** |
| 3.5 | 添加对话保存逻辑 | `generate_streaming_answer()` | **已完成** |

#### 修改后的接口

```python
# 新增请求字段
class KnowledgeQARequest(BaseModel):
    query: str
    session_id: Optional[str]  # 新增：会话ID
    knowledge_base_ids: Optional[List[str]]
    top_k: int = 3
    score_threshold: Optional[float]
    use_reranker: bool = False
```

#### 产出物

- [x] 支持连续对话的流式接口
- [x] 6个会话管理 API
- [x] 增强的 RAG Prompt

---

### 第四阶段：前端适配 (预计 0.5 天)

#### 任务清单

| 序号 | 任务 | 文件 | 状态 |
|------|------|------|------|
| 4.1 | 传递 session_id | `KnowledgeQAView.vue` | **已完成** |
| 4.2 | 保存会话ID到本地 | localStorage | **已完成** |
| 4.3 | 页面加载恢复历史 | `onMounted()` | **已完成** |
| 4.4 | 显示历史来源信息 | `formatMessage()` | **已完成** |
| 4.5 | 添加会话管理UI | 侧边栏/设置页 | 可选 |

#### 代码变更

```javascript
// 1. 页面加载时恢复 session_id
onMounted(() => {
  sessionId.value = localStorage.getItem('kqa_session_id')
  if (sessionId.value) {
    loadHistory(sessionId.value)
  }
})

// 2. 发送时传递 session_id
await knowledgeQAStream(question, { session_id: sessionId.value, ... })

// 3. 收到 session_id 保存
if (eventData.type === 'start' && eventData.data.session_id) {
  sessionId.value = eventData.data.session_id
  localStorage.setItem('kqa_session_id', sessionId.value)
}
```

#### 产出物

- [x] 连续对话功能
- [x] 会话ID持久化
- [x] 历史来源展示

---

### 第五阶段：测试与优化 (预计 0.5 天)

#### 任务清单

| 序号 | 任务 | 描述 | 状态 |
|------|------|------|------|
| 5.1 | 单元测试 | 测试存储服务各方法 | 可选 |
| 5.2 | 集成测试 | 测试完整对话流程 | 待实施 |
| 5.3 | 性能测试 | 大会话量下的性能 | 待实施 |
| 5.4 | 过期清理测试 | 验证自动清理 | 待实施 |
| 5.5 | 问题修复 | 修复发现的问题 | 待实施 |

#### 测试用例

```python
# 对话存储测试
async def test_create_session():
    store = get_conversation_store()
    sid, turns, is_new = await store.get_or_create_session()
    assert is_new == True
    assert len(turns) == 0

async def test_add_turn():
    store = get_conversation_store()
    sid, _, _ = await store.get_or_create_session()
    turn = await store.add_turn(sid, "user", "测试问题")
    assert turn.role == "user"
    assert turn.content == "测试问题"

async def test_conversation_history():
    store = get_conversation_store()
    sid, _, _ = await store.get_or_create_session()
    await store.add_turn(sid, "user", "问题1")
    await store.add_turn(sid, "assistant", "回答1")
    turns = await store.get_all_turns(sid)
    assert len(turns) == 2
```

#### 产出物

- [ ] 测试报告
- [ ] 性能基准
- [ ] 问题修复记录

---

## 六、实施检查清单

### 实施前准备

- [ ] 备份现有数据库
- [ ] 通知相关人员（可选）
- [ ] 准备回滚方案

### 实施中

- [x] 第一阶段：数据库迁移
- [x] 第二阶段：存储服务
- [x] 第三阶段：API 改造
- [x] 第四阶段：前端适配
- [ ] 第五阶段：测试验证

### 实施后

- [ ] 功能验收
- [ ] 性能验证
- [ ] 文档更新
- [ ] 监控配置（可选）

---

## 七、风险与应对

| 风险 | 等级 | 应对措施 |
|------|------|----------|
| 迁移失败 | 中 | 提前备份，准备回滚脚本 |
| 性能下降 | 中 | 添加索引，优化查询 |
| 数据不一致 | 低 | 使用事务，保证原子性 |
| 前端兼容问题 | 低 | 渐进式升级，向后兼容 |

---

## 八、预期效果

### 优化前 vs 优化后

| 能力 | 优化前 | 优化后 |
|------|--------|--------|
| 连续对话 | 不支持 | 支持多轮问答 |
| 上下文理解 | 无 | 支持指代消解 |
| 来源追溯 | 当前轮次 | 完整历史 |
| 会话管理 | 无 | 列表/归档/删除 |
| 过期清理 | 无 | 12小时自动清理 |
| 存储方式 | 内存(丢失) | PostgreSQL(持久化) |

### 性能影响

| 指标 | 影响 |
|------|------|
| API 响应延迟 | 增加 ~10-50ms (数据库操作) |
| 存储增长 | 每会话约 1-5 KB/轮 |
| 查询性能 | 索引保障，O(log n) |

---

## 九、后续扩展 (可选)

1. **对话压缩**：长对话自动压缩摘要
2. **语义搜索**：支持历史对话语义检索
3. **多知识库切换**：会话绑定知识库
4. **导出功能**：导出对话记录为 Markdown
5. **敏感过滤**：敏感词自动过滤

---

## 十、相关文件索引

| 文件 | 路径 | 说明 | 状态 |
|------|------|------|------|
| 对话模型 | `app/knowledge_base/models.py` | 新增 ConversationSession 和 ConversationTurn 模型 | **已完成** |
| 对话存储服务 | `app/knowledge_base/conversation_store.py` | ConversationStore 服务类 | **已完成** |
| 路由改造 | `app/routers/knowledge_qa.py` | 集成对话历史 + 6个管理API | **已完成** |
| 前端 API | `frontend/src/api/knowledgeQA.js` | 新增会话管理API函数 | **已完成** |
| 前端页面 | `frontend/src/views/KnowledgeQAView.vue` | session_id 传递 + 历史恢复 | **已完成** |
| 数据库迁移 | `app/alembic/versions/add_knowledge_conversation.py` | 建表 SQL 脚本 | **已完成** |

---

*文档版本: v1.1*
*创建日期: 2026-01-06*
*更新日期: 2026-01-06*
*状态: Phase 1-4 已完成，待测试验证*
