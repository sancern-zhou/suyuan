# PR: 统一架构优化 - 工作流作为ReAct工具

**作者**: Claude
**状态**: Draft
**创建时间**: 2026-03-07
**预计完成时间**: 9-10个工作日

---

## 一、优化背景

### 1.1 当前问题

项目当前存在**三套执行系统并行运行**，导致架构复杂、代码重复、维护困难：

| 执行系统 | 入口 | 特点 | 代码位置 | 问题 |
|----------|------|------|----------|------|
| **ReAct Loop** | `react_agent.py:analyze()` | LLM完全自主决策 | `app/agent/core/react_loop.py` | 工具调用粒度过细，复杂任务需要多轮交互 |
| **Expert Router V3** | `expert_router_v3.py:execute_pipeline()` | 4专家协同（气象/组分/可视化/报告） | `app/agent/experts/` | 与ReAct割裂，需要手动切换模式 |
| **Quick Trace Executor** | `quick_trace_executor.py:execute()` | 污染告警快速溯源，硬编码工具链 | `app/agent/executors/` | 重复工具加载，独立上下文 |

### 1.2 核心问题总结

1. **重复工具加载**：每个执行器都独立加载工具，维护三份同步
2. **重复上下文管理**：ExecutionContext、SimpleExecutionContext、简化版本同时存在
3. **重复并行机制**：各自的并行执行实现
4. **割裂的入口**：用户调用时需要通过`enable_multi_expert`参数手动选择模式
5. **知识问答独立**：知识库问答有独立的API路由，未集成到主Agent流程

### 1.3 优化目标

**核心理念**：工作流作为ReAct工具，实现架构统一

- **统一入口**：所有查询通过ReAct Agent，LLM自主选择工具
- **渐进能力**：提供原子工具（基础能力）和工作流工具（高级能力）
- **消除重复**：统一工具加载、上下文管理、并行执行
- **集成知识问答**：将RAG流程封装为工作流工具

---

## 二、架构方案

### 2.1 优化前后对比

#### 优化前（当前架构）

```
用户查询
    ├─ enable_multi_expert=False → ReAct Loop（原子工具）
    ├─ enable_multi_expert=True → ExpertRouter（专家系统）
    └─ 知识问答 → 独立API路由 /api/knowledge-qa/stream
```

#### 优化后（目标架构）

```
用户查询
    ↓
ReAct Agent（统一入口）
    ↓
LLM自主决策
    ↓
┌───────────────────────────────────────────────────┐
│ 工具选择                                      │
├───────────────────────────────────────────────────┤
│ 原子工具（基础能力）                          │
│ ├─ get_weather_data                           │
│ ├─ get_vocs_data                             │
│ ├─ calculate_pmf                             │
│ ├─ generate_chart                             │
│ └─ ...                                       │
│                                               │
│ 工作流工具（高级能力）                          │
│ ├─ quick_trace_workflow（快速溯源）           │
│ ├─ standard_analysis_workflow（标准分析）       │
│ ├─ deep_trace_workflow（深度溯源）            │
│ └─ knowledge_qa_workflow（知识问答）         │
└───────────────────────────────────────────────────┘
```

### 2.2 工作流工具设计

#### 工作流工具基类

```python
class WorkflowTool(ABC):
    """
    工作流工具基类

    特点：
    1. 对外表现为单个工具（LLM角度）
    2. 内部可执行多步操作、并行任务、调用子Agent
    3. 返回标准格式（符合UDF v2.0）
    """

    @abstractmethod
    def get_name(self) -> str:
        """返回工具名称"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """返回工具描述（包含适用场景）"""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工作流

        Returns:
            {
                "success": bool,
                "data": {...},          # 核心结果数据
                "visuals": [...],       # 可视化图表
                "executed_steps": [...], # 执行步骤记录
                "summary": str          # 摘要说明
            }
        """
        pass
```

---

## 三、工作流工具实现

### 3.1 快速溯源工作流（quick_trace_workflow）

**文件**: `backend/app/tools/workflow/quick_trace_workflow.py`

**功能描述**：
- **适用场景**：污染高值告警响应、快速决策支持
- **执行时间**：2-3分钟
- **执行流程**（并行）：
  1. 历史气象数据（前3天）
  2. 天气预报（未来15天）
  3. 周边城市空气质量对比
  4. 后向轨迹分析（可超时）
  5. 天气形势图AI解读

**参数**：
```python
{
    "city": "城市名称（目前支持济宁市）",
    "alert_time": "告警时间（格式：YYYY-MM-DD HH:MM:SS）",
    "pollutant": "污染物类型（如PM2.5、O3）",
    "alert_value": "告警浓度值"
}
```

**返回格式**：
```python
{
    "success": True,
    "data": {
        "summary_text": "综合溯源分析报告"
    },
    "visuals": [...],  # 轨迹图、天气形势图
    "executed_steps": [
        {"step": "historical_weather", "status": "success"},
        {"step": "forecast", "status": "success"},
        {"step": "trajectory", "status": "success", "has_trajectory": True}
    ],
    "summary": "快速溯源完成，发现主要来源为...",
    "warning_message": None  # 如有轨迹超时等警告
}
```

**实现方式**：封装现有`QuickTraceExecutor`

---

### 3.2 标准分析工作流（standard_analysis_workflow）

**文件**: `backend/app/tools/workflow/standard_analysis_workflow.py`

**功能描述**：
- **适用场景**：完整的污染溯源分析
- **执行时间**：3-5分钟
- **执行流程**（分组并行）：
  1. 第一组（并行）：气象专家 + 组分专家
  2. 第二组（串行）：可视化专家
  3. 第三组（串行）：报告专家

**参数**：
```python
{
    "city": "城市名称（如广州市、天河站）",
    "pollutant": "污染物类型（如PM2.5、O3、VOCs）",
    "start_time": "开始时间（可选，格式：YYYY-MM-DD）",
    "end_time": "结束时间（可选）",
    "precision": "精度模式（fast/standard/full，默认standard）"
}
```

**返回格式**：
```python
{
    "success": True,
    "data": {
        "final_answer": "综合分析结论",
        "conclusions": ["结论1", "结论2"],
        "recommendations": ["建议1", "建议2"]
    },
    "visuals": [...],  # 所有专家生成的图表
    "executed_steps": [
        {"expert": "weather", "status": "success", "data_ids": [...]},
        {"expert": "component", "status": "success", "data_ids": [...]},
        {"expert": "viz", "status": "success"},
        {"expert": "report", "status": "success"}
    ],
    "summary": "标准分析完成，气象+组分+可视化+报告综合分析",
    "data_ids": [...]  # 所有数据引用ID
}
```

**实现方式**：封装现有`ExpertRouterV3`

---

### 3.3 深度溯源工作流（deep_trace_workflow）

**文件**: `backend/app/tools/workflow/deep_trace_workflow.py`

**功能描述**：
- **适用场景**：深度污染源解析、完整源清单分析
- **执行时间**：7-10分钟
- **执行流程**：
  1. 完整组分分析（VOCs、PM2.5阴阳离子、碳组分）
  2. PMF源解析
  3. OBM/OFP分析
  4. 高级可视化（雷达图、3D图、热力图）
  5. 完整源清单报告

**参数**：
```python
{
    "city": "城市名称",
    "pollutant": "污染物类型（支持PM2.5、VOCs）",
    "start_time": "开始时间",
    "end_time": "结束时间",
    "station_id": "站点ID（可选）"
}
```

**返回格式**：
```python
{
    "success": True,
    "data": {
        "pmf_result": {...},      # PMF源解析结果
        "obm_result": {...},      # OBM/OFP结果
        "source_inventory": {...}, # 源清单
        "conclusions": [...]
    },
    "visuals": [...],
    "executed_steps": [...],
    "summary": "深度溯源完成，PMF+OBM+源清单综合分析"
}
```

**实现方式**：基于工具链组装

---

### 3.4 知识问答工作流（knowledge_qa_workflow）

**文件**: `backend/app/tools/workflow/knowledge_qa_workflow.py`

**功能描述**：
- **适用场景**：基于知识库的问答、专业咨询
- **执行流程**：
  1. HyDE生成假设答案（优化检索）
  2. 向量检索召回相关文档
  3. Reranker精排（可选）
  4. 构建RAG Prompt（包含对话历史）
  5. LLM流式生成回答
  6. 保存对话轮次

**参数**：
```python
{
    "query": "用户问题",
    "session_id": "会话ID（可选，用于连续对话）",
    "knowledge_base_ids": ["kb_id1", "kb_id2"],  # 知识库ID列表
    "top_k": 3,                    # 检索返回数量
    "use_reranker": False           # 是否使用重排序
}
```

**返回格式**：
```python
{
    "success": True,
    "data": {
        "answer": "LLM生成的回答",
        "sources": [
            {
                "content": "文档片段内容",
                "score": 0.95,
                "document_id": "doc_id",
                "document_name": "文档名称",
                "knowledge_base_name": "知识库名称"
            }
        ]
    },
    "visuals": [],  # 无可视化
    "executed_steps": [
        {"step": "hyde_generation", "status": "success"},
        {"step": "vector_search", "status": "success", "results_count": 3},
        {"step": "llm_generation", "status": "success"}
    ],
    "summary": "知识问答完成，基于3篇相关文档生成回答",
    "session_id": "session_id"  # 用于连续对话
}
```

**实现方式**：封装现有`knowledge_qa.py`的逻辑

---

## 四、实施步骤

### 阶段1：创建工作流工具基类

**目标**：定义工作流工具的统一接口和返回格式

**任务**：
- [ ] 创建`backend/app/tools/workflow/__init__.py`
- [ ] 创建`backend/app/tools/workflow/workflow_tool.py`
  - 定义`WorkflowTool`抽象基类
  - 定义标准返回格式
  - 实现LLM工具描述转换

**预计时间**: 0.5天

**验证标准**：
- 基类定义清晰，文档完整
- 返回格式符合UDF v2.0规范

---

### 阶段2：封装快速溯源工作流

**目标**：将`QuickTraceExecutor`包装为工作流工具

**任务**：
- [ ] 创建`backend/app/tools/workflow/quick_trace_workflow.py`
- [ ] 实现`QuickTraceWorkflow`类继承`WorkflowTool`
- [ ] 封装`QuickTraceExecutor.execute()`方法
- [ ] 转换返回格式为标准格式

**预计时间**: 1天

**验证标准**：
- 参数映射正确
- 返回格式标准
- 错误处理完善

---

### 阶段3：封装标准分析工作流

**目标**：将`ExpertRouterV3`包装为工作流工具

**任务**：
- [ ] 创建`backend/app/tools/workflow/standard_analysis_workflow.py`
- [ ] 实现`StandardAnalysisWorkflow`类
- [ ] 封装`ExpertRouterV3.execute_pipeline()`方法
- [ ] 支持precision参数（fast/standard/full）

**预计时间**: 2天

**验证标准**：
- 支持完整专家协作流程
- 返回包含所有专家结果
- visuals正确聚合

---

### 阶段4：创建深度溯源工作流

**目标**：基于工具链组装深度溯源分析

**任务**：
- [ ] 创建`backend/app/tools/workflow/deep_trace_workflow.py`
- [ ] 定义工具调用顺序：
  1. get_vocs_data / get_pm25_ionic / get_pm25_carbon
  2. calculate_pmf
  3. calculate_obm_ofp
  4. generate_chart（多种类型）
- [ ] 实现串行+并行混合执行
- [ ] 生成源清单报告

**预计时间**: 2天

**验证标准**：
- 工具调用顺序正确
- 数据流转正确
- 报告生成完整

---

### 阶段5：封装知识问答工作流

**目标**：将RAG流程包装为工作流工具

**任务**：
- [ ] 创建`backend/app/tools/workflow/knowledge_qa_workflow.py`
- [ ] 实现`KnowledgeQAWorkflow`类
- [ ] 封装`knowledge_qa.py`中的核心逻辑：
  - `generate_hypothetical_answer()`
  - `search_knowledge_bases()`
  - `build_rag_prompt()`
  - `generate_streaming_answer()`
- [ ] 支持连续对话（session_id）

**预计时间**: 1.5天

**验证标准**：
- HyDE检索正确
- Reranker可选
- 连续对话正常
- 返回格式标准

---

### 阶段6：注册工作流工具

**目标**：将工作流工具集成到全局工具注册表

**任务**：
- [ ] 修改`backend/app/tools/workflow/__init__.py`
  - 创建`WORKFLOW_TOOLS_REGISTRY`
  - 实现`get_workflow_tool()`
  - 实现`list_workflow_tools()`
- [ ] 创建`WorkflowToolLLMAdapter`适配器
- [ ] 修改`backend/app/tools/__init__.py`
  - 导入工作流工具
  - 注册到全局工具表

**预计时间**: 0.5天

**验证标准**：
- 工作流工具可被ReAct Agent发现
- LLM可获取工具描述
- 参数Schema正确

---

### 阶段7：调整提示词

**目标**：优化LLM工具选择策略

**任务**：
- [ ] 修改`backend/app/agent/prompts/react_prompts.py`
- [ ] 分类显示工具（工作流工具 vs 原子工具）
- [ ] 添加工具选择策略说明：
  ```
  工具选择策略：
  - "快速溯源"、"告警响应" → quick_trace_workflow
  - "完整溯源分析" → standard_analysis_workflow
  - "深度源解析" → deep_trace_workflow
  - "知识问答"、"专业咨询" → knowledge_qa_workflow
  ```

**预计时间**: 0.5天

**验证标准**：
- 提示词清晰
- LLM能正确选择工作流工具

---

### 阶段8：简化ReAct Agent入口

**目标**：统一入口，删除`enable_multi_expert`参数

**任务**：
- [ ] 修改`backend/app/agent/react_agent.py`
- [ ] 删除`enable_multi_expert`参数
- [ ] 删除多专家路由逻辑
- [ ] 统一使用ReAct Loop
- [ ] 保留`ExpertRouter`（供工作流工具内部使用）

**预计时间**: 1天

**验证标准**：
- 所有查询通过统一入口
- 功能无回归
- API兼容

---

### 阶段9：测试验证

**目标**：全面测试所有工作流工具

**任务**：
- [ ] 单元测试：每个工作流工具
- [ ] 集成测试：ReAct Agent调用工作流工具
- [ ] 端到端测试：
  - 快速溯源场景
  - 标准分析场景
  - 深度溯源场景
  - 知识问答场景
- [ ] 性能测试：响应时间、资源占用

**预计时间**: 2天

**测试用例**：
```python
# 快速溯源
agent = create_react_agent()
result = await agent.simple_query(
    "济宁市PM2.5告警快速溯源，告警时间2026-03-01 12:00，浓度150μg/m³"
)

# 标准分析
result = await agent.simple_query(
    "分析广州市天河站2026-02-15至2026-02-20的O3污染溯源"
)

# 深度溯源
result = await agent.simple_query(
    "深度分析济南站2026年1月的PM2.5来源，生成完整源清单"
)

# 知识问答
result = await agent.simple_query(
    "查询PMF源解析的原理和应用场景"
)
```

---

## 五、风险评估

### 5.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 工作流工具执行失败 | 高 | 中 | 添加错误处理和降级逻辑 |
| LLM工具选择错误 | 中 | 低 | 优化工具描述和提示词 |
| 性能回归 | 中 | 中 | 性能测试，优化并行执行 |
| 数据格式不一致 | 高 | 中 | 严格的格式转换和验证 |

### 5.2 兼容性风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| API接口变更 | 高 | 低 | 保持旧接口，添加废弃标记 |
| 前端适配 | 中 | 中 | 提前通知，逐步迁移 |
| 知识库API独立使用 | 中 | 低 | 保留独立API，工作流为封装 |

### 5.3 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 现有功能缺失 | 高 | 低 | 完整测试，功能对照检查 |
| 用户体验变化 | 中 | 中 | 提前通知，提供文档 |
| 运维监控失效 | 中 | 低 | 更新监控指标和告警 |

---

## 六、成功标准

### 6.1 功能完整性

- [ ] 所有原有功能正常工作
- [ ] 工作流工具返回数据完整
- [ ] 可视化图表正确渲染
- [ ] 连续对话正常

### 6.2 性能指标

- [ ] 快速溯源响应时间 < 3分钟
- [ ] 标准分析响应时间 < 5分钟
- [ ] 深度溯源响应时间 < 10分钟
- [ ] 知识问答响应时间 < 5秒

### 6.3 代码质量

- [ ] 删除重复代码 > 500行
- [ ] 测试覆盖率 > 80%
- [ ] 无新增技术债务
- [ ] 文档完整

---

## 七、后续优化

### 7.1 阶段2优化

- [ ] 删除旧的独立入口（如果确认无需保留）
- [ ] 统一错误处理机制
- [ ] 优化上下文管理

### 7.2 阶段3优化

- [ ] 添加更多工作流工具（如自动报告生成）
- [ ] 实现工作流可配置化（YAML/JSON）
- [ ] 添加工作流可视化（DAG图）

---

## 八、变更清单

### 新增文件

```
backend/app/tools/workflow/
├── __init__.py
├── workflow_tool.py              # 工作流工具基类
├── quick_trace_workflow.py       # 快速溯源工作流
├── standard_analysis_workflow.py  # 标准分析工作流
├── deep_trace_workflow.py        #    深度溯源工作流
└── knowledge_qa_workflow.py      # 知识问答工作流
```

### 修改文件

```
backend/app/tools/__init__.py          # 注册工作流工具
backend/app/agent/prompts/react_prompts.py  # 调整提示词
backend/app/agent/react_agent.py      # 简化入口
```

### 删除文件（可选，后续阶段）

```
backend/app/agent/experts/expert_router_v3.py  # 保留供内部使用
backend/app/agent/executors/quick_trace_executor.py  # 保留供内部使用
```

---

## 九、参考资料

- [ReAct Agent论文](https://arxiv.org/abs/2210.03629)
- [HyDE论文](https://arxiv.org/abs/2212.10596)
- 项目架构文档：`backend/docs/`
- 知识库文档：`backend/docs/knowledge_base/`

---

## 十、审查要点

### 代码审查

- [ ] 工作流工具接口设计合理
- [ ] 错误处理完善
- [ ] 性能无回归
- [ ] 安全性无漏洞

### 架构审查

- [ ] 架构统一性达成
- [ ] 无新增循环依赖
- [ ] 可扩展性良好
- [ ] 可维护性提升

### 业务审查

- [ ] 功能完整性
- [ ] 用户体验改善
- [ ] 文档完整准确

---

**PR状态**: 待审查
