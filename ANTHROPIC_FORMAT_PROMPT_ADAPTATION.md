# Anthropic 格式提示词与工具适配说明

## 🎯 核心问题

### 问题1: 提示词是否需要更新？

**答案**: ✅ **是的，需要大幅简化**

#### 当前问题

当前提示词（`assistant_prompt.py` 第93-149行）还在要求 JSON 格式：

```python
## ⚠️ 输出格式（CRITICAL）

### 格式1：调用单个工具
```json
{
  "thought": "简洁的思考过程",
  "action": {
    "type": "TOOL_CALL",
    "tool": "工具名称",
    "args": {
      "参数名": "参数值"
    }
  }
}
```
```

**这是为 V2（手动 JSON 解析）设计的**，V3 不需要！

---

### 问题2: 工具调用如何适配？

**答案**: ✅ **通过 Schema 转换自动适配**

---

## 📊 V2 vs V3 提示词对比

### V2 提示词（旧版 - 需要JSON格式）

```python
system_prompt = """
## ⚠️ 输出格式（CRITICAL）

**一次性生成完整的工具调用（包括参数）**：

### 格式1：调用单个工具
```json
{
  "thought": "简洁的思考过程",
  "action": {
    "type": "TOOL_CALL",
    "tool": "get_weather_data",
    "args": {"city": "广州"}
  }
}
```

### 格式2：给出最终回答
```json
{
  "thought": "可以回答用户",
  "action": {
    "type": "PLAIN_TEXT_REPLY",
    "answer": "完整的最终答案"
  }
}
```

**要求**：
- ✅ 必须输出 JSON
- ✅ 必须包含 thought 字段
- ✅ 必须包含 action 字段
- ❌ LLM 可能输出自然语言导致解析失败
"""
```

### V3 提示词（Anthropic - 推荐）

```python
system_prompt = """
## 工具使用指南

你有以下工具可以使用：

### 可用工具列表
{tool_list}

### 工具使用规则
1. 根据用户需求选择合适的工具
2. 使用工具时提供必需的参数
3. 如果没有合适的工具，直接用自然语言回复用户
4. 不要编造工具或参数

### 回复用户
- 如果能直接回答用户问题，直接用自然语言回复
- 如果需要调用工具，使用 Anthropic 的工具调用功能
"""

# 工具列表通过 Anthropic API 的 tools 参数传递
# 不需要在提示词中重复说明格式
```

---

## 🔧 工具适配机制

### 当前实现（已工作）

```python
# backend/app/agent/core/loop.py

def _get_tool_schema(self, tool_name: str, tool_doc: str) -> Dict:
    """将工具转换为 Anthropic 格式"""
    
    # 从工具文档提取描述
    description = tool_doc.split("\n\n")[0] if tool_doc else tool_name
    
    # 构建 Anthropic 格式 schema
    schema = {
        "name": tool_name,
        "description": description[:1000],  # 限制描述长度
        "input_schema": {
            "type": "object",
            "properties": {}  # 参数定义（当前为空）
        }
    }
    
    return schema

# V3 路径中使用
if settings.use_anthropic_format:
    # 获取所有工具
    tool_registry = get_react_agent_tool_registry()
    tools = []
    for tool_name, tool_func in tool_registry.items():
        tool_doc = tool_func.__doc__ or ""
        tool_schema = self._get_tool_schema(tool_name, tool_doc)
        if tool_schema:
            tools.append(tool_schema)
    
    # 调用 Anthropic API（tools 参数）
    llm_response = await self.llm_service.chat_anthropic(
        messages=messages,
        tools=tools,  # ← Anthropic 格式的工具列表
        system=system_prompt
    )
```

### Anthropic API 的工具格式

```python
# Anthropic API 期望的格式
tools = [
    {
        "name": "get_weather_data",
        "description": "获取天气数据",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称"
                },
                "date": {
                    "type": "string",
                    "description": "日期（可选）"
                }
            },
            "required": ["city"]
        }
    }
]

# API 调用
response = await anthropic.messages.create(
    model="deepseek-v4-flash",
    system=system_prompt,
    messages=[{"role": "user", "content": "查询广州天气"}],
    tools=tools  # ← 工具列表
)

# LLM 输出（SDK 自动解析）
# response.content = [
#     ContentBlock(type="tool_use", id="xxx", name="get_weather_data", input={"city": "广州"})
# ]
```

---

## 📝 完整流程对比

### V2 流程（JSON 格式）

```
┌──────────────────────────────────────────────────────┐
│ 1. 构建提示词（包含 JSON 格式要求）                    │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 2. 调用 LLM（流式输出）                               │
│    LLM 输出:                                          │
│    ```json                                           │
│    {"thought": "...", "action": {...}}               │
│    ```                                               │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 3. 手动解析 JSON（llm_response_parser.py 830行）      │
│    - 策略1: 提取代码块中的 JSON                        │
│    - 策略2: 直接解析 JSON                             │
│    - 策略3: 思维链 JSON 提取                          │
│    - 策略4: 正则表达式提取                            │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 4. 提取 action 和参数                                │
│    tool_name = action["tool"]                        │
│    tool_args = action["args"]                        │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 5. 调用工具                                          │
│    result = await execute_tool(tool_name, tool_args)  │
└──────────────────────────────────────────────────────┘
```

### V3 流程（Anthropic 原生）

```
┌──────────────────────────────────────────────────────┐
│ 1. 构建提示词（简化版，不需要 JSON 格式要求）          │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 2. 转换工具为 Anthropic 格式                         │
│    tools = [_get_tool_schema(...) for tool in tools]  │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 3. 调用 Anthropic API                                │
│    response = await anthropic.messages.create(       │
│        tools=tools,  ← 工具列表                       │
│        system=system_prompt,                          │
│        messages=messages                              │
│    )                                                 │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 4. SDK 自动解析（无需手动代码）                        │
│    content_blocks = response.content                  │
│    tool_use_blocks = [                                │
│        b for b in content_blocks                       │
│        if b.type == "tool_use"                        │
│    ]                                                 │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 5. 直接访问属性（无需解析）                            │
│    tool_call = tool_use_blocks[0]                     │
│    tool_name = tool_call.name        ← 直接获取        │
│    tool_args = tool_call.input        ← 直接获取        │
│    tool_call_id = tool_call.id        ← 直接获取        │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│ 6. 调用工具（带事件追踪）                             │
│    result = await execute_tool_with_events(           │
│        tool_name, tool_args, tool_call_id              │
│    )                                                 │
└──────────────────────────────────────────────────────┘
```

---

## 🎨 推荐的 V3 提示词结构

### 简化版提示词

```python
system_prompt = """
# 角色定义
你是一个智能助手，可以帮助用户完成各种任务。

# 工具使用
你可以使用以下工具来帮助用户：
- 直接通过工具调用功能使用（无需特殊格式）
- 工具会自动处理，你只需要决定何时使用哪个工具

# 回复风格
- 简洁、专业、友好
- 如果能直接回答，直接用自然语言
- 如果需要工具，LLM 会自动调用工具

# 注意事项
- 不要在回复中提及工具调用的技术细节
- 专注于解决用户问题
"""
```

### 详细版提示词（包含工具说明）

```python
system_prompt = """
# 角色定义
你是一个智能助手，可以帮助用户完成各种任务。

# 可用工具

## 文件操作
- read_file(path): 读取文件内容
- edit_file(path, old_string, new_string): 编辑文件
- write_file(path, content): 写入文件
- grep(pattern, path): 搜索文件内容

## 数据查询
- call_sub_agent(target_mode="query", task_description): 查询空气质量数据
- call_sub_agent(target_mode="expert", task_description): 深度分析

## 命令执行
- bash(command): 执行 Shell 命令

## 任务管理
- TodoWrite(items): 管理任务清单

# 工具使用规则
1. 选择合适的工具
2. 提供正确的参数
3. 等待工具结果
4. 基于结果继续或回复用户

# 回复风格
- 简洁、专业、友好
- 专注于解决用户问题
- 避免技术细节
"""
```

---

## 🔍 当前状态分析

### 从日志看到的实际运行情况

```log
# ✅ V3 格式正在运行
using_anthropic_format_v3 iteration=1 provider=deepseek

# ✅ API 调用成功
llm_anthropic_chat_request has_system=True has_tools=True
llm_anthropic_chat_success content_blocks=2

# ✅ 工具调用成功
action_decided action_type=TOOL_CALL iteration=2
executing_tool_v2 tool_name=TodoWrite

# ✅ 工具执行完成
todowrite_executed item_count=1
```

**关键发现**：
- ✅ V3 格式正在工作
- ✅ 工具调用成功
- ⚠️ 但提示词还在要求 JSON 格式（冗余）

---

## ✅ 建议的改进方案

### 方案1: 完全分离提示词（推荐）

```python
# backend/app/agent/prompts/anthropic_prompt.py

def build_anthropic_system_prompt(mode: str) -> str:
    """构建 Anthropic 格式的系统提示词"""
    
    base_prompt = """
# 角色定义
你是一个智能助手。

# 工具使用
你可以使用工具来帮助用户。LLM 会自动调用合适的工具。

# 回复风格
简洁、专业、友好。
"""
    
    if mode == "assistant":
        return base_prompt + ASSISTANT_SPECIFIC_INSTRUCTIONS
    elif mode == "expert":
        return base_prompt + EXPERT_SPECIFIC_INSTRUCTIONS
    # ...
```

### 方案2: 条件化提示词生成（当前可实施）

```python
# backend/app/agent/prompts/prompt_builder.py

def build_system_prompt(mode: str, use_anthropic_format: bool) -> str:
    """构建系统提示词（支持 V2/V3）"""
    
    if use_anthropic_format:
        # V3: 简化版，不需要 JSON 格式要求
        return build_v3_prompt(mode)
    else:
        # V2: 完整版，包含 JSON 格式要求
        return build_v2_prompt(mode)
```

### 方案3: 暂时保持现状（可用但不推荐）

- 当前提示词虽然冗余，但不会破坏 V3 功能
- LLM 会忽略 JSON 格式要求，直接使用 Anthropic 原生工具调用
- 优点：无需修改提示词
- 缺点：提示词冗余，可能轻微影响性能

---

## 📌 工具参数问题

### 当前问题

`_get_tool_schema` 的 `properties` 字段为空：

```python
"input_schema": {
    "type": "object",
    "properties": {}  # ← 空的！
}
```

### 改进建议

```python
def _get_tool_schema(self, tool_name: str, tool_doc: str) -> Dict:
    """改进版：提取参数信息"""
    
    schema = {
        "name": tool_name,
        "description": tool_doc.split("\n\n")[0] if tool_doc else tool_name,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
    
    # 从工具文档中提取参数
    if "Args:" in tool_doc:
        args_section = tool_doc.split("Args:")[1].split("Returns:")[0] if "Returns:" in tool_doc else tool_doc.split("Args:")[1]
        
        # 解析参数（简化实现）
        for line in args_section.split("\n"):
            if ":" in line and not line.strip().startswith("-"):
                param_name, param_desc = line.split(":", 1)
                param_name = param_name.strip()
                param_desc = param_desc.strip()
                
                schema["input_schema"]["properties"][param_name] = {
                    "type": "string",  # 默认为字符串
                    "description": param_desc
                }
    
    return schema
```

---

## 🎯 总结

### 问题1答案：提示词是否需要更新？

**是的，建议更新**：
- ✅ 移除 JSON 格式要求（第93-149行）
- ✅ 简化提示词结构
- ✅ 专注于工具使用规则而非格式要求

### 问题2答案：工具调用如何适配？

**已自动适配**：
- ✅ `_get_tool_schema` 将工具转换为 Anthropic 格式
- ✅ `convert_openai_to_anthropic_schema` 处理格式转换
- ✅ SDK 自动解析 tool_use blocks
- ⚠️ 但 `properties` 字段为空，可以改进

### 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 提示词 | ⚠️ 冗余 | 还在要求 JSON，但不影响功能 |
| 工具适配 | ✅ 工作中 | schema 转换正常 |
| 参数定义 | ⚠️ 不完整 | properties 为空 |
| API 调用 | ✅ 正常 | 成功调用工具 |
| 事件追踪 | ✅ 正常 | 生命周期事件正常 |

### 优先级建议

1. **高优先级**：改进 `_get_tool_schema` 的参数提取
2. **中优先级**：简化提示词，移除 JSON 格式要求
3. **低优先级**：完全分离 V2/V3 提示词

---

**实施建议**：
- 当前系统已经可以正常工作
- 可以逐步优化，无需立即修改
- 优先改进参数提取以提升工具调用的准确性
