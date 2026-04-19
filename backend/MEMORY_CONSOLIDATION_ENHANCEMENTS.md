# 记忆整合Agent系统增强 - 记忆上下文注入

## 增强概述

在原有记忆整合Agent系统的基础上，新增了**记忆上下文注入**功能，确保记忆整合Agent能够：
1. 访问现有记忆内容（避免重复记忆）
2. 知道当前对话模式的记忆文件路径（支持模式隔离）
3. 支持社交模式的用户隔离（路径包含用户ID）

## 问题背景

用户反馈指出，原有实现存在以下问题：
1. ❌ 记忆整合Agent**不知道现有的记忆内容**
2. ❌ 记忆整合Agent**不知道记忆文件路径**
3. ❌ 记忆工具**硬编码了模式**（`mode = "social"`）
4. ❌ 记忆工具**没有获取用户ID**（社交模式需要用户隔离）

## 解决方案

### 1. 记忆内容注入

**实现位置**：`react_agent.py:_build_consolidation_prompt()`

**增强内容**：
- 在提示词中注入**完整的现有记忆内容**（不限制字符）
- 注入记忆文件路径（供工具使用）
- 明确任务说明，告知Agent需要阅读现有记忆

**设计决策 - 为什么不限制字符？** ⭐ 重要

**问题**：如果限制记忆字符数（如1000字符），Agent无法看到完整的记忆内容，导致：
- 无法真正避免重复记忆（重复的内容可能在被截断的部分）
- 基于不完整信息做出错误决策
- 违背了"先阅读现有记忆"的设计初衷

**解决方案**：提供完整的记忆内容，理由：
1. **记忆文件不会太大**：应该被定期清理和整合（remove_memory工具）
2. **LLM可以处理**：现代LLM可以轻松处理几千到上万个字符
3. **完整性优先**：避免重复记忆比节省token更重要
4. **真正实现目标**：Agent能看到完整的记忆上下文，做出正确决策

**成本控制**：
- 如果记忆文件真的很大（比如超过10,000字符），说明需要清理
- 记忆工具应该被用于维护记忆的简洁性
- 记忆整合本身就是一个清理和维护的过程

**提示词结构**：
```markdown
请分析以下对话内容，提取重要信息并更新长期记忆。

## 模式
{mode}

## 现有记忆
```
{existing_memory}
```

## 记忆文件路径
{memory_file_path}

## 对话内容
{conversation_text}

**任务**：
1. 阅读现有记忆，了解已记住的内容
2. 分析对话内容，识别需要记住的新信息
3. 使用工具更新记忆
4. 给出简洁总结
```

### 2. 模式和用户隔离

**实现机制**：使用类变量传递上下文信息

**工具修改**：

#### remember_fact/tool.py
```python
class RememberFactTool(LLMTool):
    # 类变量：用于存储当前的模式和用户信息
    _current_mode = None
    _current_user_id = None

    @classmethod
    def set_memory_context(cls, mode: str, user_id: str = None):
        """设置当前的记忆上下文（由记忆整合Agent调用）"""
        cls._current_mode = mode
        cls._current_user_id = user_id

    @classmethod
    def clear_memory_context(cls):
        """清除记忆上下文"""
        cls._current_mode = None
        cls._current_user_id = None

    def _get_memory_file_path(self) -> str:
        """使用类变量构建记忆文件路径"""
        mode = self._current_mode or 'social'
        user_id = self._current_user_id

        base_path = Path("/home/xckj/suyuan/backend_data_registry/memory")
        memory_dir = base_path / mode

        # 社交模式需要用户隔离
        if mode == 'social' and user_id and user_id != 'global':
            memory_dir = memory_dir / user_id

        return str(memory_dir / "MEMORY.md")
```

**同样修改**：
- `replace_memory/tool.py`
- `remove_memory/tool.py`

### 3. 后台整合流程

**实现位置**：`react_agent.py:_background_memory_consolidation()`

**完整流程**：

```python
async def _background_memory_consolidation(self, session_id, unified_user_id, mode):
    try:
        # 1. 获取会话历史
        messages = memory_manager.session.get_messages_for_llm()

        # 2. 检查触发条件
        if new_message_count >= 20:
            # 3. 获取现有记忆内容和文件路径
            memory_store = await self.memory_manager.get_user_memory(
                user_id=unified_user_id,
                mode=mode
            )
            existing_memory = memory_store.read_long_term()
            memory_file_path = str(memory_store.memory_file.resolve())

            # 4. 构建整合提示词（包含现有记忆和文件路径）
            consolidation_prompt = self._build_consolidation_prompt(
                messages,
                mode,
                existing_memory,
                memory_file_path
            )

            # 5. 设置记忆上下文（供记忆工具使用）
            user_id = unified_user_id.split(':')[1] if ':' in unified_user_id else None
            RememberFactTool.set_memory_context(mode, user_id)
            ReplaceMemoryTool.set_memory_context(mode, user_id)
            RemoveMemoryTool.set_memory_context(mode, user_id)

            # 6. 创建并执行记忆整合Agent
            consolidator_agent = create_memory_consolidator_agent()
            async for event in consolidator_agent.analyze(...):
                # 处理事件...

    finally:
        # 7. 清除记忆上下文（无论成功或失败）
        RememberFactTool.clear_memory_context()
        ReplaceMemoryTool.clear_memory_context()
        RemoveMemoryTool.clear_memory_context()
```

## 路径规则

### 路径结构

```
backend_data_registry/memory/
├── {mode}/                           # 模式目录
│   ├── MEMORY.md                     # 全局记忆（非用户隔离）
│   └── {user_id}/                    # 用户专属目录（仅社交模式）
│       └── MEMORY.md                 # 用户专属记忆
```

### 示例路径

**非用户隔离模式**（assistant、expert）：
- `backend_data_registry/memory/assistant/MEMORY.md`
- `backend_data_registry/memory/expert/MEMORY.md`

**社交模式用户隔离**：
- `backend_data_registry/memory/social/global/MEMORY.md`（全局）
- `backend_data_registry/memory/social/user_12345/MEMORY.md`（用户专属）

## 记忆整合提示词示例

```markdown
请分析以下对话内容，提取重要信息并更新长期记忆。

## 模式
social

## 现有记忆
```
# 长期记忆 (MEMORY.md)

## 用户偏好
- 喜欢简洁的回答

## 领域知识
- Python是一种编程语言

## 历史结论
- 测试结论
```

## 记忆文件路径
/home/xckj/suyuan/backend_data_registry/memory/social/user_12345/MEMORY.md

## 对话内容
user: 我喜欢Python
assistant: 好的，我会记住你...

**任务**：
1. 阅读现有记忆，了解已记住的内容
2. 分析对话内容，识别需要记住的新信息
3. 使用工具更新记忆：
   - remember_fact: 添加新记忆
   - replace_memory: 替换现有记忆
   - remove_memory: 删除过时记忆
4. 给出简洁总结（不超过50字）

**注意事项**：
- 避免重复记忆（先检查现有记忆）
- 更新偏好设置时使用replace_memory
- 删除临时或错误记忆时使用remove_memory
- 记忆文件路径已在上方提供，工具会自动使用
```

## 关键改进点

### 1. 避免重复记忆

**之前**：Agent不知道现有记忆，可能重复添加相同内容
**现在**：Agent可以阅读现有记忆，避免重复

### 2. 支持模式隔离

**之前**：工具硬编码 `mode = "social"`
**现在**：工具从上下文获取模式，支持所有模式

### 3. 支持用户隔离

**之前**：所有用户共享同一个记忆文件
**现在**：社交模式支持用户专属记忆路径

### 4. 路径透明化

**之前**：工具不知道记忆文件路径
**现在**：提示词中明确告知记忆文件路径

## 测试验证

所有原有测试继续通过：
```
✓ 快照创建成功
✓ get_memory_context 返回快照内容
✓ 快照清理成功
✓ Agent创建成功，可用工具正确
✓ 提示词生成成功
✓ 工具注册正确
✅ 所有测试通过！
```

## 日志增强

新增调试日志：
```python
logger.debug(
    "memory_file_path_resolved",
    mode=mode,
    user_id=user_id,
    path=str(memory_file)
)
```

示例输出：
```json
{
  "mode": "social",
  "user_id": "user_12345",
  "path": "/home/xckj/suyuan/backend_data_registry/memory/social/user_12345/MEMORY.md"
}
```

## 总结

通过引入记忆上下文注入机制，记忆整合Agent系统现在能够：

1. ✅ **访问现有记忆**：避免重复记忆，提高记忆质量
2. ✅ **支持模式隔离**：工具自动适配当前对话模式
3. ✅ **支持用户隔离**：社交模式实现用户专属记忆
4. ✅ **路径透明化**：Agent明确知道操作的记忆文件路径
5. ✅ **向后兼容**：所有原有测试继续通过

这些增强确保了记忆整合Agent在各种场景下都能正确工作，特别是在需要用户隔离的社交模式下。
