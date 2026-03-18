# 重构后数据流分析：思考、工具调用、观察传递给LLM

## 数据流概览

```
LLM输出 → loop.py → SessionMemory → get_messages_for_llm() → LLM输入
  ↓
thought + action + observation
```

---

## ✅ 完整数据流验证

### 1. 思考（Thought）传递

**写入路径** (loop.py:688-705):
```python
# 格式化观察结果
full_message = self._format_observation(observation)

# 添加工具调用信息
action_info = self._format_action_info(action)
full_message = f"{action_info}\n\n{full_message}"

# 写入 SessionMemory（带 thought）
self.memory.session.add_assistant_message(full_message, thought=thought)
```

**存储格式** (session_memory.py:590-598):
```python
def _append_conversation_turn(self, role: str, content: str, thought: Optional[str] = None):
    self.conversation_history.append(
        ConversationTurn(
            role=role,
            content=content,  # 包含工具调用 + 观察结果
            timestamp=datetime.utcnow().isoformat(),
            thought=thought   # ✅ 存储 thought
        )
    )
```

**读取路径** (session_memory.py:630-639):
```python
messages = []
for turn in self.conversation_history:
    if turn.role == "assistant" and turn.thought:
        # ✅ 合并 thought 到 content
        content = f"## 思考\n{turn.thought}\n\n## 观察\n{turn.content}"
    else:
        content = turn.content
    messages.append({
        "role": turn.role,
        "content": content,  # ✅ 包含 thought + 观察
    })
```

**结论**: ✅ **思考内容完整传递给LLM**

---

### 2. 工具调用（Action）传递

**格式化方法** (loop.py:1872-1902):
```python
def _format_action_info(self, action: Dict[str, Any]) -> str:
    """格式化工具调用信息为字符串"""
    tool_name = action.get("tool", "")
    args = action.get("args", {})

    lines = [f"**调用工具**: {tool_name}"]

    if args:
        lines.append("**参数**:")
        for key, value in args.items():
            # 截断过长参数（保留前100字符）
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            lines.append(f"  - {key}: {value}")

    return "\n".join(lines)
```

**合并到观察结果** (loop.py:688-689):
```python
action_info = self._format_action_info(action)
full_message = f"{action_info}\n\n{full_message}"
```

**最终格式**:
```
**调用工具**: get_air_quality
**参数**:
  - city: 广州
  - start_date: 2026-01-01
  - end_date: 2026-01-31

**状态**: 成功
**数据引用**: air_quality:v1:xxx
**摘要**: 获取广州市1月份空气质量数据成功
```

**结论**: ✅ **工具调用信息完整传递给LLM**

---

### 3. 观察结果（Observation）传递

**格式化方法** (loop.py:1563-1768):
```python
def _format_observation(self, observation: Dict[str, Any]) -> str:
    """格式化观察结果为字符串"""
    lines = []

    # 1. 状态
    success = observation.get("success", False)
    lines.append(f"**状态**: {'成功' if success else '失败'}")

    # 2. 数据引用
    if "data_ref" in observation:
        lines.append(f"**数据引用**: {observation['data_ref']}")

    # 3. 错误信息
    if not success and "error" in observation:
        lines.append(f"**错误**: {observation['error']}")

    # 4. 并行工具执行结果
    if observation.get("parallel") and observation.get("tool_results"):
        # 递归格式化每个工具的结果
        ...

    # 5. 完整数据（bash、Office、图片分析等）
    if success and "data" in observation:
        data = observation["data"]
        # 根据工具类型显示完整内容
        if is_image_tool and "analysis" in data:
            lines.append(f"**完整分析结果**:\n{data['analysis']}")
        elif is_file_tool and "content" in data:
            lines.append(f"**文件内容**:\n{data['content']}")
        elif is_office_tool and "content" in data:
            lines.append(f"**文档内容**:\n```\n{data['content']}\n```")
        ...

    # 6. 摘要
    if "summary" in observation:
        lines.append(f"**摘要**: {observation['summary']}")

    return "\n".join(lines)
```

**结论**: ✅ **观察结果完整传递给LLM**

---

## 📊 完整示例

### 输入（LLM第N轮输出）
```json
{
  "thought": "需要查询广州市1月份的空气质量数据",
  "reasoning": "用户要求分析广州空气质量，首先需要获取监测数据",
  "action": {
    "type": "TOOL_CALL",
    "tool": "get_air_quality",
    "args": {
      "city": "广州",
      "start_date": "2026-01-01",
      "end_date": "2026-01-31"
    }
  }
}
```

### 存储（SessionMemory）
```python
ConversationTurn(
    role="assistant",
    thought="需要查询广州市1月份的空气质量数据",
    content="""**调用工具**: get_air_quality
**参数**:
  - city: 广州
  - start_date: 2026-01-01
  - end_date: 2026-01-31

**状态**: 成功
**数据引用**: air_quality:v1:abc123
**摘要**: 获取广州市1月份空气质量数据成功，共31天数据
""",
    timestamp="2026-02-18T00:00:00"
)
```

### 输出（LLM第N+1轮输入）
```
## 思考
需要查询广州市1月份的空气质量数据

## 观察
**调用工具**: get_air_quality
**参数**:
  - city: 广州
  - start_date: 2026-01-01
  - end_date: 2026-01-31

**状态**: 成功
**数据引用**: air_quality:v1:abc123
**摘要**: 获取广州市1月份空气质量数据成功，共31天数据
```

---

## 🎯 关键改进点

### 重构前的问题
- ❌ **thought 被存储但 LLM 永远读不到**
- ❌ WorkingMemory 和 SessionMemory 两套并行系统
- ❌ 数据流复杂，难以追踪

### 重构后的改进
- ✅ **thought 通过 `## 思考` 标记传递给 LLM**
- ✅ **工具调用信息通过 `_format_action_info()` 传递**
- ✅ **观察结果通过 `_format_observation()` 传递**
- ✅ **统一记忆路径：SessionMemory → get_messages_for_llm() → LLM**
- ✅ **数据流清晰：thought + action + observation 完整传递**

---

## 📝 验证方法

### 方法1：查看日志
```python
logger.debug(
    "get_messages_for_llm_success",
    session_id=self.session_id,
    history_length=len(self.conversation_history),
    messages_count=len(messages)
)
```

### 方法2：运行测试
```bash
cd backend
python test_refactoring.py
```

**测试结果**:
```
[OK] thought field correctly merged into content
[OK] thought field correctly parsed: Need to query weather data first...
```

### 方法3：检查实际请求
在 `llm_service.py` 中添加日志：
```python
logger.info("llm_chat_request_debug", messages=messages)
```

查看发送给 LLM 的实际消息内容。

---

## ✅ 结论

**重构后的数据流完整且正确**：

1. ✅ **思考（thought）**: 通过 `## 思考` 标记传递给 LLM
2. ✅ **工具调用（action）**: 通过 `_format_action_info()` 格式化后传递
3. ✅ **观察结果（observation）**: 通过 `_format_observation()` 格式化后传递

**所有内容都通过 SessionMemory.get_messages_for_llm() 统一传递给 LLM**，实现了：
- 连续推理质量提升（LLM 能读到上一轮的 thought）
- 数据流简化（单一记忆路径）
- 代码可维护性提升（清晰的数据流）
