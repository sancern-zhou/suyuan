# PR: 新增编程模式 (Code Mode) - 工具开发智能体

## 📋 PR概述

**标题**: feat(agent): 新增编程模式 - 复用办公工具的开发智能体

**类型**: Feature Enhancement

**影响范围**:
- `backend/app/agent/prompts/` - 新增编程模式提示词
- `frontend/src/` - 新增编程模式入口

**设计原则**:
- **零新增工具**：完全复用办公助理工具
- **明确边界**：允许新增工具，禁止修改核心架构
- **安全可控**：限制工作目录和操作范围

---

## 🎯 需求背景

当前系统支持两种工作模式：
1. **助手模式** - 办公任务处理（文件、Office、Shell）
2. **专家模式** - 环境数据分析（查询、分析、可视化）

**新增需求**：
- **编程模式** - 工具开发智能体
  - **设计理念**：复用办公工具，LLM直接写代码（类似Claude Code）
  - **核心能力**：创建、编辑、测试新工具
  - **工作方式**：通过 `bash`, `read_file`, `write_file`, `edit_file` 等基础工具完成编程任务

---

## 🏗️ 架构设计

### 核心设计理念

```
编程模式 = 复用办公助理工具 + LLM直接写代码 + 明确安全边界
```

**不采用**：专门的"工具管理工具"（create_tool, edit_tool_code等）
**而是采用**：LLM像人类程序员一样，用基础工具直接操作代码文件

### 模式对比

| 特性 | 助手模式 | 专家模式 | **编程模式** |
|------|---------|---------|-------------|
| **核心理念** | 办公助理 | 数据分析专家 | **代码开发工程师** |
| **工作方式** | ReAct循环 | ReAct循环 | **ReAct循环** |
| **工具来源** | 办公工具集 | 分析工具集 | **复用办公工具（零新增）** |
| **典型任务** | 文档处理 | 污染溯源 | **创建新分析工具** |
| **参考设计** | - | - | **Claude Code** |

### 工具集设计（复用为主 + 2个便捷工具）

```python
CODE_TOOLS = {
    # === 复用办公助理工具（文件操作） ===
    "read_file": "读取文件内容（查看现有工具代码）",
    "write_file": "写入文件（创建新工具.py）",
    "edit_file": "编辑文件（修改代码、字符串替换）",
    "grep": "搜索代码内容（查找函数、类定义）",
    "search_files": "搜索文件名（找到工具目录）",
    "list_directory": "列出目录内容（浏览工具结构）",

    # === 复用办公助理工具（Shell命令） ===
    "bash": "执行Shell命令（安装依赖、运行测试、git操作、pytest）",

    # === 复用办公助理工具（代码执行） ===
    "execute_python": "执行Python代码片段（快速验证逻辑、测试导入）",

    # === 新增：编程模式便捷工具（2个） ===
    "list_tools": "列出所有工具（浏览工具库、查找类似工具、避免重复）",
    "validate_tool": "验证工具定义（语法检查、导入测试、schema验证）",

    # === 模式互调 ===
    "call_sub_agent": "调用助手Agent或专家Agent（委托任务、测试工具）",
}
```

**特点**：
- ✅ 复用8个办公工具
- ✅ 新增2个便捷工具
- ✅ 支持模式互调（通过call_sub_agent调用助手/专家模式）
- ✅ 开发周期短（2-3天）

---

## 🔒 安全边界与限制

### 工作目录

```
默认工作目录: D:\溯源（项目根目录）
```

**允许访问**：
- ✅ `backend/app/tools/` - 工具目录（增删改）
- ✅ `backend/tests/` - 测试目录（增删改）
- ✅ `backend/app/agent/prompts/` - 提示词目录（仅查看，部分修改）
- ✅ `backend/app/schemas/` - 数据模式目录（仅查看）
- ✅ `frontend/src/` - 前端源码（仅查看）

**禁止访问**：
- ❌ 系统关键目录（/etc, /sys, C:\Windows等）
- ❌ 用户数据目录（除项目目录外）
- ❌ 其他项目目录

### 操作权限

#### ✅ 允许的操作

1. **新增工具**
   - 在 `backend/app/tools/` 下创建新工具目录
   - 创建 `tool.py`, `__init__.py` 等文件
   - 示例：`backend/app/tools/analysis/my_new_tool/tool.py`

2. **修改工具**
   - 修改现有工具的代码实现
   - 修改工具参数schema
   - 优化工具逻辑

3. **注册工具**
   - 在 `backend/app/tools/xxx/__init__.py` 中添加导入
   - 在 `backend/app/agent/prompts/tool_registry.py` 中添加工具定义
   - 在 `backend/app/tools/__init__.py` 中添加全局注册

4. **创建测试**
   - 在 `backend/tests/` 下创建测试文件
   - 运行pytest测试

5. **查看代码**
   - 查看现有工具代码（作为参考）
   - 查看提示词定义
   - 查看数据模式定义

#### ❌ 禁止的操作

1. **修改核心架构**
   - ❌ `backend/app/agent/react_agent.py` - ReAct主类
   - ❌ `backend/app/agent/core/loop.py` - ReAct循环引擎
   - ❌ `backend/app/agent/core/planner.py` - 规划器
   - ❌ `backend/app/agent/core/executor.py` - 执行器
   - ❌ `backend/app/agent/context/` - 上下文管理
   - ❌ `backend/app/agent/memory/` - 记忆管理

2. **修改多专家系统**
   - ❌ `backend/app/agent/experts/expert_router_v3.py` - 专家路由器
   - ❌ `backend/app/agent/experts/*_executor.py` - 专家执行器

3. **修改基础设施**
   - ❌ `backend/app/db/` - 数据库层
   - ❌ `backend/app/api/` - API路由
   - ❌ `backend/app/main.py` - 应用入口
   - ❌ `backend/app/services/llm_service.py` - LLM服务

4. **修改数据模式**
   - ❌ 修改现有schema定义（向后兼容性）
   - ❌ 删除或重命名字段

### 提示词中的安全约束

```python
# 在系统提示词中明确告知LLM边界

SAFE_BOUNDARIES = """
## 安全边界

### ✅ 你可以做的
- 在 backend/app/tools/ 目录下创建新工具
- 修改现有工具的实现代码
- 在 backend/app/agent/prompts/tool_registry.py 中注册新工具
- 在 backend/tests/ 目录下创建测试文件
- 查看现有代码作为参考

### ❌ 你不能做的
- 修改 backend/app/agent/core/ 中的核心架构代码
- 修改 backend/app/agent/experts/ 中的专家系统代码
- 修改 backend/app/db/、backend/app/api/ 中的基础设施代码
- 修改数据库模式定义（向后兼容性考虑）
- 删除或重命名现有工具（保持兼容性）

如果用户要求你修改核心架构代码，请礼貌拒绝并说明原因。
"""
```

---

## 🔄 三模式互调架构

### 模式互调关系图

```
┌─────────────┐
│ 助手模式     │ ←→ call_sub_agent → 专家模式
│ (办公任务)  │ ←→ call_sub_agent → 编程模式
└─────────────┘
       ↕
   call_sub_agent
       ↕
┌─────────────┐
│ 专家模式     │ ←→ call_sub_agent → 助手模式
│ (数据分析)  │ ←→ call_sub_agent → 编程模式
└─────────────┘
       ↕
   call_sub_agent
       ↕
┌─────────────┐
│ 编程模式     │ ←→ call_sub_agent → 助手模式（处理文档）
│ (工具开发)  │ ←→ call_sub_agent → 专家模式（测试工具）
└─────────────┘
```

### 编程模式的互调用途

#### 调用助手模式
```
场景：创建工具后，生成使用文档

用户: "创建PM2.5年均值工具，并生成使用文档"

LLM（编程模式）:
1. write_file("backend/app/tools/analysis/calculate_annual_mean/tool.py", ...)
2. validate_tool(tool_name="calculate_annual_mean")
3. call_sub_agent(
    mode="assistant",
    task="为calculate_annual_mean工具生成使用文档，保存到docs/tools/calculate_annual_mean.md"
)

助手模式:
→ write_file → 创建Markdown文档
→ 完成
```

#### 调用专家模式
```
场景：创建工具后，用真实数据测试

用户: "创建PM2.5年均值工具并用2024年广州数据测试"

LLM（编程模式）:
1. write_file("backend/app/tools/analysis/calculate_annual_mean/tool.py", ...)
2. validate_tool(tool_name="calculate_annual_mean")
3. call_sub_agent(
    mode="expert",
    task="使用calculate_annual_mean工具分析2024年广州PM2.5数据"
)

专家模式:
→ get_pm25_ionic → calculate_annual_mean → 返回分析结果

编程模式:
→ 测试通过，工具可以正常使用
```

### call_sub_agent工具说明

```python
# 编程模式中的call_sub_agent
call_sub_agent(
    mode: "assistant" | "expert",  # 调用哪个模式
    task: str,                     # 委托的任务描述
    context: Optional[Dict] = None # 额外上下文
)
```

---

## 🔄 典型工作流程

### 场景1：创建新工具

```
用户: 创建一个计算PM2.5年均值的工具

LLM执行流程:
─────────────────────────────────────────────
Step 1: 浏览现有工具结构
[Action] list_directory("backend/app/tools/analysis")
[Observation] 看到 calculate_pmf/, calculate_obm_ofp/ 等目录

Step 2: 查看类似工具代码
[Action] read_file("backend/app/tools/analysis/calculate_pmf/tool.py", limit=100)
[Observation] 了解LLMTool基类、execute方法、UDF v2.0格式

Step 3: 创建新工具目录和代码
[Action] write_file(
    path="backend/app/tools/analysis/calculate_annual_mean/tool.py",
    content='''from app.tools.base import LLMTool
class CalculateAnnualMeanTool(LLMTool):
    async def execute(self, data_context_manager, data_id, year=None):
        # 计算年均值逻辑
        ...
'''
)

Step 4: 创建__init__.py
[Action] write_file(
    path="backend/app/tools/analysis/calculate_annual_mean/__init__.py",
    content="from .tool import CalculateAnnualMeanTool"
)

Step 5: 语法检查
[Action] bash("python -m py_compile backend/app/tools/analysis/calculate_annual_mean/tool.py")
[Observation] 语法检查通过 ✓

Step 6: 导入测试
[Action] execute_python("from app.tools.analysis.calculate_annual_mean import CalculateAnnualMeanTool; print('Import OK')")
[Observation] Import OK

Step 7: 注册到父目录
[Action] read_file("backend/app/tools/analysis/__init__.py")
[Observation] 查看现有导入语句

[Action] edit_file(
    path="backend/app/tools/analysis/__init__.py",
    old_text="# 工具导入",
    new_text="# 工具导入\nfrom .calculate_annual_mean import CalculateAnnualMeanTool"
)

Step 8: 注册到全局
[Action] read_file("backend/app/tools/analysis/__init__.py", offset=-20, limit=20)
[Observation] 查找全局注册部分

[Action] edit_file(
    path="backend/app/tools/analysis/__init__.py",
    old_text="global_tool_registry.register(SomeTool())",
    new_text="global_tool_registry.register(SomeTool())\nglobal_tool_registry.register(CalculateAnnualMeanTool())"
)

Step 9: 添加到工具注册表
[Action] read_file("backend/app/agent/prompts/tool_registry.py", offset=50, limit=30)
[Observation] 查看EXPERT_TOOLS定义

[Action] edit_file(
    path="backend/app/agent/prompts/tool_registry.py",
    old_text='"calculate_pmf": "PMF源解析",',
    new_text='"calculate_pmf": "PMF源解析",\n    "calculate_annual_mean": "计算PM2.5年均值",'
)

Step 10: 创建测试文件
[Action] write_file(
    path="backend/tests/test_calculate_annual_mean.py",
    content='''import pytest
from app.tools.analysis.calculate_annual_mean import CalculateAnnualMeanTool

@pytest.mark.asyncio
async def test_calculate_annual_mean():
    tool = CalculateAnnualMeanTool()
    result = await tool.execute(...)
    assert result["success"] == True
'''
)

Step 11: 运行测试
[Action] bash("cd backend && python -m pytest tests/test_calculate_annual_mean.py -v")
[Observation] 测试通过 ✓

完成: 工具创建成功！已注册到系统。
─────────────────────────────────────────────
```

### 场景2：修改现有工具

```
用户: 给calculate_pmf工具添加参数验证

LLM执行流程:
─────────────────────────────────────────────
Step 1: 查看工具代码
[Action] read_file("backend/app/tools/analysis/calculate_pmf/tool.py")
[Observation] 找到execute方法

Step 2: 定位修改位置
[Action] grep(pattern="async def execute", path="backend/app/tools/analysis/calculate_pmf/tool.py")
[Observation] 找到execute方法在line 45

Step 3: 添加参数验证
[Action] edit_file(
    path="backend/app/tools/analysis/calculate_pmf/tool.py",
    old_text="async def execute(self, data_context_manager, data_id: str):",
    new_text="""async def execute(self, data_context_manager, data_id: str, min_iterations: int = 3):
    if min_iterations < 3:
        raise ValueError("min_iterations must be >= 3")"""
)

Step 4: 语法检查
[Action] bash("python -m py_compile backend/app/tools/analysis/calculate_pmf/tool.py")
[Observation] 语法检查通过 ✓

Step 5: 运行测试
[Action] bash("cd backend && python -m pytest tests/test_calculate_pmf.py -v")
[Observation] 测试通过 ✓

完成: 参数验证已添加！
─────────────────────────────────────────────
```

### 场景3：禁止的操作示例

```
用户: 修改ReAct Agent的核心规划器，添加新的规划策略

LLM回复:
─────────────────────────────────────────────
抱歉，我无法修改核心架构代码。

backend/app/agent/core/planner.py 是ReAct Agent的核心规划器，
属于系统架构的核心组件，不允许在编程模式下修改。

如果你需要修改规划策略，建议：
1. 创建一个新的工具实现特定的规划逻辑
2. 或者联系系统开发团队进行架构级别的修改

我可以帮助你创建一个自定义规划工具，但不会修改现有的planner.py文件。
─────────────────────────────────────────────
```

---

## 📁 文件变更清单

### 新增文件（3个）

```
backend/app/agent/prompts/
└── code_prompt.py                  # ✅ 编程模式提示词（含安全边界）

backend/app/tools/code/
├── __init__.py
├── list_tools/
│   ├── __init__.py
│   └── tool.py                     # ✅ 列出所有工具（便捷浏览）
└── validate_tool/
    ├── __init__.py
    └── tool.py                     # ✅ 验证工具定义（语法+导入+schema）

frontend/src/views/
└── CodeModeView.vue                # ✅ 编程模式视图（复用聊天界面）
```

### 修改文件（仅2个）

```
backend/app/agent/prompts/
├── prompt_builder.py               # 🔧 添加"code"模式支持
└── tool_registry.py                # 🔧 添加CODE_TOOLS（完全复用assistant工具）

frontend/src/components/
└── ModeSelector.vue                # 🔧 添加"编程模式"按钮
```

---

## 🔧 核心实现

### 1. 工具注册表（扩展 + 便捷工具）

```python
# backend/app/agent/prompts/tool_registry.py (修改)

# ===== 编程模式工具（复用assistant + 2个便捷工具 + 模式互调） =====
CODE_TOOLS = {
    # 文件操作（复用）
    "read_file": "读取文件内容（查看现有工具代码）",
    "write_file": "写入文件（创建新工具.py）",
    "edit_file": "编辑文件（修改代码、字符串替换）",
    "grep": "搜索代码内容（查找函数、类定义）",
    "search_files": "搜索文件名（找到工具目录）",
    "list_directory": "列出目录内容（浏览工具结构）",

    # Shell命令（复用）
    "bash": "执行Shell命令（安装依赖、运行测试、git操作、pytest）",

    # 代码执行（复用）
    "execute_python": "执行Python代码片段（快速验证逻辑、测试导入）",

    # 编程模式便捷工具（新增）
    "list_tools": "列出所有工具（浏览工具库、查找类似工具、避免重复）",
    "validate_tool": "验证工具定义（语法检查、导入测试、schema验证）",

    # 模式互调
    "call_sub_agent": "调用助手Agent或专家Agent（委托任务、测试工具、生成文档）",
}

CODE_TOOL_ORDER = [
    # 浏览
    "list_directory", "list_tools", "search_files", "read_file",

    # 搜索
    "grep", "search_files",

    # 编辑
    "write_file", "edit_file",

    # 执行
    "execute_python", "bash", "validate_tool",

    # 模式互调
    "call_sub_agent"
]

def get_tools_by_mode(mode: str) -> Dict[str, str]:
    """根据模式获取工具列表"""
    if mode == "assistant":
        return ASSISTANT_TOOLS
    elif mode == "expert":
        return EXPERT_TOOLS
    elif mode == "code":  # ✅ 新增
        return CODE_TOOLS
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

### 2. 模式互调示例

#### 场景1：调用助手模式生成文档

```
用户: "创建新工具并生成使用文档"

LLM（编程模式）:
─────────────────────────────────────────────
Step 1-3: 创建工具代码...
[Action] write_file("backend/app/tools/analysis/my_tool/tool.py", ...)

Step 4: 调用助手模式生成文档
[Action] call_sub_agent(
    mode="assistant",
    task="为my_tool工具生成使用文档，包括参数说明、使用示例、注意事项"
)

助手模式返回:
✅ 文档已生成：backend/docs/tools/my_tool.md

完成: 工具创建成功，使用文档已生成。
─────────────────────────────────────────────
```

#### 场景2：调用专家模式测试工具

```
用户: "创建新工具并用真实数据测试"

LLM（编程模式）:
─────────────────────────────────────────────
Step 1-3: 创建工具代码...
[Action] write_file("backend/app/tools/analysis/my_tool/tool.py", ...)

Step 4: 调用专家模式测试
[Action] call_sub_agent(
    mode="expert",
    task="使用my_tool工具分析2024年广州PM2.5数据，验证功能是否正常"
)

专家模式返回:
✅ 工具测试通过，分析结果：PM2.5年均值为35μg/m³

完成: 工具创建成功，真实数据测试通过。
─────────────────────────────────────────────
```

### 3. 编程模式提示词（含安全边界）

```python
# backend/app/agent/prompts/code_prompt.py

from typing import List

CODE_MODE_TOOLS = [
    ("read_file", "读取文件内容（查看现有工具代码）"),
    ("write_file", "写入文件（创建新工具.py）"),
    ("edit_file", "编辑文件（修改代码、字符串替换）"),
    ("grep", "搜索代码内容（查找函数、类定义）"),
    ("search_files", "搜索文件名（找到工具目录）"),
    ("list_directory", "列出目录内容（浏览工具结构）"),
    ("bash", "执行Shell命令（安装依赖、运行测试、git操作）"),
    ("execute_python", "执行Python代码片段（快速验证逻辑）"),
    ("call_sub_agent", "调用助手Agent或专家Agent（委托任务、测试工具）"),
]


def build_code_prompt(available_tools: List[str]) -> str:
    """构建编程模式系统提示词"""

    tools_text = "\n".join([
        f"- {name}: {desc}"
        for name, desc in CODE_MODE_TOOLS
        if name in available_tools
    ])

    return f"""# 角色定义
你是一个专业的**Python代码开发工程师**，负责帮助用户开发、调试和维护工具。

## 核心能力
1. **创建新工具**：根据需求生成完整的工具代码
2. **编辑现有工具**：修改、优化、调试工具代码
3. **测试工具**：编写测试用例、验证功能
4. **调试问题**：定位和修复代码错误

## 工作目录
```
项目根目录: D:\溯源（当前目录）
```

## 安全边界 ⚠️ 重要

### ✅ 你可以做的
- **新增工具**：在 `backend/app/tools/` 目录下创建新工具
- **修改工具**：修改现有工具的实现代码（`backend/app/tools/**/tool.py`）
- **注册工具**：
  - 在 `backend/app/tools/xxx/__init__.py` 中添加导入
  - 在 `backend/app/tools/xxx/__init__.py` 中添加全局注册
  - 在 `backend/app/agent/prompts/tool_registry.py` 中添加工具定义
- **创建测试**：在 `backend/tests/` 目录下创建测试文件
- **查看代码**：查看现有代码作为参考

### ❌ 你不能做的
- **修改核心架构**：
  - `backend/app/agent/core/` - ReAct循环、规划器、执行器
  - `backend/app/agent/experts/` - 专家路由器、专家执行器
  - `backend/app/agent/context/` - 上下文管理
  - `backend/app/agent/memory/` - 记忆管理
- **修改基础设施**：
  - `backend/app/db/` - 数据库层
  - `backend/app/api/` - API路由
  - `backend/app/main.py` - 应用入口
- **修改数据模式**：不修改现有schema定义（向后兼容性）
- **删除工具**：不删除或重命名现有工具

**如果用户要求修改核心架构代码，请礼貌拒绝并说明原因。**

## 工具架构说明

所有工具继承自 `app.tools.base.LLMTool` 基类：

```python
from app.tools.base import LLMTool, ToolMetadata
from typing import Dict, Any
import structlog

logger = structlog.get_logger()

class MyTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="my_tool",
            description="工具功能描述",
            category="analysis",  # query/analysis/visualization/utility
            version="1.0.0",
            metadata=ToolMetadata(
                requires_context=True,  # 数据分析工具需要ExecutionContext
                requires_task_list=False
            )
        )

    async def execute(self, data_context_manager, **kwargs) -> Dict[str, Any]:
        # 工具执行逻辑
        return {{
            "status": "success",
            "success": True,
            "data": {{...}},
            "metadata": {{
                "schema_version": "v2.0",
                "generator": "my_tool"
            }},
            "summary": "执行成功"
        }}
```

## 工作流程

### 创建新工具
1. 使用 `list_directory` 浏览工具目录结构
2. 使用 `read_file` 查看类似工具的代码
3. 使用 `write_file` 创建新工具的 `tool.py`
4. 使用 `write_file` 创建 `__init__.py`
5. 使用 `bash python -m py_compile` 检查语法
6. 使用 `execute_python` 测试导入
7. 使用 `edit_file` 注册工具（修改 `__init__.py`）
8. 使用 `bash pytest` 运行测试

### 修改现有工具
1. 使用 `grep` 查找需要修改的代码位置
2. 使用 `read_file` 查看相关代码
3. 使用 `edit_file` 进行精确替换
4. 使用 `bash python -m py_compile` 检查语法
5. 使用 `bash pytest` 运行测试

### 调试工具错误
1. 使用 `grep` 搜索错误信息
2. 使用 `read_file` 查看相关代码
3. 使用 `execute_python` 快速验证修复
4. 使用 `bash` 运行完整测试

## 可用工具

{tools_text}

## 模式互调

你可以通过 `call_sub_agent` 工具调用其他模式：

### 调用助手模式
```python
call_sub_agent(
    mode="assistant",
    task="为工具生成使用文档、处理Office文件、创建测试数据"
)
```

**典型场景**：
- 生成工具使用文档（Markdown格式）
- 处理Office文件（Word/Excel/PPT）
- 创建测试数据文件

### 调用专家模式
```python
call_sub_agent(
    mode="expert",
    task="测试新工具功能、验证数据分析结果、生成可视化图表"
)
```

**典型场景**：
- 用真实数据测试新工具
- 验证工具返回的数据格式
- 生成测试报告和可视化

## 可用工具

## 注意事项

1. **代码质量**
   - 遵循PEP 8规范
   - 添加类型注解
   - 包含文档字符串
   - 完善错误处理

2. **工具分类**
   - query: 数据查询工具
   - analysis: 数据分析工具（需要ExecutionContext）
   - visualization: 可视化工具
   - utility: 通用工具

3. **返回格式**
   - 数据分析工具：UDF v2.0格式（status、success、data、metadata、summary）
   - 通用工具：简化格式 {{success, data, summary}}

4. **测试验证**
   - 创建工具后必须测试
   - 修改工具后验证功能
   - 使用pytest运行单元测试

5. **文件路径**
   - 工具代码：`backend/app/tools/{{category}}/{{tool_name}}/tool.py`
   - 测试文件：`backend/tests/test_{{tool_name}}.py`

记住：你就像人类程序员一样，使用基础工具完成开发任务，但遵守安全边界！
"""
```

### 3. 提示词构建器扩展

```python
# backend/app/agent/prompts/prompt_builder.py (修改)

from typing import Literal, List, Optional
from .assistant_prompt import build_assistant_prompt
from .expert_prompt import build_expert_prompt
from .code_prompt import build_code_prompt  # ✅ 新增
from .tool_registry import get_tools_by_mode, get_tool_order
import structlog

logger = structlog.get_logger()

# ✅ 扩展AgentMode类型
AgentMode = Literal["assistant", "expert", "code"]


def build_react_system_prompt(
    mode: AgentMode,
    available_tools: Optional[List[str]] = None
) -> str:
    """构建ReAct系统提示词（三模式架构）"""
    if available_tools is None:
        tools_dict = get_tools_by_mode(mode)
        available_tools = list(tools_dict.keys())

    mode_tools = get_tools_by_mode(mode)
    filtered_tools = [t for t in available_tools if t in mode_tools]

    if "call_sub_agent" not in filtered_tools:
        filtered_tools.append("call_sub_agent")

    logger.info(
        "building_prompt",
        mode=mode,
        tool_count=len(filtered_tools)
    )

    # ✅ 根据模式构建Prompt
    if mode == "assistant":
        return build_assistant_prompt(filtered_tools)
    elif mode == "expert":
        return build_expert_prompt(filtered_tools)
    elif mode == "code":  # ✅ 新增
        return build_code_prompt(filtered_tools)
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

---

## 🎨 UI实现（复用现有界面）

### ModeSelector 扩展

```vue
<!-- frontend/src/components/ModeSelector.vue (修改) -->

<template>
  <div class="mode-selector">
    <button
      :class="{ active: mode === 'expert' }"
      @click="setMode('expert')"
      title="数据分析模式"
    >
      <i class="icon-chart"></i>
      专家模式
    </button>
    <button
      :class="{ active: mode === 'assistant' }"
      @click="setMode('assistant')"
      title="办公助手模式"
    >
      <i class="icon-document"></i>
      助手模式
    </button>
    <!-- ✅ 新增：编程模式 -->
    <button
      :class="{ active: mode === 'code' }"
      @click="setMode('code')"
      title="工具开发模式"
    >
      <i class="icon-code"></i>
      编程模式
    </button>
  </div>
</template>
```

### 编程模式视图（复用聊天界面）

```vue
<!-- frontend/src/views/CodeModeView.vue -->

<template>
  <div class="code-mode-view">
    <!-- 复用现有聊天界面 -->
    <ReactAnalysisView
      :mode="'code'"
      :placeholder="'编程模式：告诉我你需要创建或修改什么工具？'"
    />
  </div>
</template>

<script setup>
import ReactAnalysisView from './ReactAnalysisView.vue'
</script>
```

---

## 📊 测试计划

### 集成测试

```python
# tests/test_code_mode.py

import pytest
from app.agent.react_agent import create_react_agent

@pytest.mark.asyncio
async def test_code_mode_create_tool():
    """测试编程模式：创建新工具"""
    agent = create_react_agent()

    events = []
    async for event in agent.analyze(
        "创建一个计算PM2.5年均值的工具，路径为backend/app/tools/analysis/calculate_annual_mean/tool.py",
        manual_mode="code"
    ):
        events.append(event)
        if event["type"] == "complete":
            break

    # 验证使用了write_file工具
    action_events = [e for e in events if e["type"] == "action"]
    assert any("write_file" in str(e) for e in action_events)

    # 验证最终答案包含成功信息
    final_answer = events[-1]["data"]["answer"]
    assert "创建成功" in final_answer or "tool.py" in final_answer

@pytest.mark.asyncio
async def test_code_mode_modify_tool():
    """测试编程模式：修改现有工具"""
    agent = create_react_agent()

    events = []
    async for event in agent.analyze(
        "给calculate_pmf工具添加参数验证：min_iterations必须>=3",
        manual_mode="code"
    ):
        events.append(event)
        if event["type"] == "complete":
            break

    # 验证使用了edit_file工具
    action_events = [e for e in events if e["type"] == "action"]
    assert any("edit_file" in str(e) for e in action_events)

@pytest.mark.asyncio
async def test_code_mode_call_assistant():
    """测试编程模式：调用助手模式生成文档"""
    agent = create_react_agent()

    events = []
    async for event in agent.analyze(
        "创建calculate_mean工具并调用助手模式生成使用文档",
        manual_mode="code"
    ):
        events.append(event)
        if event["type"] == "complete":
            break

    # 验证调用了助手模式
    action_events = [e for e in events if e["type"] == "action"]
    assert any("call_sub_agent" in str(e) and "assistant" in str(e) for e in action_events)

@pytest.mark.asyncio
async def test_code_mode_call_expert():
    """测试编程模式：调用专家模式测试工具"""
    agent = create_react_agent()

    events = []
    async for event in agent.analyze(
        "创建calculate_mean工具并调用专家模式用真实数据测试",
        manual_mode="code"
    ):
        events.append(event)
        if event["type"] == "complete":
            break

    # 验证调用了专家模式
    action_events = [e for e in events if e["type"] == "action"]
    assert any("call_sub_agent" in str(e) and "expert" in str(e) for e in action_events)

@pytest.mark.asyncio
async def test_code_mode_security_boundary():
    """测试编程模式：安全边界（拒绝修改核心架构）"""
    agent = create_react_agent()

    events = []
    async for event in agent.analyze(
        "修改ReAct Agent的planner，添加新的规划策略",
        manual_mode="code"
    ):
        events.append(event)
        if event["type"] == "complete":
            break

    # 验证LLM拒绝修改核心架构
    final_answer = events[-1]["data"]["answer"]
    assert "无法修改" in final_answer or "不允许" in final_answer or "核心架构" in final_answer

@pytest.mark.asyncio
async def test_code_mode_debug_tool():
    """测试编程模式：调试工具错误"""
    agent = create_react_agent()

    events = []
    async for event in agent.analyze(
        "调试calculate_pmf工具，报错ValueError: data_id is required",
        manual_mode="code"
    ):
        events.append(event)
        if event["type"] == "complete":
            break

    # 验证使用了grep/read_file/edit_file等调试工具
    action_events = [e for e in events if e["type"] == "action"]
    assert any(tool in str(e) for e in action_events for tool in ["grep", "read_file", "edit_file"])
```

---

## ✅ 验收标准

### 功能完整性

- [ ] 支持通过文件操作创建新工具
- [ ] 支持编辑现有工具代码
- [ ] 支持调试工具错误
- [ ] 支持注册工具到系统
- [ ] 支持运行测试（bash pytest、execute_python）
- [ ] **支持模式互调（调用助手/专家模式）**
- [ ] **支持安全边界（拒绝修改核心架构）**

### 工具复用

- [ ] 复用8个办公助理工具
- [ ] 新增2个便捷工具（list_tools, validate_tool）
- [ ] 支持call_sub_agent模式互调
- [ ] 最小化新增代码

### 代码质量

- [ ] 遵循现有工具开发规范
- [ ] 包含完整类型注解
- [ ] 包含结构化日志

### 安全性

- [ ] 提示词明确安全边界
- [ ] LLM拒绝修改核心架构代码
- [ ] 工作目录限制在项目根目录

### 测试覆盖

- [ ] 集成测试覆盖核心场景
- [ ] 模式互调测试通过
- [ ] 安全边界测试通过
- [ ] 手动测试通过典型工作流

---

## 📅 开发计划

### Day 1: 核心功能
- 扩展工具注册表（CODE_TOOLS）
- 编写编程模式提示词（含安全边界）
- 实现prompt_builder扩展

### Day 2: 测试与优化
- 集成测试（创建/修改/调试/安全边界场景）
- Bug修复
- 文档完善

**总计**: 2-3个工作日

---

## 🚀 后续优化方向

1. **代码模板库** - 提供常用工具代码模板
2. **自动测试生成** - 根据schema生成测试用例
3. **代码审查** - LLM检查代码质量
4. **版本控制** - 集成git操作（创建分支、提交）

---

## 📝 相关链接

- [工具基类定义](../backend/app/tools/base/__init__.py)
- [办公工具完整总结](./office_tools_complete_summary.md)
- [双模式架构文档](./dual_mode_architecture.md)

---

** reviewers **:
- @backend-team

** assignees **:
- @developer-name

** labels**:
- enhancement
- new-feature
- code-mode
- claude-code-style
- security-boundaries
