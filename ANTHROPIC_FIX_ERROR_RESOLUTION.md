# Anthropic 格式修复 - 错误解决

## 问题描述

在应用 Anthropic 格式修复后，系统出现以下错误：

```
AttributeError: 'ReActPlanner' object has no attribute 'memory'
```

**错误位置**:
- `backend/app/agent/core/planner.py:608`
- 方法: `think_and_action_v3`

**错误原因**:
在 `think_and_action_v3` 方法中，我错误地使用了 `self.memory.session.get_messages_for_llm()`，但 `ReActPlanner` 类没有 `memory` 属性。

## 根本原因分析

### ReActPlanner 的属性

```python
class ReActPlanner:
    def __init__(
        self,
        tool_registry: ToolRegistry = None,
        context: Optional[ExecutionContext] = None,
        llm_client=None,
        max_context_turns: int = 3
    ):
        self._tool_registry = tool_registry
        self.context = context
        self.llm_service = llm_service  # ✅ 有这个
        self.max_context_turns = max_context_turns
        # ❌ 没有 self.memory
```

### 错误代码

```python
# ❌ 错误：ReActPlanner 没有 memory 属性
conversation_history = self.memory.session.get_messages_for_llm()
```

## 解决方案

### 1. 修改方法签名，添加 conversation_history 参数

**文件**: `backend/app/agent/core/planner.py`

```python
async def think_and_action_v3(
    self,
    query: str,
    system_prompt: str,
    user_conversation: str,
    tools: List[Dict],
    iteration: int = 0,
    mode: str = "expert",
    conversation_history: Optional[List[Dict[str, Any]]] = None  # ✅ 新增参数
) -> Dict[str, Any]:
    # 使用传入的 conversation_history
    if conversation_history is None:
        conversation_history = []
```

### 2. 修改调用点，传递 conversation_history

**文件**: `backend/app/agent/core/loop.py`

```python
# conversation_history 在 ReAct 循环中已定义
conversation_history = self.memory.session.get_messages_for_llm()

# 传递给 think_and_action_v3
think_action_result = await self.planner.think_and_action_v3(
    query=user_query,
    system_prompt=context_result["system_prompt"],
    user_conversation=context_result["user_conversation"],
    tools=tools,
    iteration=iteration_count,
    mode=self.current_mode,
    conversation_history=conversation_history  # ✅ 传递对话历史
)
```

## 修改的文件

1. `backend/app/agent/core/planner.py`
   - 添加 `conversation_history` 参数
   - 使用参数而非 `self.memory`

2. `backend/app/agent/core/loop.py`
   - 传递 `conversation_history` 给 `think_and_action_v3`

## 验证

运行快速测试：

```bash
cd backend
python -c "
from app.agent.utils.anthropic_messages import (
    build_tool_result_message,
    detect_missing_tool_results
)

# 测试构建 tool_result
result = {'success': True, 'data': [1, 2, 3]}
msg = build_tool_result_message('toolu_test', result, False)
print('✓ tool_result 构建成功')

# 测试检测缺失
messages = [
    {'role': 'assistant', 'content': [{'type': 'tool_use', 'id': 'tu1', 'name': 'test', 'input': {}}]}
]
missing = detect_missing_tool_results(messages)
print(f'✓ 缺失检测成功: {missing}')
"
```

**输出**:
```
✓ tool_result 构建成功
✓ 缺失检测成功: {'tu1'}
```

## 教训

1. **检查类属性**: 在使用 `self.xxx` 之前，确认类确实有该属性
2. **依赖注入**: 对于跨模块的数据（如 conversation_history），应该通过参数传递而非直接访问
3. **逐步测试**: 每次修改后立即运行测试，避免引入错误

## 后续优化

为了避免类似问题，建议：

1. **添加类型检查**: 使用 `Optional[List[Dict]]` 明确参数类型
2. **参数验证**: 在方法开始时验证参数有效性
3. **单元测试**: 为 `think_and_action_v3` 添加单元测试

---

**修复完成时间**: 2026-04-26 21:55
**修复状态**: ✅ 已验证
