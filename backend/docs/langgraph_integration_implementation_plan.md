# 集成 LangGraph 作为 ReAct Agent 的专用流程引擎 - 实施计划

## 背景

当前系统基于 ReAct Agent 架构，LLM 通过"思考-行动-观察"循环自主决策。多专家系统通过 ExpertRouterV3 作为工具被调用，使用 ToolDependencyGraph 进行调度。

**引入 LangGraph 的原因**：
- 为固定流程场景（如快速溯源）提供可视化的流程定义
- 改进并行执行的调度和依赖管理
- 提供调试和性能分析工具

**关键设计决策**：LangGraph 作为 ReAct Loop 的一个工具，而非替代品。

## 架构设计

```
┌─────────────────────────────────────┐
│         ReAct Loop (不变)         │
│  (LLM 自主决策的主框架)         │
└────────────┬────────────────────┘
             │ LLM 决策调用工具
             ▼
    ┌────────┼────────┐
    │        │        │
    ▼        ▼        ▼
 简单    探索性    固定流程
 工具    任务      (LangGraph)
                   │
                   ▼
            ┌─────────────────┐
            │ LangGraph 工具流  │
            │ - 快速溯源流程   │
            │ - 其他固定工作流  │
            └─────────────────┘
```

## 实施计划

### Phase 1: 添加 LangGraph 依赖

**文件**: `backend/requirements.txt`

添加以下依赖：
```
langgraph>=0.1.0
langchain>=0.2.0
langchain-core>=0.2.0
```

### Phase 2: 创建 LangGraph 集成层

**新建目录**: `backend/app/agent/langgraph/`

#### 文件 2.1: `states.py` - 定义 LangGraph 状态

```python
from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field

class LangGraphState(TypedDict):
    """LangGraph 执行状态"""
    # 执行上下文
    session_id: str
    context: Dict[str, Any]

    # 用户输入
    user_query: str = ""
    workflow_type: str = ""

    # 执行结果
    expert_results: Dict[str, Any] = Field(default_factory=dict)
    data_ids: List[str] = Field(default_factory=list)
    visuals: List[Dict[str, Any]] = Field(default_factory=list)

    # 执行元数据
    iteration: int = 0
    errors: List[str] = Field(default_factory=list)

    # 完成标记
    completed: bool = False
```

#### 文件 2.2: `quick_trace_graph.py` - 快速溯源流程图

```python
from typing import Literal
from langgraph.graph import StateGraph, END
from .states import LangGraphState

# 定义快速溯源流程
workflow = StateGraph(LangGraphState)

# 添加专家节点
workflow.add_node("weather_expert", weather_expert_node)
workflow.add_node("component_expert", component_expert_node)
workflow.add_node("viz_expert", viz_expert_node)
workflow.add_node("report_expert", report_expert_node)

# 并行执行气象和组分专家
workflow.add_conditional_edges(
    START,
    lambda state: "ready",
    {
        "ready": ["["weather_expert", "component_expert"]"]
    }
)

# 可视化专家依赖前两个
workflow.add_edge("weather_expert", "viz_expert")
workflow.add_edge("component_expert", "viz_expert")

# 报告专家依赖可视化
workflow.add_edge("viz_expert", "report_expert")
workflow.add_edge("report_expert", END)
```

#### 文件 2.3: `executor.py` - LangGraph 执行器

```python
from typing import List, Dict, Any
from .states import LangGraphState
from .quick_trace_graph import workflow as quick_trace_workflow

WORKFLOW_REGISTRY = {
    "quick_trace": quick_trace_workflow,
    # 未来可添加其他流程
}

class LangGraphExecutor:
    """LangGraph 执行器"""

    @staticmethod
    def get_available_workflows() -> List[str]:
        """获取可用的工作流列表"""
        return list(WORKFLOW_REGISTRY.keys())

    @staticmethod
    async def execute(
        workflow_type: str,
        user_query: str,
        context: Dict[str, Any],
        session_id: str
    ) -> Dict[str, Any]:
        """执行指定的工作流"""
        if workflow_type not in WORKFLOW_REGISTRY:
            return {
                "success": False,
                "error": f"未知的工作流类型: {workflow_type}"
            }

        # 初始化状态
        initial_state = LangGraphState(
            session_id=session_id,
            context=context,
            user_query=user_query,
            workflow_type=workflow_type
        )

        # 执行流程
        app = WORKFLOW_REGISTRY[workflow_type]
        result = await app.ainvoke(initial_state)

        return {
            "success": result.get("completed", False),
            "data_ids": result.get("data_ids", []),
            "visuals": result.get("visuals", []),
            "expert_results": result.get("expert", {}),
            "errors": result.get("errors", [])
        }
```

### Phase 3: 创建 LangGraph 工具

**文件**: `backend/app/tools/langgraph/workflow_tool.py` (新建)

```python
from typing import Dict, Any
from app.agent.langgraph.executor import LangGraphExecutor

class LangGraphWorkflowTool:
    """LangGraph 工作流工具"""

    name = "langgraph_workflow"
    description = """
执行预定义的 LangGraph 工作流，用于固定流程场景如快速溯源。

适用场景：
- 快速污染溯源分析（quick_trace）
- 其他固定流程的多步骤分析

参数：
- workflow_type: 工作流类型，如 "quick_trace"
- user_query: 用户查询内容

返回：标准 UDF v2.0 格式，包含所有专家的结果和数据
"""

    async def execute(
        self,
        workflow_type: str,
        user_query: str,
        **kwargs
    ) -> Dict[str, Any]:
        """执行 LangGraph 工作流"""
        from app.agent.context import ExecutionContext

        # 获取执行上下文
        context = kwargs.get("context")
        session_id = getattr(context, "session_id", "langgraph_session")

        # 执行工作流
        result = await LangGraphExecutor.execute(
            workflow_type=workflow_type,
            user_query=user_query,
            context=kwargs,
            session_id=session_id
        )

        # 返回标准格式
        return {
            "status": "success" if result.get("success") else "failed",
            "success": result.get("success", False),
            "data": result.get("expert_results", {}),
            "data_ids": result.get("data_ids", []),
            "visuals": result.get("visuals", []),
            "metadata": {
                "generator": "langgraph_workflow",
                "workflow_type": workflow_type
            },
            "summary": f"LangGraph 工作流执行: {workflow_type}"
        }
```

### Phase 4: 注册 LangGraph 工具

**文件**: `backend/app/tools/langgraph/__init__.py` (新建)

```python
from .workflow_tool import LangGraphWorkflowTool

__all__ = ["LangGraphWorkflowTool"]
```

**文件**: 修改 `backend/app/tools/__init__.py`

确保 LangGraph 工具被自动注册。

## 文件清单

### 新建文件
```
backend/app/agent/langgraph/
├── __init__.py           # 包初始化
├── states.py             # LangGraph 状态定义
├── quick_trace_graph.py  # 快速溯源流程图
└── executor.py          # LangGraph 执行器

backend/app/tools/langgraph/
├── __init__.py
└── workflow_tool.py       # LangGraph 工具
```

### 修改文件
```
backend/requirements.txt   # 添加 LangGraph 依赖
backend/app/tools/__init__.py  # 确保工具被注册
```

## 测试计划

### 单元测试
- 测试 LangGraph 状态初始化
- 测试快速溯源流程图构建
- 测试 LangGraph 执行器

### 集成测试
- 测试 LangGraph 工具的 execute 方法
- 测试与现有 ExecutionContext 的兼容性
- 测试数据格式转换（UDF v2.0）

### 功能测试
- 测试快速溯源流程的完整执行
- 测试并行专家执行
- 测试错误处理和重试机制

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LangGraph 依赖冲突 | 中 | 在测试环境验证依赖版本 |
| 状态序列化问题 | 低 | 使用 Pydantic 确保类型安全 |
| 工具调用兼容性 | 中 | 适配层处理签名差异 |
| 性能回退 | 低 | 保留现有 ToolDependencyGraph 作为备选 |

## 验证步骤

1. 安装依赖并验证 LangGraph 导入
2. 运行单元测试确保核心功能正常
3. 集成测试验证与现有系统兼容
4. 功能测试验证快速溯源流程正确执行
5. 性能测试对比 LangGraph 和原始实现

## 回退计划

如果发现问题：
1. 禁用 LangGraph 工具（通过工具注册表配置）
2. 移除 LangGraph 依赖
3. 恢复为原始 ToolDependencyGraph 实现
