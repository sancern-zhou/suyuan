# Anthropic 格式修复总结

## 修复日期
2026-04-26

## 问题描述

suyuan 项目虽然声称支持 Anthropic 格式，但实现不完整：
- ❌ 只在解析 LLM 响应时使用 `content_block` 概念
- ❌ 工具执行结果仍以 JSON 文本方式传递
- ❌ 没有构建结构化的 `tool_result` 消息
- ❌ 无法享受 Anthropic API 的原生工具调用优势

## 修复内容

### 1. 创建 Anthropic 消息格式工具模块

**文件**: `backend/app/agent/utils/anthropic_messages.py`

**核心功能**:
```python
# 构建 tool_result 消息
def build_tool_result_message(tool_use_id, result, is_error=False)
→ 返回 Anthropic 格式的 tool_result 消息

# 检测缺失的 tool_result
def detect_missing_tool_results(messages)
→ 返回缺失的 tool_use_id 集合

# 生成缺失的 tool_result 消息
def generate_missing_tool_result_messages(assistant_messages, error_message)
→ 为缺失的 tool_result 生成错误消息

# 提取 tool_use blocks
def extract_tool_use_blocks(assistant_message)
→ 从 assistant 消息中提取 tool_use blocks

# 验证消息格式
def validate_anthropic_message(message)
→ 验证消息是否符合 Anthropic 格式
```

### 2. 扩展 SessionMemory 支持 Anthropic 格式

**文件**: `backend/app/agent/memory/session_memory.py`

**修改**:
```python
@dataclass
class ConversationTurn:
    role: str
    content: str | List[Dict[str, Any]]  # ✅ 支持 Anthropic content blocks
    tool_use_id: Optional[str] = None     # ✅ Anthropic: tool_use.id
    is_error: Optional[bool] = None       # ✅ Anthropic: is_error 标记
```

**新增方法**:
```python
def add_tool_result_message(tool_use_id, result, is_error=False)
→ 添加 Anthropic 格式的 tool_result 消息到对话历史
```

**修改方法**:
```python
def get_messages_for_llm()
→ ✅ 支持返回 Anthropic content block 格式的消息
```

### 3. 修改 ReAct Loop 构建 tool_result 消息

**文件**: `backend/app/agent/core/loop.py`

**修改位置**: `_observe` 方法（第 1583 行）

**修改内容**:
```python
# ✅ Anthropic Format: 构建 tool_result 消息（如果启用）
from config.settings import settings

if settings.use_anthropic_format and "tool_call_id" in action:
    tool_call_id = action["tool_call_id"]

    # 构建 Anthropic tool_result 消息
    is_error = not observation.get("success", False)

    # 添加到对话历史
    self.memory.session.add_tool_result_message(
        tool_use_id=tool_call_id,
        result=observation,
        is_error=is_error
    )
```

### 4. 修改 Planner 检测缺失 tool_result

**文件**: `backend/app/agent/core/planner.py`

**修改位置**: `think_and_action_v3` 方法（第 577 行）

**修改内容**:
```python
# ✅ 获取完整的对话历史（Anthropic 格式）
conversation_history = self.memory.session.get_messages_for_llm()

# ✅ 检测并修复缺失的 tool_result
from app.agent.utils.anthropic_messages import (
    detect_missing_tool_results,
    generate_missing_tool_result_messages
)

missing_tool_use_ids = detect_missing_tool_results(conversation_history)
if missing_tool_use_ids:
    # 生成缺失的 tool_result 消息
    missing_messages = generate_missing_tool_result_messages(
        assistant_messages[-5:],
        error_message="工具执行被中断或失败"
    )

    # 添加到对话历史
    conversation_history.extend(missing_messages)

# 使用完整的对话历史调用 LLM
messages = conversation_history + [
    {"role": "user", "content": user_conversation}
]
```

## 修复效果

### 修复前
```python
# ❌ 工具执行结果作为 JSON 文本传递
observation = {"success": True, "data": {...}, "summary": "..."}
formatted_observation = json.dumps(observation, ensure_ascii=False, indent=2)

# 添加到对话历史（普通文本）
self.memory.add_observation_message(observation)
```

### 修复后
```python
# ✅ 构建 Anthropic tool_result 消息
tool_result_message = {
    "role": "user",
    "content": [{
        "type": "tool_result",
        "content": "{...}",  # JSON 字符串
        "is_error": False,
        "tool_use_id": "toolu_xxx"
    }]
}

# 添加到对话历史（结构化格式）
self.memory.session.add_tool_result_message(
    tool_use_id="toolu_xxx",
    result=observation,
    is_error=False
)
```

## 测试验证

**测试文件**: `backend/tests/test_anthropic_format_fix.py`

**测试覆盖**:
- ✅ tool_result 消息构建（成功/错误）
- ✅ 缺失 tool_result 检测
- ✅ 生成缺失 tool_result 消息
- ✅ 提取 tool_use blocks
- ✅ Anthropic 消息格式验证
- ✅ 完整工作流

**测试结果**:
```
============================================================
✅ 所有测试通过！
============================================================
```

## 与原生 Claude Code 对比

| 功能 | 原生 Claude Code | suyuan (修复前) | suyuan (修复后) |
|------|-----------------|-----------------|-----------------|
| tool_result 构建 | ✅ 完整实现 | ❌ 未实现 | ✅ 完整实现 |
| tool_use_id 关联 | ✅ 严格关联 | ❌ 仅追踪 | ✅ 严格关联 |
| content block 支持 | ✅ 多种类型 | ❌ 仅解析 | ✅ 构建和解析 |
| 缺失 tool_result 检测 | ✅ 自动修复 | ❌ 未实现 | ✅ 自动修复 |
| 错误处理 | ✅ is_error 标记 | ❌ JSON 文本 | ✅ is_error 标记 |

## 使用说明

### 启用 Anthropic 格式

确保 `.env` 文件中设置：
```bash
USE_ANTHROPIC_FORMAT=true
```

### 验证功能

运行测试：
```bash
cd backend
PYTHONPATH=/home/xckj/suyuan/backend python tests/test_anthropic_format_fix.py
```

### 消息格式示例

**tool_use 消息**（LLM 返回）:
```json
{
  "role": "assistant",
  "content": [
    {"type": "text", "text": "我将查询天气"},
    {
      "type": "tool_use",
      "id": "toolu_abc123",
      "name": "get_weather",
      "input": {"city": "北京"}
    }
  ]
}
```

**tool_result 消息**（工具返回）:
```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "content": "{\"success\": true, \"data\": {...}}",
      "is_error": false,
      "tool_use_id": "toolu_abc123"
    }
  ]
}
```

## 注意事项

1. **向后兼容**: 修复保持了向后兼容性，未启用 `USE_ANTHROPIC_FORMAT` 时仍使用旧格式
2. **性能影响**: 添加的消息格式转换开销极小，不影响性能
3. **降级策略**: V3 规划器失败时自动降级到 V2，确保系统稳定

## 后续优化建议

1. **支持更多 content block 类型**: 图片、文件等
2. **优化消息压缩**: 基于 Anthropic content block 的智能压缩
3. **增强错误处理**: 更细粒度的错误分类和处理
4. **性能监控**: 添加 tool_result 构建的性能指标

## 相关文档

- `ANTHROPIC_FORMAT_QUICK_REFERENCE.md` - 快速参考
- `ANTHROPIC_FORMAT_MIGRATION_COMPLETE.md` - 迁移完成报告
- `backend/tests/test_anthropic_format_fix.py` - 测试文件

---

**修复完成时间**: 2026-04-26 21:51
**修复验证**: ✅ 所有测试通过
