# 快速溯源任务清单（标准版 - 多专家子Agent）

## 🚀 快速任务清单（直接使用）

**使用方法**：Agent应该直接调用 `TodoWrite(task_list_file="backend/config/task_lists/quick_trace_standard_multi_agent.md")` 加载以下任务清单。

**⚠️ 执行前必读**：
1. 加载任务清单后，**必须重新阅读每个任务的详细步骤**（在"完整任务列表"章节）
2. 每个任务可能需要调用**多个工具**，不要遗漏
3. 具体参数（城市、日期、污染物）在**执行时动态使用**

```python
# ✅ 正确用法：直接加载文件
TodoWrite(task_list_file="backend/config/task_lists/quick_trace_standard_multi_agent.md")

# ❌ 错误用法：手动输入会丢失详细的工具调用和参数说明
TodoWrite(items=[...])  # 不推荐
```

---

## 📋 使用指南（给Agent阅读）

你是专家模式Agent，用户要求进行污染溯源分析。本任务清单将指导你制定完整详细的执行计划。

**重要原则**：
1. 📖 **加载任务清单后，必须仔细阅读每个任务的详细步骤**（工具调用、参数说明）
2. 📝 **使用 TodoWrite 加载任务清单**：`TodoWrite(task_list_file="backend/config/task_lists/quick_trace_standard_multi_agent.md")`
3. ✅ **跟用户确认**后再开始执行
4. 🔄 **执行时逐步更新**任务状态，确保**每个工具调用都完成**
5. 📊 **每个任务完成后**生成阶段性报告（MD格式），避免分析结论丢失

---

## 🎯 全局参数（从用户查询中提取）

| 参数 | 说明 | 示例 | 提取方式 |
|------|------|------|----------|
| **station_name** | 站点名称 | "广州天河" | 从用户查询中提取 |
| **date** | 分析日期 | "2026-03-28"（"昨天"） | 解析"昨天"/"今天"/具体日期 |
| **pollutant** | 目标污染物 | "PM2.5" / "O3" | 从用户查询中提取 |
| **analysis_type** | 分析类型 | "标准溯源" | 默认标准溯源 |

**参数提取示例**：
- "对广州市昨天进行颗粒物溯源分析" → station_name="广州", date="2026-03-28", pollutant="PM2.5"
- "广州天河站今天的O3污染溯源" → station_name="广州天河", date="2026-03-29", pollutant="O3"

---

## 🤖 多专家子Agent系统

### 专家列表

1. **气象专家**（weather_expert）
   - 提示词文件：`backend/config/prompts/weather_expert.md`
   - 专长：气象条件分析、大气边界层、扩散条件、轨迹传输、上风向企业
   - 工具：get_weather_data, get_weather_forecast, meteorological_trajectory_analysis, analyze_upwind_enterprises

2. **化学专家**（chemical_expert）
   - 提示词文件：
     - PM2.5模式：`backend/config/prompts/chemical_expert_pm.md`
     - O3模式：`backend/config/prompts/chemical_expert_o3.md`
   - 专长：污染物组分分析、PMF源解析、OBM分析、组分重构
   - 工具：get_vocs_data, get_pm25_component, calculate_pm_pmf, calculate_vocs_pmf, calculate_obm_full_chemistry, calculate_reconstruction, smart_chart_generator

3. **报告专家**（report_expert）
   - 提示词文件：`backend/config/prompts/report_expert.md`
   - 专长：汇总专家分析、综合溯源结论、管控建议
   - 输入：所有专家的分析结果

### call_sub_agent 调用格式

```python
call_sub_agent(
    target_mode="expert",
    task_description="详细的任务描述，告诉专家要做什么",
    context_data={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",  # 或其他专家提示词文件
        "data_ids": ["station_info:xxx", "weather_analysis:xxx"]  # 传递给专家的数据ID列表
    }
)
```

**关键要点**：
- `task_description` 必须详细明确，告诉专家具体要做什么
- `expert_prompt_file` 根据污染物类型动态选择（PM2.5用pm，O3用o3）
- `data_ids` 包含专家需要的所有上游数据ID
- 子Agent会读取提示词文件、获取数据、调用工具、生成报告

---

## 📝 完整任务列表（6个核心任务）

### 任务1：获取城市空气质量数据

**目标**：获取目标城市的空气质量数据和站点经纬度信息

**工具调用**：
```python
# 步骤1：获取空气质量数据
query_xcai_city_history(
    cities=["{city_name}"],
    data_type="hour",
    start_time="{date} 00:00:00",
    end_time="{date} 23:00:00"
)
```

**站点经纬度**（使用城市中心坐标）：
- 广州市: 23.1291, 113.2644
- 深圳市: 22.5431, 114.0579
- 北京市: 39.9042, 116.4074
- 上海市: 31.2304, 121.4737
- 东莞市: 23.0205, 113.7518
- 佛山市: 23.0219, 113.1214
- 其他城市请查询在线地图获取中心坐标

**参数说明**：
- `cities`: 城市名称列表（如["广州市"]）
- `data_type`: "hour"（小时数据）
- `start_time/end_time`: 分析日期的时间范围
- 示例：`query_xcai_city_history(cities=["广州市"], data_type="hour", start_time="2026-03-28 00:00:00", end_time="2026-03-28 23:00:00")`

**数据处理**：
1. 从 `query_xcai_city_history` 获取空气质量数据
2. 调用站点API获取城市辖内站点经纬度（城市环境评价点）
3. 合并两个数据源，生成完整的站点信息

**输出**：
- `data_id`: "air_quality_unified:xxx"
- 数据内容：城市名称、空气质量数据（PM2.5、O3等）、站点经纬度

**阶段性报告**：
```markdown
## 1. 城市空气质量数据

**城市名称**：{城市名称}
**数据时间**：{date}
**数据记录数**：{记录数}条
**主要污染物**：{主要污染物及浓度}
```

**TodoWrite示例**：
```python
TodoWrite(items=[{
    'content': '获取城市空气质量数据：广州市',
    'status': 'in_progress'
}])
```

---

### 任务2：气象数据分析【气象专家子Agent】

**目标**：分析气象条件对污染扩散的影响（包含历史数据和预报数据）

**专家**：气象专家（weather_expert）

**工具调用**：
```python
call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析气象条件对污染扩散的影响（包含历史数据和预报数据）。

    **站点信息**：
    - 站点名称：{station_name}
    - 经纬度：({lat}, {lon})
    - 分析日期：{date}

    **分析要求**：
    1. 读取专家提示词文件：backend/config/prompts/weather_expert.md
    2. 使用站点信息获取气象数据：
       a) get_weather_data - 获取历史气象数据（前3天ERA5数据）
          - data_type: "era5"
          - lat: {lat}
          - lon: {lon}
          - start_time: {date前3天}
          - end_time: {date前1天}
       b) get_weather_forecast - 获取未来15天预报数据
          - lat: {lat}
          - lon: {lon}
          - location_name: {station_name}
          - forecast_days: 15
          - past_days: 1  # 获取昨天+今天00:00~当前时刻完整数据
          - hourly: True
          - daily: True
    3. 生成专业的气象条件分析报告（MD格式），包含：
       - 大气扩散能力诊断
       - 光化学污染气象条件
       - 轨迹传输路径分析
       - 上风向企业污染源识别
       - 不利扩散条件识别
       - 天气系统与环流
       - 气象预报与污染潜势
       - 控制建议与应对方案
    4. 生成可视化图表（使用smart_chart_generator）
    """,
    context_data={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]  # 从任务1获取
    }
)
```

**输出**：
- `data_id`: "weather_analysis:xxx"
- 分析内容：气象条件分析报告（MD格式）+ 可视化图表

**阶段性报告**：
```markdown
## 2. 气象条件分析报告

### 2.1 大气扩散能力诊断
{气象专家生成的分析内容}

### 2.2 气象预报与污染潜势
{气象专家生成的预报内容}

![气象图表](/api/image/xxx)
```

**依赖**：任务1完成

**TodoWrite示例**：
```python
TodoWrite(items=[{
    'content': '气象数据分析（气象专家）',
    'status': 'in_progress'
}])
```

---

### 任务3：后向轨迹分析【气象专家子Agent】

**目标**：分析后向轨迹，追溯污染来源

**专家**：气象专家（weather_expert）

**工具调用**：
```python
call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析后向轨迹，追溯污染来源。

    **站点信息**：
    - 站点名称：{station_name}
    - 经纬度：({lat}, {lon})
    - 分析日期：{date}

    **分析要求**：
    1. 读取专家提示词文件：backend/config/prompts/weather_expert.md
    2. 使用站点信息和气象分析结果进行轨迹分析：
       a) meteorological_trajectory_analysis - 后向轨迹分析
          - lat: {lat}
          - lon: {lon}
          - start_time: {date} 00:00:00
          - hours: 72  # 72小时后向轨迹
    3. 生成专业的轨迹分析报告（MD格式），包含：
       - 轨迹聚类与源区识别
       - 传输通道和距离
       - 高度结构分析
       - 污染来源推断
    4. 生成轨迹地图可视化
    """,
    context_data={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx", "weather_analysis:xxx"]  # 从任务1、2获取
    }
)
```

**输出**：
- `data_id`: "trajectory_analysis:xxx"
- 分析内容：后向轨迹分析报告（MD格式）+ 轨迹地图

**阶段性报告**：
```markdown
## 3. 后向轨迹分析报告

### 3.1 轨迹特征分析
{气象专家生成的轨迹分析内容}

### 3.2 污染来源推断
{气象专家生成的来源推断内容}

![后向轨迹图](/api/image/xxx)
```

**依赖**：任务2完成

**TodoWrite示例**：
```python
TodoWrite(items=[{
    'content': '后向轨迹分析（气象专家）',
    'status': 'in_progress'
}])
```

---

### 任务4：上风向企业分析【气象专家子Agent】

**目标**：分析上风向潜在污染企业

**专家**：气象专家（weather_expert）

**工具调用**：
```python
call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析上风向潜在污染企业。

    **站点信息**：
    - 站点名称：{station_name}
    - 经纬度：({lat}, {lon})
    - 分析日期：{date}

    **分析要求**：
    1. 读取专家提示词文件：backend/config/prompts/weather_expert.md
    2. 使用轨迹分析结果进行企业分析：
       a) analyze_upwind_enterprises - 上风向企业分析
          - lat: {lat}
          - lon: {lon}
          - analysis_date: {date}
    3. 生成企业分析报告（MD格式），包含：
       - 企业分布与影响评估
       - 企业分级管控建议（5km/20km/50km）
       - TOP10高影响污染源清单
    4. 生成企业分布地图
    """,
    context_data={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["trajectory_analysis:xxx"]  # 从任务3获取
    }
)
```

**输出**：
- `data_id`: "enterprise_analysis:xxx"
- 分析内容：上风向企业分析报告（MD格式）+ 企业分布地图

**阶段性报告**：
```markdown
## 4. 上风向企业分析报告

### 4.1 企业分布与影响评估
{气象专家生成的企业分析内容}

### 4.2 TOP10高影响污染源
{气象专家生成的TOP10清单}

![企业分布图](/api/image/xxx)
```

**依赖**：任务3完成

**可选**：是（如无企业数据可跳过）

**TodoWrite示例**：
```python
TodoWrite(items=[{
    'content': '上风向企业分析（气象专家）',
    'status': 'in_progress'
}])
```

---

### 任务5：污染物组分分析【化学专家子Agent】

**目标**：分析污染物组分，推断污染来源（包含PMF/OBM等深度分析）

**专家**：化学专家（chemical_expert）

**工具调用（PM2.5模式）**：
```python
expert_prompt_file = "backend/config/prompts/chemical_expert_pm.md"

call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析PM2.5组分，推断污染来源（包含PMF源解析和7大组分重构）。

    **站点信息**：
    - 站点名称：{station_name}
    - 经纬度：({lat}, {lon})
    - 分析日期：{date}

    **分析要求**：
    1. 读取专家提示词文件：{expert_prompt_file}
    2. 调用数据查询工具（按优先级尝试）：
       a) get_pm25_component - PM2.5完整组分（32个因子，优先）
          - station_id: {station_id}
          - start_date: {date}
          - end_date: {date}
       b) get_particulate_components - PM2.5组分分析（备选）
       c) get_pm25_ionic - 颗粒物离子组分（备选）
       d) get_pm25_carbon - 颗粒物碳组分（备选）
       e) get_pm25_crustal - 颗粒物地壳元素（备选）
    3. 调用深度分析工具（基于数据查询结果）：
       a) calculate_pm_pmf - PMF源解析
          - data_id: {pm25_ionic_data_id}
          - gas_data_id: {pm25_carbon_data_id}
       b) calculate_reconstruction - 7大组分重构
          - data_id: {pm25_component_data_id}
          - reconstruction_type: "full"
       c) calculate_carbon - 碳组分分析
          - data_id: {carbon_data_id}
       d) calculate_soluble - 水溶性离子分析
          - data_id: {ionic_data_id}
    4. 调用可视化工具：
       a) smart_chart_generator - 生成专业图表
          - data_id: {analysis_data_id}
          - chart_purpose: "PMF源解析和组分重构分析"
    5. 生成专业的组分分析报告（MD格式），包含：
       - 区域时序对比分析
       - 颗粒物组分诊断
       - PMF源解析深度分析
       - 7大组分重构分析
       - 二次颗粒物生成评估（SOR、NOR）
       - 源贡献季节性变化
    """,
    context_data={
        "expert_prompt_file": expert_prompt_file,
        "data_ids": ["station_info:xxx"]  # 从任务1获取
    }
)
```

**工具调用（O3模式）**：
```python
expert_prompt_file = "backend/config/prompts/chemical_expert_o3.md"

call_sub_agent(
    target_mode="expert",
    task_description=f"""
    分析O3组分和VOCs，推断污染来源（包含PMF源解析和OBM分析）。

    **站点信息**：
    - 站点名称：{station_name}
    - 经纬度：({lat}, {lon})
    - 分析日期：{date}

    **分析要求**：
    1. 读取专家提示词文件：{expert_prompt_file}
    2. 调用数据查询工具：
       a) get_vocs_data - VOCs组分数据
          - station_id: {station_id}
          - start_date: {date}
          - end_date: {date}
    3. 调用深度分析工具：
       a) calculate_vocs_pmf - VOCs PMF源解析
          - data_id: {vocs_data_id}
       b) calculate_obm_full_chemistry - OBM分析（EKMA/PO3/RIR）
          - vocs_data_id: {vocs_data_id}
          - mode: "all"  # 完整分析
    4. 调用可视化工具：
       a) smart_chart_generator - 生成专业图表
          - data_id: {vocs_data_id}
          - chart_purpose: "VOCs组分和OFP分析"
    5. 生成专业的组分分析报告（MD格式），包含：
       - 区域时序对比分析
       - VOCs组分诊断
       - PMF源解析深度分析
       - OBM/OFP臭氧生成潜势分析
       - O3-NOx-VOCs敏感性分析
       - 光化学进程分析
    """,
    context_data={
        "expert_prompt_file": expert_prompt_file,
        "data_ids": ["station_info:xxx"]  # 从任务1获取
    }
)
```

**输出**：
- `data_id`: "component_analysis:xxx"
- 分析内容：污染物组分分析报告（MD格式）+ 源解析图表

**阶段性报告**：
```markdown
## 5. 污染物组分分析报告

### 5.1 组分特征分析
{化学专家生成的组分分析内容}

### 5.2 PMF源解析结果
{化学专家生成的PMF分析内容}

### 5.3 二次生成评估
{化学专家生成的二次生成分析内容}

![组分分析图](/api/image/xxx)
```

**依赖**：任务1完成（可与任务2-4并行）

**可选**：是（如无数据可跳过）

**TodoWrite示例**：
```python
TodoWrite(items=[{
    'content': '污染物组分分析（化学专家）',
    'status': 'in_progress'
}])
```

---

### 任务6：生成综合报告【报告专家子Agent】

**目标**：汇总所有专家分析，生成综合溯源报告

**专家**：报告专家（report_expert）

**工具调用**：
```python
call_sub_agent(
    target_mode="expert",
    task_description=f"""
    汇总所有专家分析，生成综合溯源报告。

    **基本信息**：
    - 站点名称：{station_name}
    - 分析日期：{date}
    - 污染物：{pollutant}

    **分析要求**：
    1. 读取专家提示词文件：backend/config/prompts/report_expert.md
    2. 使用所有 data_ids 获取各专家的分析结果：
       - station_info:xxx（任务1）
       - weather_analysis:xxx（任务2）
       - trajectory_analysis:xxx（任务3）
       - enterprise_analysis:xxx（任务4）
       - component_analysis:xxx（任务5）
    3. 汇总所有专家的章节内容
    4. 生成综合溯源结论：
       - 主要来源识别
       - 贡献比例评估
       - 关键影响因素总结
    5. 生成管控建议：
       - 近期管控措施（应急响应）
       - 中长期管控建议（根本治理）
       - 监测建议
    6. 输出完整的综合溯源报告（MD格式）
    """,
    context_data={
        "expert_prompt_file": "backend/config/prompts/report_expert.md",
        "data_ids": [
            "station_info:xxx",      # 从任务1获取
            "weather_analysis:xxx",   # 从任务2获取
            "trajectory_analysis:xxx", # 从任务3获取
            "enterprise_analysis:xxx", # 从任务4获取
            "component_analysis:xxx"  # 从任务5获取
        ]
    }
)
```

**输出**：
- 完整的综合溯源报告（MD格式）

**最终报告结构**：
```markdown
# {站点名称}{污染物}污染溯源分析报告

**分析时间**：{date}
**站点**：{station_name}
**污染物**：{pollutant}

---

## 1. 站点信息
{任务1的阶段性报告}

## 2. 气象条件分析报告
{任务2的阶段性报告}

## 3. 后向轨迹分析报告
{任务3的阶段性报告}

## 4. 上风向企业分析报告
{任务4的阶段性报告}

## 5. 污染物组分分析报告
{任务5的阶段性报告}

---

## 6. 综合溯源结论

### 6.1 主要来源识别
{报告专家生成的综合结论}

### 6.2 关键影响因素
{报告专家生成的因素分析}

## 7. 管控建议

### 7.1 近期管控措施（应急响应）
{报告专家生成的应急建议}

### 7.2 中长期管控建议（根本治理）
{报告专家生成的长期建议}
```

**依赖**：所有任务完成

**TodoWrite示例**：
```python
TodoWrite(items=[{
    'content': '生成综合报告（报告专家）',
    'status': 'in_progress'
}])
```

---

## 🔄 完整执行流程（给Agent参考）

### 步骤1：读取任务清单
```python
read_file(path="backend/config/task_lists/quick_trace_standard_multi_agent.md")
```

### 步骤2：提取全局参数
从用户查询中提取：
- station_name: "广州"
- date: "2026-03-28"（解析"昨天"）
- pollutant: "PM2.5"（从"颗粒物"推断）

### 步骤3：制定详细任务清单
```python
TodoWrite(items=[
    {'content': '定位站点：广州', 'status': 'pending'},
    {'content': '气象数据分析（气象专家）', 'status': 'pending'},
    {'content': '后向轨迹分析（气象专家）', 'status': 'pending'},
    {'content': '上风向企业分析（气象专家）', 'status': 'pending'},
    {'content': '污染物组分分析（化学专家）', 'status': 'pending'},
    {'content': '生成综合报告（报告专家）', 'status': 'pending'}
])
```

### 步骤4：跟用户确认
```
## 标准溯源分析计划（多专家子Agent模式）

**基本信息**：
- 站点：广州
- 时间：2026-03-28
- 污染物：PM2.5
- 执行模式：标准（约3分钟）

**任务清单**：
[ ] 定位站点：广州
[ ] 气象数据分析（🌤️ 气象专家）
[ ] 后向轨迹分析（🛰️ 气象专家）
[ ] 上风向企业分析（🛰️ 气象专家）
[ ] 污染物组分分析（🧪 化学专家）
[ ] 生成综合报告（📝 报告专家）

**专家配置**：
- 气象专家：backend/config/prompts/weather_expert.md
- 化学专家：backend/config/prompts/chemical_expert_pm.md
- 报告专家：backend/config/prompts/report_expert.md

**说明**：每个专家任务由独立的子Agent完成，确保分析专业性。

是否开始执行？
```

### 步骤5：按计划执行

**执行任务1**：
```python
# 标记任务1为进行中
TodoWrite(items=[..., {'content': '获取城市空气质量数据', 'status': 'in_progress'}, ...])

# 执行工具
query_xcai_city_history(cities=["广州市"], data_type="hour", start_time="2026-03-28 00:00:00", end_time="2026-03-28 23:00:00")
bash(command='curl "http://180.184.91.74:9095/api/station-district/by-city?city_name=广州&fields=name,lat,lon&station_type_id=1.0"')
# 保存返回的 data_id

# 标记任务1完成
TodoWrite(items=[..., {'content': '定位站点：广州', 'status': 'completed'}, ...])

# 生成阶段性报告（MD格式）
```

**执行任务2**：
```python
# 标记任务2为进行中
TodoWrite(items=[..., {'content': '气象数据分析（气象专家）', 'status': 'in_progress'}, ...])

# 调用气象专家子Agent
call_sub_agent(
    target_mode="expert",
    task_description="详细任务描述...",
    context_data={
        "expert_prompt_file": "backend/config/prompts/weather_expert.md",
        "data_ids": ["station_info:xxx"]
    }
)
# 保存返回的 data_id

# 标记任务2完成
TodoWrite(items=[..., {'content': '气象数据分析（气象专家）', 'status': 'completed'}, ...])

# 生成阶段性报告（MD格式）
```

**继续执行任务3-5...**

**执行任务6**：
```python
# 标记任务6为进行中
TodoWrite(items=[..., {'content': '生成综合报告（报告专家）', 'status': 'in_progress'}])

# 调用报告专家子Agent
call_sub_agent(
    target_mode="expert",
    task_description="详细任务描述...",
    context_data={
        "expert_prompt_file": "backend/config/prompts/report_expert.md",
        "data_ids": ["station_info:xxx", "weather_analysis:xxx", ...]
    }
)

# 标记任务6完成
TodoWrite(items=[..., {'content': '生成综合报告（报告专家）', 'status': 'completed'}])

# 输出最终报告
```

---

## ⚠️ 重要提示

### 1. 任务清单要详细
每个任务都要明确：
- **输入**：需要哪些 data_id
- **输出**：返回什么 data_id
- **工具调用**：具体的工具名称和参数
- **阶段性报告**：生成MD格式的分析结论

### 2. 数据链路要完整
- 每个 data_id 都要记录
- 后续任务通过 data_id 引用前面的数据
- 确保数据不丢失

### 3. 阶段性报告要生成
- 每完成一个任务就生成阶段性报告（MD格式）
- 避免分析结论丢失
- 最终报告汇总所有阶段性报告

### 4. 错误处理
- 可选任务失败时继续执行
- 在最终报告中说明缺失部分
- 不要因为某个任务失败就放弃整个流程

### 5. 用户可见性
- 每个任务的状态变化都要更新 TodoWrite
- 让用户看到进度
- 增强信任感

---

## 📊 预计耗时

- 任务1（定位站点）：~5秒
- 任务2（气象数据分析）：~30秒
- 任务3（后向轨迹分析）：~60秒
- 任务4（上风向企业分析）：~10秒
- 任务5（污染物组分分析）：~60秒
- 任务6（生成综合报告）：~15秒

**总计**：约3分钟

---

## ✅ 质量检查清单

在提交最终报告前，检查：
- [ ] 所有任务都已完成（或标记为跳过）
- [ ] 每个 data_id 都正确传递
- [ ] 阶段性报告都已生成
- [ ] 最终报告包含所有章节
- [ ] 图表都能正常显示
- [ ] 结论和建议都有数据支撑
- [ ] 报告格式正确（MD格式）

---

**任务清单版本**：v2.0（多专家子Agent版）
**最后更新**：2026-03-29
**维护者**：Claude
