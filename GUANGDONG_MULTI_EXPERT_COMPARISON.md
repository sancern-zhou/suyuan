# 广东省多专家并行溯源系统对比分析

## 对比时间
2026-03-29

## 对比范围

- **原系统**: `ExpertRouterV3` (app/agent/experts/expert_router_v3.py) - 广东省多专家并行溯源
- **新系统**: `quick_trace_standard_multi_agent.md` (任务清单驱动的多专家子Agent)

---

## 一、原系统工作流程分析（ExpertRouterV3）

### 架构概述

```python
ExpertRouterV3（专家路由器V3）
├── StructuredQueryParser（结构化查询解析器）
├── ExpertPlanGenerator（专家计划生成器）
├── TaskList（任务列表管理）
├── SessionManager（会话管理器）
└── 专家执行器
    ├── WeatherExecutor（气象专家）
    ├── ComponentExecutor（组分专家）
    ├── VizExecutor（可视化专家）
    ├── ReportExecutor（报告专家）
    └── TemplateReportExecutor（模板报告专家）
```

### 执行流程

```
1. 结构化解析
   ├─ StructuredQueryParser.parse(user_query)
   └─ 返回 StructuredQuery（location, pollutant, time_range等）

2. 选择专家
   ├─ ExpertPlanGenerator.determine_required_experts(parsed_query)
   └─ 返回专家列表：["weather", "component", "viz", "report"]

3. 创建任务列表
   ├─ TaskList.create_task(...)

4. 并行执行分组
   ├─ 第一组（并行）：weather + component
   ├─ 第二组：viz（依赖第一组）
   └─ 第三组：report（依赖前两组）

5. 按组执行专家
   ├─ 为每组生成 ExpertTask
   ├─ 并行执行组内专家
   ├─ 收集结果
   └─ 传递给下一组

6. 生成综合报告
   └─ ReportExecutor汇总所有专家结果
```

### 并行执行策略

```python
def _build_parallel_groups(self, experts: List[str]) -> List[List[str]]:
    """根据专家列表生成可并行的执行分组"""
    groups: List[List[str]] = []
    # 第一组：weather + component（并行）
    first_group = [e for e in experts if e in ["weather", "component"]]
    if first_group:
        groups.append(first_group)
    # 第二组：viz（依赖第一组）
    if "viz" in experts:
        groups.append(["viz"])
    # 第三组：report（依赖前两组）
    if "report" in experts:
        groups.append(["report"])
    return groups or [experts]
```

### 专家执行器详解

#### 1. WeatherExecutor（气象专家）

**工具清单**：
- get_weather_data - 历史气象数据（ERA5）
- get_universal_meteorology - 通用气象数据
- get_current_weather - 当前天气
- get_weather_forecast - 天气预报
- get_fire_hotspots - 火点数据
- get_dust_data - 沙尘数据
- get_satellite_data - 卫星数据
- meteorological_trajectory_analysis - 气象轨迹分析
- trajectory_simulation - 轨迹模拟
- analyze_upwind_enterprises - 上风向企业分析
- analyze_trajectory_sources - 轨迹源清单分析（深度溯源）
- generate_map - 地图生成

**专业提示词**：weather_executor.py:498-677（10个分析框架）

#### 2. ComponentExecutor（组分专家）

**工具清单**：
- get_weather_data - 气象数据（用于气象-污染协同分析）
- get_jining_regular_stations - 济宁市区域对比（端口9096）
- get_vocs_data - VOCs组分数据（端口9092）
- get_pm25_ionic - 颗粒物离子组分
- get_pm25_carbon - 颗粒物碳组分
- get_pm25_crustal - 颗粒物地壳元素
- get_pm25_trace - 颗粒物微量元素
- get_pm25_elements - 颗粒物元素分析
- calculate_pm_pmf - PM2.5/PM10 PMF源解析
- calculate_vocs_pmf - VOCs PMF源解析
- calculate_obm_full_chemistry - OBM分析（EKMA/PO3/RIR）
- calculate_reconstruction - PM2.5 7大组分重构
- calculate_carbon - 碳组分分析（POC/SOC）
- calculate_crustal - 地壳元素分析
- calculate_soluble - 水溶性离子分析

**专业提示词**：
- PM模式：component_executor.py:665-749
- O3模式：component_executor.py:770-864

#### 3. VizExecutor（可视化专家）

**工具清单**：
- smart_chart_generator - 智能图表生成器

**功能**：
- 根据上游专家的数据生成可视化图表
- 支持跳过自带图表的数据（skip_viz_data_ids）

#### 4. ReportExecutor（报告专家）

**功能**：
- 汇总所有专家的分析结果
- 生成综合溯源报告
- 提供管控建议

**专业提示词**：report_executor.py:1087-1164

### 数据流转机制

```python
# 每个专家执行后返回 ExpertResult
class ExpertResult(BaseModel):
    status: str = "pending"
    expert_type: str = ""
    task_id: str = ""
    data_ids: List[str] = []  # 生成数据的ID列表
    skip_viz_data_ids: List[str] = []  # 需要跳过可视化的data_id
    execution_summary: ExecutionSummary
    analysis: ExpertAnalysis
    visuals: List[Dict[str, Any]] = []  # 聚合所有图表
    errors: List[Dict[str, Any]] = []

# 上游结果传递给下游专家
upstream_results: Dict[str, ExpertResult] = {}
for group in parallel_groups:
    group_tasks = plan_generator.generate(parsed_query, group, upstream_results)
    group_results = await execute_group(group_tasks, upstream_results)
    upstream_results.update(group_results)
```

### 精度模式支持

```python
async def execute_pipeline(
    self,
    user_query: str,
    precision: str = 'standard',  # fast/standard/full
    session_id: Optional[str] = None
) -> PipelineResult:
```

- **fast**: 快速筛查模式（~18秒）
- **standard**: 标准分析模式（~3分钟）
- **full**: 完整分析模式（~7-10分钟）

---

## 二、新系统工作流程分析（任务清单驱动）

### 架构概述

```python
ReActAgent（主Agent）
├── TodoWrite（任务列表工具）
├── call_sub_agent（子Agent调用工具）
└── 专家子Agent
    ├── 气象专家（weather_expert.md）
    ├── 轨迹专家（trajectory_expert.md）
    ├── 化学专家（chemical_expert_pm.md / chemical_expert_o3.md）
    └── 报告专家（report_expert.md）
```

### 执行流程

```
1. 读取任务清单模板
   └─ read_file("backend/config/task_lists/quick_trace_standard_multi_agent.md")

2. 制定执行计划
   └─ TodoWrite(items=[...])

3. 跟用户确认
   └─ 确认执行计划

4. 按计划执行任务
   任务1：定位站点（get_nearby_stations）
   任务2：气象数据分析（call_sub_agent → 气象专家）
   任务3：后向轨迹分析（call_sub_agent → 轨迹专家）
   任务4：上风向企业分析（call_sub_agent → 轨迹专家）
   任务5：污染物组分分析（call_sub_agent → 化学专家）
   任务6：生成综合报告（call_sub_agent → 报告专家）

5. 生成最终报告
```

### 专家子Agent调用方式

```python
call_sub_agent(
    target_mode="expert",
    task_description="分析气象条件对污染扩散的影响",
    context={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]
    }
)
```

---

## 三、功能对比分析

### 专家对比

| 原系统专家 | 新系统专家 | 映射关系 | 说明 |
|-----------|-----------|---------|------|
| WeatherExecutor | 气象专家 | ✅ 对应 | 相同 |
| ComponentExecutor | 化学专家 | ✅ 对应 | 相同 |
| VizExecutor | ❌ 无 | ❌ 缺失 | 新系统没有独立的可视化专家 |
| ReportExecutor | 报告专家 | ✅ 对应 | 相同 |
| ❌ 无 | 轨迹专家 | ✅ 新增 | 原系统轨迹分析在气象专家中 |

### 工具对比

#### 气象分析工具

| 原系统 | 新系统 | 状态 |
|--------|--------|------|
| get_weather_data | get_weather_data | ✅ 相同 |
| get_weather_forecast | ❓ 未明确 | ⚠️ 可能缺失 |
| meteorological_trajectory_analysis | meteorological_trajectory_analysis | ✅ 相同 |
| analyze_upwind_enterprises | analyze_upwind_enterprises | ✅ 相同 |
| analyze_trajectory_sources | ❓ 未明确 | ⚠️ 可能缺失 |
| get_fire_hotspots | ❌ 无 | ❌ 缺失 |
| get_dust_data | ❌ 无 | ❌ 缺失 |
| get_satellite_data | ❌ 无 | ❌ 缺失 |
| trajectory_simulation | ❌ 无 | ❌ 缺失 |

#### 组分分析工具

| 原系统 | 新系统 | 状态 |
|--------|--------|------|
| get_vocs_data | get_vocs_data | ✅ 相同 |
| get_pm25_ionic | get_pm25_ionic | ✅ 相同 |
| get_pm25_carbon | ❓ 未明确 | ⚠️ 可能缺失 |
| get_pm25_crustal | ❓ 未明确 | ⚠️ 可能缺失 |
| calculate_pm_pmf | ❓ 未明确 | ⚠️ 可能缺失 |
| calculate_vocs_pmf | ❓ 未明确 | ⚠️ 可能缺失 |
| calculate_obm_full_chemistry | ❓ 未明确 | ⚠️ 可能缺失 |
| calculate_reconstruction | ❓ 未明确 | ⚠️ 可能缺失 |
| calculate_carbon | ❓ 未明确 | ⚠️ 可能缺失 |

### 执行策略对比

| 维度 | 原系统 | 新系统 | 对比 |
|------|--------|--------|------|
| **并行执行** | weather + component 并行 | 顺序执行 | 原系统更快 |
| **任务依赖** | 自动管理依赖图 | 手动指定依赖 | 原系统更智能 |
| **数据传递** | upstream_results | data_id | 机制不同但等效 |
| **可视化** | 独立viz专家 | 各专家自带图表 | 原系统更专业 |
| **精度模式** | fast/standard/full | 单一模式 | 原系统更灵活 |
| **用户可见性** | TaskList + WebSocket | TodoWrite | 相当 |

---

## 四、关键差异总结

### ✅ 新系统的优势

1. **架构简洁**: 不需要复杂的ExpertRouterV3，直接使用ReAct + call_sub_agent
2. **易于维护**: 专家提示词独立存储在md文件中
3. **用户可见**: TodoWrite使整个流程对用户透明
4. **灵活扩展**: 可以轻松添加新的专家或任务

### ❌ 新系统的主要缺失

#### 🔴 严重问题

1. **缺少独立可视化专家**
   - 原系统有VizExecutor专门负责图表生成
   - 新系统依赖各专家自带图表
   - 影响：图表质量和专业性可能下降

2. **缺少深度分析工具**
   - calculate_pm_pmf（PMF源解析）
   - calculate_vocs_pmf（VOCs PMF源解析）
   - calculate_obm_full_chemistry（OBM分析）
   - calculate_reconstruction（7大组分重构）
   - 影响：溯源深度大幅下降

#### 🟡 重要问题

3. **缺少并行执行**
   - 原系统：weather + component 并行执行
   - 新系统：顺序执行
   - 影响：总耗时可能增加

4. **部分工具可能缺失**
   - get_weather_forecast（天气预报）
   - analyze_trajectory_sources（深度溯源）
   - get_pm25_carbon（碳组分）
   - get_pm25_crustal（地壳元素）

#### 🟢 小问题

5. **缺少精度模式选择**
   - 原系统支持fast/standard/full三种模式
   - 新系统只有单一模式

---

## 五、改进建议

### 优先级1（必须）：补充深度分析工具

**原因**：PMF、OBM等深度分析是溯源的核心工具，缺失会导致溯源结论质量大幅下降。

**实施方案**：
在任务5（污染物组分分析）中补充深度分析工具调用：
```python
call_sub_agent(
    target_mode="expert",
    task_description="""
    分析污染物组分，推断污染来源。

    分析要求：
    1. 读取专家提示词文件：{expert_prompt_file}
    2. 调用数据查询工具：get_vocs_data / get_pm25_ionic
    3. 调用深度分析工具：
       - PM2.5 → calculate_pm_pmf（PMF源解析）
       - O3 → calculate_vocs_pmf + calculate_obm_full_chemistry
    4. 生成专业的组分分析报告（MD格式）
    """,
    context={...}
)
```

### 优先级2（重要）：补充独立可视化专家

**原因**：独立可视化专家可以确保图表质量和专业性。

**实施方案**：
在任务清单中新增"可视化分析"任务：
```markdown
### 任务5.5：数据可视化生成【可视化专家子Agent】
- **专家**：📊 可视化专家
- **工具**：call_sub_agent
- **内容**：生成专业可视化图表
```

### 优先级3（建议）：优化并行执行

**原因**：weather + component 并行执行可以显著减少总耗时。

**实施方案**：
在任务清单中明确标注可并行的任务：
```markdown
### 并行执行说明
- 任务2（气象分析）和任务5（组分分析）可并行
- 建议使用Promise.all或类似机制并行执行
```

---

## 六、总结

### 核心差异

| 维度 | 原系统（ExpertRouterV3） | 新系统（任务清单驱动） |
|------|------------------------|---------------------|
| **架构复杂度** | 高（2300+行） | 低（md文件） |
| **并行执行** | ✅ 支持 | ❌ 顺序执行 |
| **深度分析** | ✅ PMF/OBM等 | ⚠️ 未明确 |
| **可视化** | ✅ 独立专家 | ⚠️ 各专家自带 |
| **灵活性** | ⚠️ 较低 | ✅ 高 |
| **用户可见性** | ✅ TaskList | ✅ TodoWrite |
| **专业性** | ✅ 高 | ✅ 高（使用原提示词） |

### 关键洞察

**原系统优势**：
1. 并行执行提升效率
2. 深度分析工具完善
3. 独立可视化专家保证图表质量

**新系统优势**：
1. 架构简洁，易于维护
2. 专家提示词独立管理
3. 流程对用户透明

### 最佳方案

**融合两者优势**：
1. ✅ 使用任务清单驱动架构（简洁、灵活）
2. ✅ 补充深度分析工具（PMF、OBM等）
3. ✅ 补充独立可视化专家（保证图表质量）
4. ✅ 优化并行执行策略（提升效率）

---

**生成时间**: 2026-03-29
**分析人**: Claude
**文档版本**: v1.0
