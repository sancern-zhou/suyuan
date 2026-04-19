# 历史会话记忆内容显示问题修复

## 问题描述

打开历史会话时，用户的对话内容会显示历史记忆（MEMORY.md的内容），影响用户体验。

## 根本原因

记忆增强内容被保存到对话历史中，导致恢复会话时显示给用户。

### 代码流程（修复前）

1. **`react_agent.py` 第 184-186 行**：
   - 将记忆上下文直接添加到 `user_query` 中
   - 格式：`"{记忆内容}\n\n**记忆文件路径**：{路径}\n\n用户问题：{原始问题}"`

2. **`loop.py` 第 220 行**：
   - 将带有记忆信息的 `user_query` 保存到对话历史
   - `self.memory.session.add_user_message(user_query)`

3. **会话保存和恢复**：
   - 带有记忆的用户消息被保存到数据库
   - 恢复会话时，记忆内容从对话历史中读取并显示

## 解决方案（V2）

**记忆内容注入到系统提示词中，不修改用户查询**。

### 设计原则

1. **记忆注入到系统提示词**：在系统提示词中真正注入记忆内容（而不是只说"已加载"）
2. **保持用户消息纯粹性**：用户消息只包含原始输入
3. **使用记忆快照机制**：连续对话时从快照获取记忆内容

### 代码修改

#### 1. 所有模式提示词文件 - 添加memory_context参数

**修改前**（assistant_prompt.py）：
```python
def build_assistant_prompt(available_tools: List[str]) -> str:
    prompt_parts = [
        "你是通用办公助手...\n",
        "## 记忆机制\n",
        "**长期记忆已自动加载**：系统会自动加载你的长期记忆...\n",
        "**记忆文件位置**：你的长期记忆保存在 `/path/to/MEMORY.md`...\n",
        ...
    ]
```

**修改后**：
```python
def build_assistant_prompt(available_tools: List[str], memory_context: Optional[str] = None) -> str:
    prompt_parts = []

    # ✅ 记忆注入：从快照获取的记忆内容直接注入到系统提示词
    if memory_context and memory_context.strip():
        prompt_parts.append(memory_context + "\n")

    prompt_parts.extend([
        "你是通用办公助手...\n",
        ...  # 删除"记忆已加载"说明
    ])
```

**影响文件**：
- `assistant_prompt.py` ✅
- `expert_prompt.py` ✅
- `code_prompt.py` ✅
- `query_prompt.py` ✅
- `report_prompt.py` ✅
- `chart_prompt.py` ✅
- `social_prompt.py` ✅

#### 2. prompt_builder.py - 传递memory_context

**修改前**：
```python
def build_react_system_prompt(
    mode: AgentMode,
    available_tools: Optional[List[str]] = None,
    user_preferences: Optional[dict] = None,
    memory_file_path: Optional[str] = None
) -> str:
    ...
    if mode == "assistant":
        return build_assistant_prompt(filtered_tools)
    ...
```

**修改后**：
```python
def build_react_system_prompt(
    mode: AgentMode,
    available_tools: Optional[List[str]] = None,
    user_preferences: Optional[dict] = None,
    memory_file_path: Optional[str] = None,
    memory_context: Optional[str] = None  # ✅ 新增
) -> str:
    ...
    # ✅ 统一传递memory_context
    if mode == "assistant":
        return build_assistant_prompt(filtered_tools, memory_context)
    ...
```

#### 3. react_agent.py - 不修改user_query

**修改前**：
```python
# 加载记忆上下文并添加到查询中
memory_context = memory_store.get_memory_context()
if memory_context:
    memory_info = f"{memory_context}\n\n**记忆文件路径**：{memory_file_path}"
    user_query = f"{memory_info}\n\n用户问题：{user_query}"
```

**修改后**：
```python
# ✅ 加载记忆上下文（用于系统提示词注入，不修改user_query）
memory_context = None
if unified_user_id:
    memory_store = await self.memory_manager.get_user_memory(...)
    memory_context = memory_store.get_memory_context()  # 从快照获取
    memory_file_path = str(memory_store.memory_file.resolve())

    # ✅ 记录记忆注入详情
    if memory_context:
        logger.info("memory_context_prepared", ...)

# ✅ user_query保持原样，不添加记忆内容
```

#### 4. react_agent.py - 传递memory_context给loop

**修改前**：
```python
async for event in react_loop.run(
    user_query=user_query,
    original_user_query=original_user_query,  # V1方案的临时修复
    ...
):
```

**修改后**：
```python
# ✅ 设置记忆上下文到上下文构建器
if memory_context:
    react_loop.context_builder.memory_context = memory_context

async for event in react_loop.run(
    user_query=user_query,  # ✅ 原始用户查询（不包含记忆）
    ...
):
```

#### 5. loop.py - 移除original_user_query逻辑

**修改前**：
```python
async def run(
    self,
    user_query: str,
    original_user_query: Optional[str] = None,
    ...
):
    ...
    query_to_save = original_user_query if original_user_query else user_query
    self.memory.session.add_user_message(query_to_save)
```

**修改后**：
```python
async def run(
    self,
    user_query: str,  # ✅ 移除original_user_query参数
    ...
):
    ...
    # ✅ 直接保存原始查询
    self.memory.session.add_user_message(user_query)
```

#### 6. simplified_context_builder.py - 添加memory_context字段

**修改前**：
```python
def __init__(self, ...):
    self.current_mode = "expert"
    self.memory_file_path = None

def _build_system_prompt(self):
    return build_react_system_prompt(
        mode=self.current_mode,
        memory_file_path=self.memory_file_path
    )
```

**修改后**：
```python
def __init__(self, ...):
    self.current_mode = "expert"
    self.memory_context = None  # ✅ 新增
    self.memory_file_path = None

def _build_system_prompt(self):
    return build_react_system_prompt(
        mode=self.current_mode,
        memory_file_path=self.memory_file_path,
        memory_context=self.memory_context  # ✅ 传递记忆上下文
    )
```

## 修改后的数据流

### 会话开始
```
create_snapshot()  # 创建记忆快照
  ↓
get_memory_context()  # 从快照获取记忆内容
  ↓
build_react_system_prompt(memory_context=...)  # 注入到系统提示词
```

### LLM实际收到的内容
```
系统消息：
"你是通用办公助手...
## 长期记忆
用户偏好：...
领域知识：...
历史结论：...
...
[工具列表]
"

用户消息：
"查一下广州空气质量"  # ✅ 纯净的原始问题
```

### 对话历史保存
```
user_query（原始问题）→ add_user_message → conversation_history → 数据库
```

### 会话恢复
```
数据库 → conversation_history → 前端显示（只显示用户原始问题）
```

### 会话结束
```
cleanup_snapshot()  # 清理快照
```

## 关键改进点

1. ✅ **记忆真正注入到系统提示词**：而不是只说"已加载"
2. ✅ **用户消息保持纯粹**：不包含记忆增强内容
3. ✅ **使用快照机制**：连续对话时从快照获取记忆
4. ✅ **历史会话干净**：恢复时不显示记忆内容
5. ✅ **所有模式统一**：7种模式都支持记忆注入

## 记忆快照机制

**会话开始**：
- `create_snapshot()` 创建MEMORY.md的独立副本
- 后台Agent的更新不影响当前对话

**对话期间**：
- `get_memory_context()` 从快照获取记忆（固定不变）
- 记忆内容注入到系统提示词中

**会话结束**：
- `cleanup_snapshot()` 清理快照文件
- 下次会话重新创建快照（包含所有更新）

## 影响范围

- **核心修改**：9个文件
  - 提示词文件：7个（所有模式）
  - 核心逻辑：2个（react_agent.py, simplified_context_builder.py）
- **清理修改**：1个文件（loop.py，移除V1方案）
- **向后兼容**：完全兼容（memory_context默认为None）
- **性能影响**：无

## 相关文件

- `/backend/app/agent/prompts/` - 所有模式提示词文件
- `/backend/app/agent/prompts/prompt_builder.py` - 提示词构建器
- `/backend/app/agent/react_agent.py` - ReAct Agent主入口
- `/backend/app/agent/core/loop.py` - ReAct循环引擎
- `/backend/app/agent/context/simplified_context_builder.py` - 上下文构建器
- `/backend/app/agent/memory/memory_store.py` - 记忆存储和快照机制
