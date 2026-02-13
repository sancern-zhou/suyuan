# CLAUDE.md

本文件为Claude Code在此代码库中工作时提供指导。

## 项目概述

**大气污染溯源分析系统** - FastAPI后端 + Vue 3前端

- **后端**: FastAPI (Python) - 端口8000
- **前端**: Vue 3 - 端口5174
- **核心功能**: 基于ReAct架构的智能污染源分析

## 关键目录结构

```
backend/app/
├── agent/              # ReAct Agent核心
│   ├── input_adapter.py      # 参数规范化 ("宽进严出")
│   ├── core/                 # 规划、反思、执行
│   ├── context/              # Context-Aware V2
│   ├── experts/              # 多专家Agent系统
│   │   ├── weather_executor.py     # 气象执行器
│   │   ├── component_executor.py   # 组分执行器
│   │   ├── viz_executor.py         # 可视化执行器
│   │   ├── report_executor.py      # 综合报告执行器
│   │   ├── expert_router_v3.py     # V3路由调度
│   │   └── expert_health_monitor.py  # 健康监控
│   └── react_agent.py        # ReAct主Agent
├── tools/              # 工具层
│   ├── query/               # 数据查询工具
│   ├── analysis/            # 分析工具 (PMF/OBM/智能图表)
│   └── visualization/       # 可视化工具
├── services/           # 服务层
│   └── image_cache.py       # 图片缓存服务（避免LLM处理大base64）
├── schemas/            # 数据模式
│   ├── unified.py           # UDF v2.0统一格式（全链路标准化）
│   ├── vocs.py             # VOCs数据
│   ├── pmf.py              # PMF结果
│   ├── obm.py              # OBM/OFP结果
│   └── chart.py            # ChartConfig图表模式
├── utils/              # 工具模块
│   ├── llm_response_parser.py     # LLM响应解析 (4策略)
│   ├── data_format_converter.py   # 数据→UDF转换
│   └── chart_data_converter.py    # 图表格式转换
└── db/                 # 数据库层
    ├── database.py          # PostgreSQL+TimescaleDB
    └── models.py            # 数据模型
```

## 核心架构原则

### 1. ReAct Agent架构
系统使用**ReAct (Reasoning + Acting)**模式进行智能分析：
- 思考 → 行动 → 观察 → 循环
- 动态规划执行方案
- 工具注册表智能选择
- 真正Agent：LLM自主决策，动态工具调用

### 2. 多专家Agent系统 ⭐ 新增

**文件**: `app/agent/experts/expert_router.py`

**4个专业专家Agent**:
- **WeatherExpertAgent**: 气象数据分析（天气、轨迹、风向、上风向分析）
- **ComponentExpertAgent**: 污染物组分分析（VOCs、PM2.5、PM10、PMF、OBM、OFP源解析）
- **VizExpertAgent**: 数据可视化（图表生成、可视化分析，15种图表类型）
- **ReportExpertAgent**: 综合报告生成（分析总结、结论建议）

**专家路由器 (ExpertRouter)**:
- **智能任务路由**: 基于NLP意图解析自动选择专家（无关键词匹配）
- **依赖图调度**: 支持并行/顺序执行，可视化任务依赖关系
- **健康感知路由**: 实时监控专家健康状态，故障检测和自动降级
- **可观测性监控**: 完整执行追踪、性能指标、告警系统

**健康监控系统**:
- 实时健康检查：响应时间、成功率、错误类型统计
- 负载均衡：自动分发任务到健康专家
- 故障恢复：自动重启、降级服务、告警通知

**使用示例**:
```python
# 创建ReAct Agent
agent = create_react_agent(enable_multi_expert=True)

# 多专家任务（自动路由）
async for event in agent.analyze("综合分析广州O3污染溯源"):
    if event["type"] == "expert_result":
        result = event["data"]
        # 多专家协同完成：气象+组分+可视化+报告
```

### 3. 两阶段工具加载 (Two-Stage Tool Loading)
**文件**: `app/agent/core/planner.py`

**设计理念**：模仿Claude Code/Skills的渐进式加载架构，节省40-50% token消耗

**工作流程**:
1. **第一阶段（工具选择）**: LLM只看工具摘要（~2K tokens），选择需要的工具
   - LLM输出 `args: null` 表示需要详细schema
2. **第二阶段（参数构造）**: 按需加载详细schema（~1K tokens）+ 精简上下文（~1.5-2K tokens）
   - 调用 `_load_schema_and_construct_params()` 方法
   - 使用 `_extract_relevant_context()` 精简历史上下文（保留data_id、最近3轮操作）
   - 使用 `_build_param_construction_prompt()` 构造参数prompt
   - 第二次LLM调用生成工具参数

**关键方法**:
- `_load_schema_and_construct_params()` - 第二阶段加载协调器
- `_extract_relevant_context()` - 上下文精简（压缩比60-80%）
- `_build_param_construction_prompt()` - 参数构造prompt生成

**性能监控**：完整日志追踪（schema加载、LLM调用、上下文压缩比等）

**Token消耗对比**:
- 传统方式（全量加载）: 38.7-43.7K tokens
- 两阶段加载: 21.5-22K tokens
- **节省**: 40-50%

### 4. Input Adapter ("宽进严出")
**文件**: `app/agent/input_adapter.py`
- 参数映射：LLM模糊参数→标准参数
- 数据规范化：自动推断和验证
- 字段映射：支持`TOOL_RULES.field_mapping`
- 错误处理：抛出`InputValidationError`

### 5. Context-Aware V2 架构
**文件**: `app/agent/context/execution_context.py`

**核心**: 工具通过ExecutionContext管理数据生命周期
- 标记: `requires_context=True`
- 数据加载: `context.get_data()` / `context.get_raw_data()`
- 数据存储: `context.save_data()` → 返回`data_id`
- 外部化: 所有数据外部化自动存储

**要求**:
- 所有分析工具必须使用此架构
- 输出必须是纯字典（JSON可序列化）

#### 数据存储与访问架构规范 ⚠️ 重要

**文件**: `app/agent/context/data_context_manager.py`

**核心原则**: **存储层用字典，访问层返回类型化对象**

```python
# 架构契约 (已在DataContextManager中实现)
存储层 (save_data):
  - 输入: List[BaseModel] 或 List[Dict]  # 支持两种格式
  - 序列化: 统一转换为字典（JSON序列化）
  - 存储: JSON文件存储（灵活、可移植）

访问层 (get_data):
  - 加载: 从JSON文件加载字典数据
  - 反序列化: 根据SCHEMA_MODEL_MAP自动转换为Pydantic对象
  - 返回: List[BaseModel]  # 类型安全的Pydantic模型
```

**扁平数据 vs 嵌套数据格式处理规范** ⚠️
- **API返回的数据通常是扁平结构**（离子在顶层，如 `{"sulfate": 3.5, "nitrate": 7.5, ...}`）
- **Schema定义的格式是嵌套结构**（离子在 `components` 字段，如 `{"components": {"sulfate": 3.5, "nitrate": 7.5}}`）
- **数据格式转换必须在数据层统一处理**，不允许在分析工具层打补丁

**正确做法**（在 `DataContextManager.save_data()` 中）:
```python
# 对于 particulate_unified schema，将扁平数据转换为嵌套格式
if schema == "particulate_unified" and isinstance(standardized_records, list):
    nested_records = []
    for record in standardized_records:
        if isinstance(record, dict):
            # 使用 UnifiedParticulateData.from_raw_data() 转换
            nested_record = UnifiedParticulateData.from_raw_data(record)
            nested_records.append(nested_record.model_dump())
        else:
            nested_records.append(record)
    standardized_data = nested_records
```

**错误做法**（在分析工具中打补丁）:
```python
# ❌ 不允许：每个工具自己处理扁平/嵌套格式
def my_analysis_tool():
    if 'components' not in record:
        # 自己处理格式转换 - 禁止！
        record['components'] = extract_ions_from_top_level(record)
```

**SCHEMA_MODEL_MAP 映射表**:
```python
SCHEMA_MODEL_MAP = {
    "vocs": VOCsSample,
    "vocs_unified": UnifiedVOCsData,
    "particulate": ParticulateSample,
    "pmf_result": PMFResult,
    "chart_config": ChartConfig,
    "obm_ofp_result": OBMOFPResult,
    "guangdong_stations": UnifiedDataRecord,
    "air_quality_unified": UnifiedDataRecord,
}
```

**关键实现细节**:
1. `save_data()`: **返回字符串ID（非Handle对象）** - 工具层直接使用
   ```python
   # ✅ 正确用法 - 直接返回data_id字符串
   data_id = context.save_data(data=[...], schema="vocs_unified")
   result["data_id"] = data_id  # 字符串ID，可直接赋值

   # ❌ 错误理解 - 不返回Handle对象（已废弃）
   # handle = context.save_data(...)  # 错误！返回的是字符串
   # data_id = handle.full_id          # 不需要此步骤
   ```
   **设计理由**: 工具层99%场景只需ID字符串，直接返回最简洁

2. `get_handle()`: 需要元数据时调用（罕见场景）
   ```python
   # 需要访问record_count、quality_report等元数据时
   handle = context.get_handle(data_id)
   print(handle.record_count, handle.schema, handle.quality_report)
   ```

3. `get_data()`: 使用handle.model_class自动反序列化字典为Pydantic对象
4. `get_raw_data()`: 直接返回字典格式（用于特殊场景，如PMF/OBM结果）


### 5. LLM响应处理
**文件**: `app/utils/llm_response_parser.py`
- 4种解析策略：代码块JSON → 直接JSON → 思维链JSON → 正则提取
- 容错机制：渐进式降级

### 6. 错误恢复
三层机制: Input Adapter → Reflexion → ReAsk
- Input Adapter: 参数规范化，抛出`InputValidationError`
- Reflexion: 分析失败原因，生成修复建议
- ReAsk: 智能重试（最大2次）

### 7. 分析图片URL渲染流程

**文件**: `app/services/image_cache.py` + `app/api/image_routes.py`

**流程**:
1. 可视化工具生成base64图片
2. `ImageCache.save()` 保存图片到磁盘 `backend_data_registry/images/{image_id}.png`
3. 工具返回 `{"image_url": "/api/image/{image_id}", "markdown_image": "![title](/api/image/{image_id})"}`
4. LLM在报告中引用 `![title](/api/image/{image_id})`
5. 前端通过 `MarkdownRenderer.vue` 渲染Markdown图片标签
6. 浏览器请求 `/api/image/{image_id}` 获取图片数据

**API接口**:
- `GET /api/image/{image_id}` - 返回图片bytes（`base64.b64decode`后）
- `GET /api/image/{image_id}/info` - 返回元信息
- `DELETE /api/image/{image_id}` - 删除图片

### 8. matplotlib图表单位上标字符规范
matplotlib默认不支持Unicode上标（³²⁻μ），所有单位标签需用LaTeX格式：
- `μg/m³` → `r'$\mu$g/m$^3$'`
- `R²` → `r'R$2$'`
- 字符串加`r`前缀

已修改: `particulate_visualizer.py`, `scientific_charts/chonggou.py`

### 9. 报告图表占位符方案

**问题**: LLM生成的报告需要图表与文字混排，而非分离显示

**方案**: `[INSERT_CHART:图表类型]` 占位符 + 前端三級匹配

**占位符格式**: LLM在报告各章节插入 `[INSERT_CHART:ternary_SNA]` 等标记

**章节-图表映射**:
- 水溶性离子特征与二次生成 → ternary_SNA, sor_nor_scatter, charge_balance
- 碳组分特征 → ec_oc_scatter
- 地壳与微量元素 → crustal_boxplot
- 时空变化特征 → ion_timeseries

**前端匹配优先级**:
1. ID直接匹配 `[INSERT_CHART:viz_1]`
2. 图表类型匹配 `[INSERT_CHART:crustal_boxplot]`
3. 标题模糊匹配（fallback）

**文件**:
- 后端: `component_executor.py` - Prompt模板定义占位符
- 前端: `ReActMessageList.vue` - `matchChartByType()` 函数

### 10. 办公助理工具完整结果返回机制 ⚠️ 重要

**设计理念**：办公助理工具（bash/read_file/analyze_image/Office工具）返回的完整数据内容必须传递给 LLM，不做截断或摘要化处理。

**核心机制**：
- **主要格式化**：`loop.py:_format_observation` 方法负责将工具结果格式化为助手消息
- **完整数据传递**：办公助理工具的 data 字段完整内容直接传递给 LLM
- **压缩保护**：`context_compressor.py` 中的 COMPRESSION_PROMPT 确保上下文压缩时保留完整结果

**已支持的办公助理工具**：
```python
# loop.py:_format_observation 中的工具识别
is_image_tool = generator == "analyze_image"  # 图片分析工具
is_file_tool = generator == "read_file"      # 文件读取工具
is_office_tool = generator in ["word_processor", "excel_processor", "ppt_processor"]  # Office三件套
```

**新增办公助理工具配置流程**：
1. 确保工具的 `metadata.generator` 字段正确设置工具名称
2. 在 `loop.py:_format_observation` 方法中添加工具识别逻辑：
   ```python
   is_new_tool = generator == "your_new_tool_name"
   if is_new_tool and "key_field" in data:
       lines.append(f"**完整结果**:\n{data['key_field']}")
   ```
3. 在 `context_compressor.py:COMPRESSION_PROMPT` 中更新工具列表：
   ```
   - 办公助理工具（bash/read_file/analyze_image/Office工具/your_new_tool）：完整保留工具返回的 data 字段内容
   ```

**工具返回格式规范**：
```python
# 办公助理工具应返回以下格式
{
    "status": "success",
    "success": True,
    "data": {
        "result_field": "完整的分析结果或文件内容",  # 核心数据
        # ... 其他辅助字段
    },
    "metadata": {
        "schema_version": "v2.0",
        "generator": "tool_name"  # 必须正确设置，用于 loop.py 识别
    },
    "summary": "简短摘要"
}
```

**相关文件**：
- `backend/app/agent/core/loop.py` - 主要格式化逻辑（第1585-1635行）
- `backend/app/agent/memory/context_compressor.py` - 压缩保护（第18-65行）

### 11. 工具返回数据架构规范
**图片可视化 vs LLM总结分离**：
- 图片用于可视化：`visuals` 字段存图表占位符 `[IMAGE:id]`
- 结论供LLM总结：`data.statistics` 字段存分析结论

```python
{
    "data": {
        "statistics": {...},    # ✅ LLM可读取的分析结论
        "series": [...],        # 简化的时序数据
    },
    "visuals": [...],           # 图片占位符
    "data_id": "particulate_analysis:xxx"  # 指向存储层
}
```

**存储层只保存可序列化的摘要**：
```python
summary = {
    "status": "success",
    "available_ions": [...],
    "statistics": {...},        # 关键分析结论
    "visuals": [{"id": "...", "title": "...", "type": "..."}]
}
```

**禁止**：保存整个 `result` 对象（可能导致序列化失败）

## 关键文件位置

**数据模式**:
- `app/schemas/unified.py` - UDF v2.0统一格式（全链路标准化+visuals字段）
- `app/schemas/vocs.py` - VOCs数据模式
- `app/schemas/pmf.py` / `app/schemas/unified_pmf.py` - PMF结果模式
- `app/schemas/obm.py` / `app/schemas/unified_obm.py` - OBM/OFP结果模式
- `app/schemas/visualization.py` - v3.1图表格式（15种类型+增强元数据）

**工具实现** (Context-Aware V2):
- `app/tools/analysis/calculate_pmf/tool.py` - PMF源解析
- `app/tools/analysis/calculate_obm_ofp/tool_v2_context.py` - OBM/OFP分析
- `app/tools/visualization/generate_chart/tool.py` - 图表生成
- `app/tools/analysis/smart_chart_generator/tool.py` - 智能图表

**转换器**:
- `app/utils/data_format_converter.py` - VOCs/PMF/OBM → UDF v2.0
- `app/utils/chart_data_converter.py` - 分析结果 → v3.1图表（含验证增强）
- `app/utils/data_standardizer.py` - 字段映射系统（260个字段）

## 外部API
- **站点查询**: `180.184.91.74:9095`
- **数据查询**: `180.184.91.74:9091/9092/9093` (监测/VOCs/颗粒物)
- **上风向分析**: `180.184.91.74:9095`

### 外部 API 响应格式规范
**文件**: `app/api_response_formats.py`

记录所有外部 API 的响应数据结构，用于工具层的数据解析：

| API 类型 | 端口 | 端点 | 响应路径 |
|----------|------|------|----------|
| 空气质量监测 | 9091 | `180.184.91.74:9091/api/uqp/query` | `data` |
| VOCs组分 | 9092 | `180.184.91.74:9092/api/uqp/query` | `dataList` 或 `data` |
| 颗粒物组分 | 9093 | `180.184.91.74:9093/api/uqp/query` | `data.result.resultOne` |
| 站点/气象 | 9095 | `180.184.91.74:9095` | 多接口各异 |

**工具与端口映射**:
- `get_guangdong_regular_stations` → 9091（空气质量监测：PM2.5, O3, NO2, SO2, CO, AQI）
- `get_vocs_data` → 9092（VOCs组分数据）
- `get_pm25_ionic/carbon/crustal` → 9093（颗粒物组分数据）

**使用方式**:
```python
from app.api_response_formats import get_api_format, get_response_path

# 获取特定 API 格式定义
fmt = get_api_format("particulate")
path = get_response_path("particulate")
```

**工具开发规范**:
1. 新增外部 API 时，在此文件注册响应格式
2. 工具的 `_seek_records` 方法应使用注册的路径解析数据
3. 记录字段映射：API 列名 → 标准字段名

## 数据存储规范

### UDF v2.0 全链路统一格式 ✅
**核心原则**: 宽进严出、自动标准化、版本追踪、元数据增强

**标准格式**:
```python
{
    "status": "success|failed|partial|empty",
    "success": true|false,
    "data": [records...],              # 标准化后的数据列表
    "metadata": {
        "schema_version": "v2.0",      # ✅ 必填：格式版本
        "field_mapping_applied": true, # ✅ 必填：是否已标准化
        "field_mapping_info": {...},   # ✅ 必填：字段映射统计
        "source_data_ids": ["..."],    # 源数据ID列表
        "generator": "tool_name",       # 生成工具名称
        "scenario": "scenario",         # 场景标识
        "record_count": 100,            # 记录数量
        "generator_version": "2.0.0"    # 工具版本
    },
    "summary": "..."                    # 摘要信息
}
```

**多图表场景**:
```python
{
    "status": "success",
    "success": true,
    "data": null,                       # v2.0不使用data承载图表
    "visuals": [                        # ✅ 统一visuals字段
        {
            "id": "visual_001",
            "type": "chart|map|table",
            "schema": "chart_config",
            "payload": {图表v3.1格式},
            "meta": {
                "schema_version": "v2.0",
                "source_data_ids": ["..."],
                "generator": "tool_name",
                "scenario": "scenario"
            }
        }
    ],
    "metadata": {
        "schema_version": "v2.0",
        "record_count": 1
    }
}
```

**核心要求**:
- ✅ 所有工具输出必须包含 `schema_version="v2.0"`
- ✅ 强制字段：`field_mapping_applied`、`field_mapping_info`
- ✅ 图表工具必须返回 `visuals` 格式（不使用data字段）
- ✅ 所有输出必须是纯字典（JSON可序列化）
- ✅ 通过 `DataContextManager.save_data()` 自动应用标准化

### Chart v3.1 图表格式
所有图表数据必须遵循v3.1标准，与UDF v2.0配合使用:
```python
{
    "id": "图表ID",
    "type": "pie|bar|line|timeseries|wind_rose|profile|map|...",  # 15种类型
    "title": "标题",
    "data": {图表数据},
    "meta": {
        "schema_version": "3.1",          # ✅ 图表格式版本
        "generator": "生成器标识",          # 与UDF v2.0对齐
        "original_data_ids": ["源数据ID"], # 源数据ID
        "scenario": "场景标识",             # 与UDF v2.0对齐
        "layout_hint": "wide|tall|map-full|side|main",  # 布局提示
        "interaction_group": "chart_interaction",  # 交互组
        "data_flow": ["data_source", "chart_config"]  # 数据流
    }
}
```

**支持的图表类型（15种）**:
- 基础: pie, bar, line, timeseries
- 气象: wind_rose（风向玫瑰图）, profile（边界层廓线图）
- 3D: scatter3d, surface3d, line3d, bar3d, volume3d
- 高级: heatmap, radar, map（高德地图）

**数据类型**:
- 饼图: `[{"name": "...", "value": ...}]`
- 柱/线图: `{"x": [], "y": []}` 或 `{"x": [], "series": [...]}`
- 时序图: `{"x": [], "series": [{"name": "...", "data": [...]}]}`
- 风向玫瑰: `{"sectors": [{"direction": "N", "avg_speed": 3.5}]}`
- 边界层廓线: `{"altitudes": [...], "elements": [{"name": "温度", "data": [...]}]}`
- 地图: `{"map_center": {lng, lat}, "zoom": 12, "layers": [...]}`

## 全链路v2.0规范约定 ✅

### 字段映射系统
**文件**: `app/utils/data_standardizer.py`
- **总映射数**: 260个字段
- **气象字段**: 110个（支持中文字段：气温→temperature_2m）
- **类别覆盖**: 时间、站点、坐标、污染物、AQI、VOCs、颗粒物、气象、元数据
- **特性**: 支持大小写不敏感、驼峰命名、中文映射

### 强制性标准化钩子
**文件**: `app/agent/context/data_context_manager.py`
- **强制标准化schema**: weather、air_quality_unified、vocs_unified、particulate等
- **自动标记**: 所有数据自动添加 `schema_version="v2.0"`
- **字段映射**: 自动应用字段标准化，添加 `field_mapping_applied=true`

### 工具改造状态
**已统一UDF v2.0格式的工具有**:
- ✅ `get_weather_data` - 气象数据工具（visuals格式）
- ✅ `calculate_pmf` - PMF源解析工具
- ✅ `calculate_obm_ofp` - OBM/OFP分析工具
- ✅ `analyze_upwind_enterprises` - 上风向企业分析工具（visuals格式）
- ✅ `smart_chart_generator` - 智能图表生成工具（visuals格式）

**新工具开发规范**:
1. 使用 `data_standardizer.standardize()` 标准化数据
2. 返回格式包含 `schema_version="v2.0"`
3. 图表工具使用 `visuals` 字段，不使用 `data` 字段
4. 包含完整元数据：`generator`、`scenario`、`field_mapping_info`

### 前端适配
**文件**: `frontend/src/components/VisualizationPanel.vue`
- **处理visuals**: 自动检测并渲染 `content.visuals` 数组
- **Meta传递**: 完整传递 `meta` 中的 `source_data_ids`、`generator` 等信息
- **布局支持**: 支持5种布局模式（wide, tall, map-full, side, main）

### 测试规范
**文件**: `tests/test_udf_v2_full_chain.py`
- **测试框架**: pytest
- **覆盖率**: 13个测试用例，涵盖全链路
- **验证点**: 数据格式、字段映射、工具集成、向后兼容性
- **运行命令**: `pytest tests/test_udf_v2_full_chain.py -v`

## 设计理念

**"LLM完全自由 + 系统智能适配"**
- LLM自由输出任何内容，系统智能处理
- 移除max_tokens限制，支持大型输出
- 多策略解析确保鲁棒性

**"内部工具的输出要直接符合UDF v2.0标准格式和v3.1图表格式，避免多次转换"**
- 前端图表渲染需直接适配UDF v2.0格式
- 通过DataContextManager强制标准化，确保全链路v2.0统一

## 专家系统工作流程文档

**气象专家分析工作流程（快速溯源场景）**
- **文件**: `backend/docs/weather_expert_workflow.md`
- **内容**: 详细的气象专家工具调用顺序、数据流转、输出标准
- **包含**: ERA5历史数据获取、天气预报、后向轨迹分析、上风向企业分析



## 快速开始

```bash
# 后端
cd backend && start.bat  # Windows
python -m uvicorn app.main:app --reload
# 或
chmod +x start.sh && ./start.sh  # Linux/macOS

# 端口: 8000

# 前端
cd frontend && npm install && npm run dev
# 端口: 5174
```

---

**详细实施和API文档，请参阅项目中的专门markdown文件。**
**我讨厌你每次修改完都生成一个总结文档，即使他没必要。**
**禁止生成带EMOJI图标的测试脚本。**