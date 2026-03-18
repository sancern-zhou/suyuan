# unpack_office 工具加载问题修复报告

**日期**: 2026-02-21
**问题**: `unpack_office` 工具已注册到 `global_tool_registry`，但 ReAct Agent 实例无法访问该工具

---

## 问题根因

### 1. Agent 全局单例在模块加载时创建

**位置**: `app/routers/agent.py:138-175`

```python
# 全局 Agent 实例在模块导入时创建
multi_expert_agent_instance = create_react_agent(...)
meteorology_expert_agent_instance = create_react_agent(...)
# ...
```

### 2. 工具注册表在 Agent 创建时固定

当 Agent 实例创建时：
1. 调用 `create_react_agent()` → 创建 `ToolExecutor`
2. `ToolExecutor.__init__()` → 调用 `_register_builtin_tools()`
3. `_register_builtin_tools()` → 调用 `get_react_agent_tool_registry()`
4. 获取当前 `global_tool_registry` 中的工具列表
5. 将工具列表**复制**到 `self.tool_registry` 字典中

**问题**：即使后来 `global_tool_registry` 更新（例如新注册了 `unpack_office`），已创建的 Agent 实例的 `tool_registry` 也不会自动更新。

### 3. 模块导入顺序

```
main.py
  ├─ app.routers.agent (导入) → 创建全局 Agent 实例
  │    └─ create_react_agent() → 固定工具列表
  └─ startup_event()
       └─ initialize_llm_tools() → 验证工具注册（但 Agent 已创建）
```

---

## 修复方案

### 1. 添加工具刷新机制

**文件**: `app/agent/core/executor.py`

添加 `refresh_tools()` 方法，允许重新加载工具注册表：

```python
def refresh_tools(self):
    """刷新工具注册表（从 global_tool_registry 重新加载所有工具）"""
    logger.info("refreshing_tool_registry")

    # 清空当前注册表
    self.tool_registry.clear()

    # 重新注册所有工具
    self._register_builtin_tools()

    logger.info(
        "tool_registry_refreshed",
        tool_count=len(self.tool_registry),
        tools=list(self.tool_registry.keys())
    )
```

### 2. ReActAgent 添加刷新接口

**文件**: `app/agent/react_agent.py`

```python
def refresh_tools(self):
    """刷新工具注册表（重新加载所有工具）"""
    self.executor.refresh_tools()
    logger.info(
        "agent_tools_refreshed",
        agent_id=id(self),
        tool_count=len(self.executor.tool_registry)
    )
```

### 3. Startup 事件刷新全局 Agent

**文件**: `app/main.py`

在 `startup_event()` 中，工具初始化后刷新所有全局 Agent 实例：

```python
# 1. 初始化LLM工具（独立于数据库）
try:
    initialize_llm_tools()
    logger.info("llm_tools_initialized")

    # 🔧 刷新全局 Agent 实例的工具注册表
    try:
        from app.routers.agent import (
            multi_expert_agent_instance,
            meteorology_expert_agent_instance,
            quick_tracing_agent_instance,
            data_viz_agent_instance,
            deep_tracing_agent_instance
        )

        logger.info("refreshing_global_agent_tools")

        multi_expert_agent_instance.refresh_tools()
        meteorology_expert_agent_instance.refresh_tools()
        quick_tracing_agent_instance.refresh_tools()
        data_viz_agent_instance.refresh_tools()
        deep_tracing_agent_instance.refresh_tools()

        logger.info(
            "global_agents_refreshed",
            multi_expert_tools=len(multi_expert_agent_instance.get_available_tools()),
            # ...
        )
    except Exception as e:
        logger.warning("agent_refresh_failed", error=str(e))

except Exception as e:
    logger.error("llm_tools_initialization_failed", error=str(e), exc_info=True)
    logger.warning("continuing_without_llm_tools")
```

---

## 其他修复

### 4. 修复 Planner 工具注册表实例化问题

**文件**: `app/agent/core/planner.py:243-244`

**问题**：Planner 调用 `create_global_tool_registry()` 重新创建了新的注册表实例

**修复**：改用全局单例

```python
# ❌ 错误：重新创建注册表
from app.tools import create_global_tool_registry
registry = create_global_tool_registry()

# ✅ 正确：使用全局单例
from app.tools import global_tool_registry
tool_data = global_tool_registry._tools.get(tool_name)
```

### 5. 添加调试日志

**文件**: `app/agent/tool_adapter.py`, `app/agent/core/executor.py`

添加详细日志追踪工具加载状态：

```python
logger.info(
    "get_react_agent_tool_registry_debug",
    total_global_tools=len(global_tools),
    has_unpack_office="unpack_office" in global_tools,
    all_tools=global_tools
)

logger.info(
    "builtin_tools_registered",
    tools=registered_tools,
    count=len(real_tools),
    has_unpack_office="unpack_office" in registered_tools
)
```

---

## 验证步骤

1. **重启后端服务**：
   ```bash
   cd D:\溯源\backend
   # 按 Ctrl+C 停止当前服务
   start.bat  # 重新启动
   ```

2. **检查启动日志**：
   ```
   [info] llm_tools_initialized
   [info] refreshing_global_agent_tools
   [info] global_agents_refreshed
     multi_expert_tools=64
     meteorology_tools=64
     ...
   ```

3. **验证工具可用**：
   ```bash
   python D:\溯源\test_tool_refresh.py
   ```

   预期输出：
   ```
   [Step 4] Agent after refresh:
     - Total tools: 64
     - Has 'unpack_office': True

   [Step 5] Verification:
     [OK] unpack_office is now available in agent!
   ```

---

## 总结

### 核心问题
Agent 实例在创建时工具注册表被固定，无法感知后续的工具注册更新。

### 解决方案
1. 添加 `refresh_tools()` 机制，允许动态重新加载工具
2. 在 startup 事件中刷新所有全局 Agent 实例
3. 修复 Planner 使用错误的工具注册表实例

### 影响范围
- ✅ 所有全局 Agent 实例（5个）
- ✅ `unpack_office` 等新增工具
- ✅ 未来动态添加的工具

### 后续建议
考虑将 Agent 实例改为**延迟初始化**（首次请求时创建），避免模块加载时的时序问题。
