# 双模式Agent架构设计文档

## 概述

系统实现了**双模式Agent架构**，支持助手模式（办公任务）和专家模式（数据分析）两种工作模式，两种模式可通过 `call_sub_agent` 工具实现双向互调。

## 架构设计

### 模式定义

| 模式 | 用途 | 系统提示词 | 工具集 |
|------|------|-----------|--------|
| **助手模式** (assistant) | 办公任务、文档处理、通用助理 | 通用办公助理prompt | 全工具集（包含Office工具、bash等） |
| **专家模式** (expert) | 数据查询、污染源分析、科学计算 | 数据分析专家prompt | 全工具集（侧重数据/分析工具） |

### 双向调用机制

```
助手模式 ←→ call_sub_agent ←→ 专家模式
```

**场景示例**：
- 助手 → 专家：用户在助手模式问"查询广州空气质量"，助手调用专家子Agent执行数据查询
- 专家 → 助手：用户在专家模式要求"生成Word报告"，专家调用助手子Agent处理文档

### call_sub_agent 工具

**文件**: `backend/app/tools/agent_tools/call_sub_agent.py`

**核心参数**:
```python
{
    "target_mode": "assistant | expert",  # 目标模式
    "task_description": "任务描述",         # 明确的任务说明
    "context_data": {...}                 # 可选的上下文数据
}
```

**依赖注入实现**:
```python
# 工具通过 ExecutionContext 获取运行时依赖
async def execute(
    self,
    context: Optional[Any] = None,  # ExecutionContext
    target_mode: str = None,
    task_description: str = None,
    **kwargs
):
    # 从 context 获取依赖
    memory_manager = context.memory_manager
    llm_planner = context.llm_planner
    tool_executor = context.tool_executor

    # 创建子Agent
    sub_agent_loop = ReActLoop(
        memory_manager=memory_manager,
        llm_planner=llm_planner,
        tool_executor=tool_executor,
        max_iterations=10
    )

    # 执行子Agent
    async for event in sub_agent_loop.run(user_query=enhanced_query, manual_mode=target_mode):
        result_events.append(event)
```

**依赖注入链**:
```
ReActAgent.__init__
  ↓ 创建并注入
ToolExecutor.__init__(llm_planner=planner)
  ↓ 创建ExecutionContext时注入
ExecutionContext.memory_manager
ExecutionContext.llm_planner
ExecutionContext.tool_executor
  ↓ 传递给工具
CallSubAgentTool.execute(context=...)
```

**关键修改点**:
1. `backend/app/agent/react_agent.py:82` - 注入 llm_planner 到 executor
2. `backend/app/agent/core/executor.py:78-88` - 接收 llm_planner 参数
3. `backend/app/agent/core/executor.py:291-295` - 扩展 ExecutionContext
4. `backend/app/tools/agent_tools/call_sub_agent.py:74-80` - execute 方法接收 context

## 前端实现

### 模式选择器

**文件**: `frontend/src/components/AgentModeSelector.vue`

**设计**：
- 简洁按钮风格（与"深度思考"标签一致）
- 双按钮切换（助手/专家）
- LocalStorage持久化用户选择
- 默认助手模式

**位置**：与深度思考标签同一行，位于其前方

### 状态管理

**文件**: `frontend/src/stores/reactStore.js`

```javascript
// 状态定义
agentMode: localStorage.getItem('agent-mode') || 'assistant'

// 模式切换
handleAgentModeChange(value) {
    store.agentMode = value
    localStorage.setItem('agent-mode', value)
}
```

### API传递

**文件**: `frontend/src/services/reactApi.js`

```javascript
async analyze(query, options = {}) {
    const { agentMode = 'expert', ... } = options
    const body = {
        query,
        mode: agentMode  // 传递给后端
    }
}
```

## 后端处理

### API接收

**文件**: `backend/app/routers/agent.py`

```python
class AgentAnalyzeRequest(BaseModel):
    mode: Optional[str] = Field("expert", description="Agent模式")

analyze_kwargs = {
    "manual_mode": request.mode
}
```

### 系统提示词构建

**文件**: `backend/app/agent/prompts/simplified_context_builder.py`

```python
def build_react_system_prompt(mode: str = "expert") -> str:
    if mode == "assistant":
        return ASSISTANT_SYSTEM_PROMPT  # 办公助理prompt
    else:
        return EXPERT_SYSTEM_PROMPT     # 数据分析专家prompt
```

### ReActLoop执行

**文件**: `backend/app/agent/core/loop.py`

```python
async def run(
    self,
    user_query: str,
    manual_mode: Optional[str] = None  # 接收模式参数
):
    # 构建系统提示词
    system_prompt = build_react_system_prompt(mode=manual_mode or "expert")

    # 使用指定模式执行
    messages = [{"role": "system", "content": system_prompt}]
```

## 使用示例

### 助手模式调用专家模式

**用户输入**（助手模式）:
```
查询昨天广州的空气质量数据
```

**助手Agent执行流程**:
```
Thought: 用户需要查询数据，我应该调用专家Agent处理
Action: call_sub_agent
Args: {
    "target_mode": "expert",
    "task_description": "查询2026年2月13日广州的空气质量数据"
}
Observation: 专家Agent返回查询结果（PM2.5、O3等数据）
Thought: 整理数据并回复用户
Action: FINISH
```

### 专家模式调用助手模式

**用户输入**（专家模式）:
```
将这份分析结果生成Word报告
```

**专家Agent执行流程**:
```
Thought: 用户需要生成Word文档，我应该调用助手Agent处理
Action: call_sub_agent
Args: {
    "target_mode": "assistant",
    "task_description": "生成污染源分析Word报告",
    "context_data": {"analysis_data_id": "particulate_analysis:xxx"}
}
Observation: 助手Agent返回报告生成结果
Thought: 报告已生成
Action: FINISH
```

## 关键技术点

### 1. 延迟依赖注入

**问题**：工具全局注册时依赖未初始化
**解决**：通过 ExecutionContext 运行时注入

**优势**：
- 避免循环依赖
- 工具注册更灵活
- 不同执行环境可注入不同依赖

### 2. 参数验证

**文件**: `backend/app/tools/agent_tools/call_sub_agent.py:100-118`

```python
if not target_mode:
    return {"status": "failed", "result": "缺少必需参数：target_mode"}
if not task_description:
    return {"status": "failed", "result": "缺少必需参数：task_description"}
```

### 3. 上下文增强查询

**方法**: `_build_enhanced_query()`

```python
def _build_enhanced_query(task_description, context_data, target_mode):
    query_parts = [task_description]

    # 携带上下文数据
    if context_data:
        query_parts.append("\n\n【上下文数据】")
        for key, value in context_data.items():
            query_parts.append(f"- {key}: {value}")

    # 添加模式提示
    if target_mode == "assistant":
        query_parts.append("\n注意：你是作为子Agent被调用，专注完成上述办公任务即可。")

    return "\n".join(query_parts)
```

### 4. 结果提取

**方法**: `_extract_final_result()`

```python
def _extract_final_result(events: list) -> Dict:
    # 查找 agent_finish 事件
    for event in reversed(events):
        if event.get("type") == "agent_finish":
            return {
                "status": "success",
                "answer": event.get("answer", ""),
                "data": event.get("data", {})
            }
    # Fallback: 查找最后的 observation
    ...
```

## 性能表现

**日志示例** (`docs/后端日志.md`):
```
助手模式总迭代: 2次
  └─ 子Agent（专家模式）: 3次
     ├─ Iteration 1: 参数验证失败
     ├─ Iteration 2: 数据查询成功
     └─ Iteration 3: 生成总结

总耗时: 合理（大部分时间在数据查询API）
```

## 已知优化点

1. **子Agent参数推断** - 减少首次失败重试（优先级：高）
2. **会话上下文共享** - 减少重复信息传递（优先级：中）
3. **子Agent迭代限制** - 当前max_iterations=10，可根据任务类型动态调整（优先级：低）

## 相关文件

### 后端核心
- `backend/app/tools/agent_tools/call_sub_agent.py` - 子Agent调用工具
- `backend/app/agent/core/executor.py` - 工具执行器（依赖注入）
- `backend/app/agent/react_agent.py` - ReAct主Agent（注入llm_planner）
- `backend/app/agent/core/loop.py` - ReAct循环（模式参数支持）
- `backend/app/agent/prompts/simplified_context_builder.py` - 模式提示词构建

### 前端核心
- `frontend/src/components/AgentModeSelector.vue` - 模式选择器
- `frontend/src/components/InputBox.vue` - 输入框（模式传递）
- `frontend/src/views/ReactAnalysisView.vue` - 主视图（事件处理）
- `frontend/src/stores/reactStore.js` - 状态管理
- `frontend/src/services/reactApi.js` - API调用

### 修复总结文档
- `call_sub_agent工具依赖注入修复总结.md` - 完整实现细节
