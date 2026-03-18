# Agent 架构对比和优化建议

## 当前架构 vs 优化建议

### 当前架构（较复杂）

```
┌─────────────────────────────────────────────────────────┐
│                    ReActAgent                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │              ReActLoop                             │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  │  │
│  │  │Reflexion   │  │ReWOO       │  │MemoryTools │  │  │
│  │  │Handler     │  │Executor    │  │Handler     │  │  │
│  │  └────────────┘  └────────────┘  └────────────┘  │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  │  │
│  │  │AutoToken   │  │Agent       │  │Simplified  │  │  │
│  │  │Manager     │  │Logger      │  │Context     │  │  │
│  │  └────────────┘  └────────────┘  │Builder     │  │  │
│  │                                   └────────────┘  │  │
│  │  ┌────────────┐  ┌────────────┐                   │  │
│  │  │ReAct       │  │Tool        │                   │  │
│  │  │Planner     │  │Executor    │                   │  │
│  │  └────────────┘  └────────────┘                   │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │         ExpertRouter (V3)                         │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │Weather   │ │Component │ │Viz       │          │  │
│  │  │Expert    │ │Expert    │ │Expert    │ ...      │  │
│  │  │  ┌────┐  │ │  ┌────┐  │ │  ┌────┐  │          │  │
│  │  │  │Exe │  │ │  │Exe │  │ │  │Exe │  │          │  │
│  │  │  │cut  │  │ │  │cut  │  │ │  │cut  │  │          │  │
│  │  │  │tor  │  │ │  │tor  │  │ │  │tor  │  │          │  │
│  │  │  └────┘  │ │  └────┘  │ │  └────┘  │          │  │
│  │  └──────────┘ └──────────┘ └──────────┘          │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │         HybridMemoryManager                       │  │
│  │  Working → Session → LongTerm                    │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────┐
│              Tool Registry (~55 tools)              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ Query   │ │Analysis │ │  Viz    │ │ Office  │  │
│  │  (25)   │ │  (15)   │ │  (8)    │ │  (7)    │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
└─────────────────────────────────────────────────────┘

问题：
❌ 层次过深（4-5层）
❌ 多个 Executor 可能重复逻辑
❌ 专家系统与 ReAct 循环边界不清晰
❌ 调试困难
```

---

### 建议架构（简化版）

```
┌─────────────────────────────────────────────────────────┐
│                    ReActAgent                           │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              ReActLoop (核心)                     │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────────┐ │  │
│  │  │         统一执行引擎                         │ │  │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐       │ │  │
│  │  │  │Planner  │ │Executor │ │Memory   │       │ │  │
│  │  │  │(决策)   │ │(执行)   │ │Manager  │       │ │  │
│  │  │  └─────────┘ └─────────┘ └─────────┘       │ │  │
│  │  │                                             │ │  │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐       │ │  │
│  │  │  │Reflexion│ │Token    │ │Logger   │       │ │  │
│  │  │  │(错误恢复)│ │Manager  │ │(日志)   │       │ │  │
│  │  │  └─────────┘ └─────────┘ └─────────┘       │ │  │
│  │  └─────────────────────────────────────────────┘ │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────────┐ │  │
│  │  │      ExpertRouter (可选，按需启用)           │ │  │
│  │  │                                               │ │  │
│  │  │  Weather ←→ Component ←→ Viz ←→ Report      │ │  │
│  │  │    (共享统一执行引擎，而非独立 Executor)      │ │  │
│  │  └─────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────┐
│              Tool Registry (~55 tools)              │
│                                                     │
│  每个工具包含：                                     │
│  - validate_params()    参数验证                    │
│  - get_examples()       使用示例                    │
│  - get_dependencies()   依赖声明                    │
│  - execute()            执行逻辑                    │
└─────────────────────────────────────────────────────┘

优点：
✅ 简化为2-3层
✅ 统一执行引擎，避免重复
✅ 专家系统与核心循环清晰分离
✅ 易于调试和维护
```

---

## 关键改进点

### 1. 统一执行引擎

**当前问题**：
```python
# ReActLoop 有自己的 ToolExecutor
ReActLoop.executor = ToolExecutor()

# 每个 Expert 也有自己的 Executor
WeatherExpert.executor = WeatherExecutor()
ComponentExpert.executor = ComponentExecutor()
```

**建议方案**：
```python
# 统一的执行引擎
class UnifiedExecutionEngine:
    """统一的工具和专家执行引擎"""

    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.expert_registry = ExpertRegistry()

    async def execute_tool(self, tool_name: str, **kwargs):
        """执行工具"""
        tool = self.tool_registry.get(tool_name)
        return await tool.execute(**kwargs)

    async def execute_expert(self, expert_name: str, query: str):
        """执行专家（复用工具执行逻辑）"""
        expert = self.expert_registry.get(expert_name)
        return await expert.analyze(query, executor=self)
```

**好处**：
- ✅ 避免重复代码
- ✅ 统一错误处理
- ✅ 统一日志记录
- ✅ 更容易测试

---

### 2. 工具增强

**当前工具**：
```python
class MyTool(LLMTool):
    async def execute(self, **kwargs):
        # 直接执行，无验证
        return await self._do_something(**kwargs)
```

**增强工具**：
```python
class MyTool(LLMTool):
    # 依赖声明
    dependencies = ["get_data_tool"]
    required_context = ["data_id"]

    # 参数验证
    def validate_params(self, **kwargs) -> Tuple[bool, str]:
        if "param1" not in kwargs:
            return False, "缺少必需参数 param1"
        if kwargs.get("param1") < 0:
            return False, "param1 必须大于0"
        return True, ""

    # 使用示例
    def get_examples(self) -> List[Dict]:
        return [
            {
                "description": "基本用法",
                "params": {"param1": 10, "param2": "value"}
            },
            {
                "description": "高级用法",
                "params": {"param1": 20, "param2": "value", "option": True}
            }
        ]

    # 执行（带验证）
    async def execute(self, **kwargs):
        # 1. 验证参数
        is_valid, error = self.validate_params(**kwargs)
        if not is_valid:
            raise InvalidParameterError(error)

        # 2. 检查依赖
        self._check_dependencies(kwargs)

        # 3. 执行逻辑
        result = await self._do_something(**kwargs)

        # 4. 格式化返回
        return self._format_result(result)
```

**好处**：
- ✅ 防止错误参数
- ✅ 提供 LLM 可读的示例
- ✅ 自动检查依赖
- ✅ 统一返回格式

---

### 3. System Prompt 自动生成

**当前问题**：
- System Prompt 手动编写
- 工具更新后需要手动更新 Prompt
- 容易遗漏重要信息

**建议方案**：
```python
class PromptGenerator:
    """自动生成 System Prompt"""

    def generate_system_prompt(self) -> str:
        """根据当前工具和配置生成 System Prompt"""

        prompt_parts = [
            self._generate_basic_instructions(),
            self._generate_tool_usage_workflow(),
            self._generate_available_tools(),
            self._generate_tool_dependencies(),
            self._generate_examples()
        ]

        return "\n\n".join(prompt_parts)

    def _generate_tool_usage_workflow(self) -> str:
        """生成工具使用流程"""
        return """
## 工具使用流程

1. 【必须】先读取文档/数据
2. 【分析】确认需要修改的内容
3. 【执行】选择合适的工具
4. 【验证】检查结果

⚠️ 重要：Office 工具修改前必须先读取！
"""

    def _generate_tool_dependencies(self) -> str:
        """生成工具依赖说明"""
        deps = {}
        for tool in self.tool_registry:
            for dep in tool.dependencies:
                if tool.name not in deps:
                    deps[tool.name] = []
                deps[tool.name].append(dep)

        deps_text = "\n".join([
            f"- {tool}: 需要 {', '.join(deps)} 先执行"
            for tool, deps in deps.items()
        ])

        return f"""
## 工具依赖关系

{deps_text}

注意：调用工具前请确认依赖的工具已执行。
"""
```

**好处**：
- ✅ 自动保持最新
- ✅ 包含所有必要信息
- ✅ 易于维护

---

## 实施路线图

### 阶段1：修复关键问题（1-2周）

- [x] 修复 Office 工具替换 bug
- [ ] 添加工具参数验证
- [ ] 完善工具使用文档
- [ ] 添加集成测试

### 阶段2：简化架构（2-3周）

- [ ] 设计统一执行引擎
- [ ] 重构 Expert Executor
- [ ] 简化 ReActLoop
- [ ] 更新文档

### 阶段3：增强功能（3-4周）

- [ ] 实现 Prompt 自动生成
- [ ] 添加工具依赖声明
- [ ] 实现智能建议系统
- [ ] 添加性能监控

### 阶段4：优化和安全（持续）

- [ ] 性能优化
- [ ] 安全加固
- [ ] 并发控制
- [ ] 事务支持

---

## 总结

**当前架构评价**：
- 设计思路正确
- 实现质量良好
- 但存在过度工程化的问题

**优化方向**：
1. 简化架构，减少层次
2. 统一执行引擎
3. 增强工具（验证、示例、依赖）
4. 自动化 Prompt 生成
5. 加强测试和文档

**预期收益**：
- 🚀 更易维护和调试
- 📈 更好的可扩展性
- 🛡️ 更高的可靠性
- 🤖 更好的 LLM 体验
- 🔒 更强的安全性
