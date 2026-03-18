# LobsterAI 历史对话处理 - 简单有效的方法

## LobsterAI 的做法

### 核心代码（`coworkRunner.ts`）

#### 1. 定义限制常量（第64-66行）

```typescript
const SANDBOX_HISTORY_MAX_MESSAGES = 24;        // 最多 24 条消息
const SANDBOX_HISTORY_MAX_TOTAL_CHARS = 32000;  // 最多 32000 个字符
const SANDBOX_HISTORY_MAX_MESSAGE_CHARS = 4000; // 每条消息最多 4000 字符
```

**就这么简单**：
- 两个数字限制（消息数量 + 字符数）
- 没有复杂的算法

---

#### 2. 构建历史块（第1324-1367行）

```typescript
private buildSandboxHistoryBlocks(messages: CoworkMessage[], currentPrompt: string): string[] {
  const history = [...messages];

  // 去重：如果最后一条是当前问题，移除（避免重复）
  const last = history[history.length - 1];
  if (last?.type === 'user' && last.content.trim() === currentPrompt.trim()) {
    history.pop();
  }

  const selectedFromNewest: string[] = [];
  let totalChars = 0;

  // ✅ 从最新消息开始反向遍历
  for (let i = history.length - 1; i >= 0; i--) {
    // 限制1：最多 N 条消息
    if (selectedFromNewest.length >= SANDBOX_HISTORY_MAX_MESSAGES) {
      break;
    }

    const block = this.formatSandboxHistoryMessage(history[i]);
    if (!block) continue;

    // 限制2：总字符数
    const nextTotal = totalChars + block.length;
    if (nextTotal > SANDBOX_HISTORY_MAX_TOTAL_CHARS) {
      // 如果是第一条，截断而不是丢弃
      if (selectedFromNewest.length === 0) {
        const truncated = this.truncateSandboxHistoryContent(block, SANDBOX_HISTORY_MAX_TOTAL_CHARS);
        if (truncated) {
          selectedFromNewest.push(truncated);
        }
      }
      break;
    }

    selectedFromNewest.push(block);
    totalChars = nextTotal;
  }

  // ✅ 反转数组（恢复时间顺序：旧 → 新）
  return selectedFromNewest.reverse();
}
```

**关键点**：
1. **从最新开始**：`for (let i = history.length - 1; i >= 0; i--)`
2. **双重限制**：消息数量 + 字符数
3. **最后反转**：保持时间顺序
4. **去重逻辑**：移除重复的当前问题

---

#### 3. 注入提示词（第1369-1391行）

```typescript
private injectSandboxHistoryPrompt(sessionId: string, currentPrompt: string, effectivePrompt: string): string {
  const historyBlocks = this.buildSandboxHistoryBlocks(session.messages, currentPrompt);
  if (historyBlocks.length === 0) {
    return effectivePrompt;
  }

  return [
    'The sandbox VM was restarted. Continue using the reconstructed conversation context below.',
    'Use this context for continuity and do not quote it unless necessary.',
    '<conversation_history>',
    ...historyBlocks,  // ✅ 插入历史消息
    '</conversation_history>',
    '',
    '<current_user_request>',
    effectivePrompt,  // ✅ 当前问题
    '</current_user_request>',
  ].join('\n');
}
```

**关键点**：
- 清晰的结构：XML 标签分隔
- 历史与当前分离
- 简单的文本拼接

---

## LobsterAI 方案的核心思想

### 1. 简单粗暴的限制

```
┌─────────────────────────────┐
│  历史消息池（所有历史）        │
└─────────────────────────────┘
              ↓
┌─────────────────────────────┐
│  从最新开始反向选择           │
│  - 最多 24 条                │
│  - 最多 32000 字符           │
└─────────────────────────────┘
              ↓
┌─────────────────────────────┐
│  保留的历史（最近 24 条）     │
└─────────────────────────────┘
```

### 2. 两个限制足够了

**不需要**：
- ❌ 任务边界检测
- ❌ 语义相似度分析
- ❌ 去重机制（除了当前问题）
- ❌ 重要性评分

**只需要**：
- ✅ 消息数量限制
- ✅ 字符数量限制
- ✅ 从最新开始选择

### 3. 为什么这样有效？

**对话的自然属性**：
- 最近的对话最相关
- 太早的历史通常不相关
- Context window 有限

**KISS 原则**：
> "Keep It Simple, Stupid"
>
> 简单的方案往往是最有效的

---

## 对比当前项目的问题

### 当前项目的做法

```python
def get_messages_for_llm(self):
    messages = []
    for turn in self.conversation_history:  # ❌ 遍历所有历史
        messages.append(...)
    return messages  # ❌ 返回所有 36 条
```

**问题**：
- 无限制地返回所有历史
- 导致 36 条消息全部传递给 LLM

### LobsterAI 的做法

```python
def get_messages_for_llm(self):
    MAX_MESSAGES = 24  # ✅ 常量限制
    MAX_CHARS = 32000   # ✅ 常量限制

    selected = []
    total_chars = 0

    # ✅ 从最新开始反向选择
    for turn in reversed(self.conversation_history):
        if len(selected) >= MAX_MESSAGES:
            break
        if total_chars + len(turn.content) > MAX_CHARS:
            break

        selected.append(turn)
        total_chars += len(turn.content)

    # ✅ 反转数组（恢复时间顺序）
    selected.reverse()
    return self._convert_to_llm_format(selected)
```

---

## 实施建议

### 修改 `session_memory.py`

```python
class SessionMemory:
    # ✅ 定义常量（在类级别）
    MAX_HISTORY_TURNS = 24          # 最多 24 条消息
    MAX_HISTORY_CHARS = 32000      # 最多 32000 个字符

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """
        返回 LLM 格式的对话历史

        限制：
        - 最多 MAX_HISTORY_TURNS 条消息
        - 最多 MAX_HISTORY_CHARS 个字符
        - 从最新消息开始选择
        """
        if not self.conversation_history:
            return []

        selected_turns = []
        total_chars = 0

        # ✅ 从最新开始反向选择
        for turn in reversed(self.conversation_history):
            # 限制1：消息数量
            if len(selected_turns) >= self.MAX_HISTORY_TURNS:
                break

            content = turn.content
            # 限制2：字符数量
            if total_chars + len(content) > self.MAX_HISTORY_CHARS:
                break

            selected_turns.append(turn)
            total_chars += len(content)

        # ✅ 反转数组（恢复时间顺序）
        selected_turns.reverse()

        # 转换为 LLM 格式
        messages = []
        for turn in selected_turns:
            # ... 现有的转换逻辑
            pass

        logger.info(
            "get_messages_for_llm_success",
            session_id=self.session_id,
            total_turns=len(self.conversation_history),
            selected_turns=len(selected_turns),
            total_chars=total_chars,
            messages_count=len(messages)
        )

        return messages
```

---

## 总结

### LobsterAI 的方法

**简单**：两个常量限制（消息数 + 字符数）
**有效**：从最新开始反向选择
**实用**：无复杂算法，易于理解和维护

### 核心代码（60 行）

```typescript
// 1. 定义限制
const MAX_MESSAGES = 24;
const MAX_CHARS = 32000;

// 2. 从最新开始选择
for (let i = messages.length - 1; i >= 0; i--) {
  if (count >= MAX_MESSAGES || chars > MAX_CHARS) break;
  selected.push(messages[i]);
}

// 3. 反转数组
selected.reverse();
```

### 为什么不需要复杂方案？

1. **对话的自然属性**：最近的对话最相关
2. **LLM 的短期记忆**：20-30 条消息足够
3. **KISS 原则**：简单的方案最有效

### 对比

| 方案 | 代码行数 | 复杂度 | 效果 |
|------|---------|--------|------|
| **LobsterAI** | 60 行 | 🟢 低 | ⭐⭐⭐⭐⭐ |
| 我之前的方案 | 500+ 行 | 🔴 高 | ⭐⭐⭐⭐ |

**结论**：LobsterAI 的方法更简单、更实用。

**原则**：
> "Don't overthink it"
>
> 大多数问题都可以用简单的方法解决
