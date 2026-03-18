# call_sub_agent工具依赖注入修复总结

## 问题描述

用户在助手模式下询问"查询广州市昨天的空气质量数据"时，助手Agent调用`call_sub_agent`工具切换到专家Agent，但出现错误：

```
'NoneType' object has no attribute 'session_id'
```

## 根本原因

`CallSubAgentTool` 在创建子Agent实例时需要以下依赖：
1. `memory_manager` - 内存管理器
2. `llm_planner` - LLM规划器
3. `tool_executor` - 工具执行器

但在全局工具注册时（`tools/__init__.py`），这些依赖还不存在：
```python
call_sub_agent_tool = CallSubAgentTool()  # ❌ 没有传递依赖
```

导致调用时 `self.memory_manager` 为 `None`，访问 `session_id` 属性时报错。

## 解决方案

采用**延迟依赖注入**的方式，通过`ExecutionContext`传递依赖。

### 1. 修改CallSubAgentTool - 支持从context获取依赖
**文件**: `backend/app/tools/agent_tools/call_sub_agent.py`

#### 修改1: 标记需要context
```python
super().__init__(
    name="call_sub_agent",
    description="调用另一个Agent模式作为子Agent执行任务",
    category=ToolCategory.QUERY,
    function_schema=function_schema,
    version="1.0.0",
    requires_context=True  # ✅ 改为True
)
```

#### 修改2: execute方法接收context参数
```python
async def execute(
    self,
    target_mode: AgentMode,
    task_description: str,
    context_data: Optional[Dict[str, Any]] = None,
    context: Optional[Any] = None  # ✅ 新增
) -> Dict[str, Any]:
```

#### 修改3: 从context获取依赖
```python
# ✅ 从context获取依赖（如果工具初始化时没有传递）
memory_manager = self.memory_manager
llm_planner = self.llm_planner
tool_executor = self.tool_executor

if context and hasattr(context, 'memory_manager'):
    memory_manager = context.memory_manager
    if hasattr(context, 'llm_planner'):
        llm_planner = context.llm_planner
    if hasattr(context, 'tool_executor'):
        tool_executor = context.tool_executor

# 验证必需的依赖
if not memory_manager:
    raise RuntimeError("memory_manager is required for call_sub_agent")
```

### 2. 修改ToolExecutor - 扩展ExecutionContext
**文件**: `backend/app/agent/core/executor.py`

#### 修改1: 添加llm_planner参数
```python
def __init__(
    self,
    tool_registry: Optional[Dict[str, Callable]] = None,
    memory_manager: Optional["HybridMemoryManager"] = None,
    task_list: Optional[Any] = None,
    llm_planner: Optional[Any] = None  # ✅ 新增
):
    # ...
    self.llm_planner = llm_planner  # ✅ 存储llm_planner
```

#### 修改2: 在ExecutionContext中添加依赖
```python
def _create_execution_context(self, iteration: int):
    # ...
    context = ExecutionContext(
        session_id=self.memory_manager.session_id,
        iteration=iteration,
        data_manager=self.data_context_manager,
        task_list=self.task_list
    )

    # ✅ 为 call_sub_agent 工具添加额外的依赖
    context.memory_manager = self.memory_manager
    context.llm_planner = self.llm_planner
    context.tool_executor = self

    return context
```

### 3. 修改ReActAgent - 注入llm_planner
**文件**: `backend/app/agent/react_agent.py`

```python
# 初始化工具执行器
self.executor = ToolExecutor(tool_registry=tool_registry)

# 初始化 LLM 规划器
self.planner = ReActPlanner(tool_registry=tool_registry)

# ✅ 将planner注入到executor中（用于call_sub_agent）
self.executor.llm_planner = self.planner
```

## 数据流

### 修复前
```
call_sub_agent工具
    ↓
self.memory_manager → None
    ↓
创建ReActLoop失败
    ↓
错误: 'NoneType' object has no attribute 'session_id'
```

### 修复后
```
call_sub_agent工具
    ↓
检查self.memory_manager → None
    ↓
从context获取memory_manager → 成功
context.memory_manager → HybridMemoryManager实例
context.llm_planner → ReActPlanner实例
context.tool_executor → ToolExecutor实例
    ↓
创建ReActLoop成功
    ↓
子Agent执行成功
```

## 测试验证

### 1. 启动后端
```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 2. 测试场景
```
1. 打开前端，选择"通用助手"
2. 选择"助手"模式
3. 输入："查询广州市昨天的空气质量数据"
4. 预期：
   - 助手Agent识别需要数据查询
   - 调用call_sub_agent(target_mode="expert", ...)
   - 专家Agent执行数据查询
   - 返回结果给助手Agent
   - 助手Agent整理并回复用户
```

### 3. 日志验证
```bash
# 查看日志
tail -f logs/app.log | grep -E "(calling_sub_agent|sub_agent_completed)"

# 应该看到：
calling_sub_agent target_mode=expert task=查询广州市昨天的空气质量数据
sub_agent_completed target_mode=expert status=success
```

## 相关文件

修改的文件（4个）：
1. `backend/app/tools/agent_tools/call_sub_agent.py` - 支持从context获取依赖
2. `backend/app/agent/core/executor.py` - 扩展ExecutionContext + 添加llm_planner参数
3. `backend/app/agent/react_agent.py` - 注入llm_planner到executor

## 技术细节

### ExecutionContext扩展
```python
# 原有字段
context.session_id
context.iteration
context.data_manager
context.task_list

# 新增字段（用于call_sub_agent）
context.memory_manager  # ✅ HybridMemoryManager实例
context.llm_planner     # ✅ ReActPlanner实例
context.tool_executor   # ✅ ToolExecutor实例
```

### requires_context的作用
当工具的`requires_context=True`时，executor会自动在调用时传递context：
```python
if execution_context:
    result = await tool_func(context=execution_context, **tool_args)
else:
    result = await tool_func(**tool_args)
```

## 设计理念

### 延迟依赖注入
- **全局注册时**：工具不需要依赖，可以无参数创建
- **运行时**：通过ExecutionContext动态注入依赖
- **优点**：
  - 避免循环依赖
  - 工具注册更灵活
  - 不同执行环境可以注入不同依赖

### 向后兼容
- 工具仍然可以在初始化时接收依赖（如果有）
- 运行时优先使用初始化的依赖
- 如果初始化时没有依赖，才从context获取
- 保证了灵活性和兼容性

## 已知问题

无

## 下一步优化建议

1. **统一依赖注入模式**
   - 定义标准的`ToolDependencies`类
   - 所有需要依赖的工具都从context获取

2. **依赖验证**
   - 在工具执行前验证所需依赖是否存在
   - 提供更友好的错误提示

3. **文档更新**
   - 更新工具开发指南
   - 说明如何正确使用context获取依赖
