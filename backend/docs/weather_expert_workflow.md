# 气象专家分析工作流程（快速溯源场景）

## 文档信息

- **创建日期**: 2026-02-02
- **版本**: v1.0
- **适用场景**: 快速溯源（多专家并行）
- **负责人**: ReAct Agent 系统

---

## 概述

气象专家（WeatherExpertAgent）是快速溯源场景中的核心专家之一，负责气象数据获取、分析和污染气象条件诊断。本文档详细描述气象专家的工作流程、工具调用顺序、数据流转和输出标准。

---

## 系统架构

### 1. 专家路由（ExpertRouterV3）

气象专家由 `ExpertRouterV3` 统一调度，通过 NLP 意图解析自动决定调用哪些专家。

**路由逻辑**：
- 基于自然语言查询解析（LLM）
- 无关键词匹配，无硬编码规则
- 自动识别气象分析需求
- 与其他专家并行执行

**文件位置**: `app/agent/experts/expert_router_v3.py`

### 2. 气象专家执行器（WeatherExecutor）

**文件位置**: `app/agent/experts/weather_executor.py`

**核心职责**：
1. 执行气象工具链
2. 提取统计信息
3. 生成气象分析报告（Markdown 格式）

**初始化**：
```python
executor = WeatherExecutor()
# 自动加载 11 个气象工具
```

---

## 工作流程

### 阶段 1: 计划生成（ExpertPlanGenerator）

**输入**:
- `StructuredQuery`（结构化查询）
  - `location`: 地点名称
  - `lat`, `lon`: 经纬度坐标
  - `start_time`, `end_time`: 时间范围
  - `pollutants`: 污染物列表

**输出**: 气象专家工具执行计划

**默认计划（default_plan）**:
```python
[
    {
        "tool": "get_weather_data",
        "purpose": "获取ERA5历史气象数据",
        "priority": "high"
    },
    {
        "tool": "get_weather_forecast",
        "purpose": "获取未来1-16天天气预报（包含边界层高度预报，用于污染趋势预测和改善时机判断）",
        "priority": "high"
    },
    {
        "tool": "meteorological_trajectory_analysis",
        "purpose": "后向轨迹分析（快速溯源默认流程）",
        "depends_on": [0],  # 依赖 get_weather_data
        "priority": "high"
    },
    {
        "tool": "analyze_upwind_enterprises",
        "purpose": "上风向企业分析（快速溯源默认流程）",
        "depends_on": [0, 2],  # 依赖 get_weather_data 和 trajectory_analysis
        "priority": "high"
    }
]
```

**工具依赖关系**:
```
get_weather_data (0)
    ├── meteorological_trajectory_analysis (2)
    │     └── analyze_upwind_enterprises (3)
    └── analyze_upwind_enterprises (3)

get_weather_forecast (1)  # 独立执行
```

**文件位置**: `app/agent/core/expert_plan_generator.py`

---

### 阶段 2: 工具执行

#### 2.1 获取 ERA5 历史气象数据

**工具**: `get_weather_data`

**功能**:
- 获取指定时间范围的历史气象数据
- 数据来源: ERA5 再分析数据（0.25° 网格）
- 时间范围: 用户查询时间段

**输入参数**（LLM 自动生成）:
```python
{
    "lat": 23.1291,
    "lon": 113.2644,
    "location_name": "广州",
    "start_time": "2026-02-01 00:00:00",
    "end_time": "2026-02-01 23:59:59",
    "time_granularity": "hourly"
}
```

**输出（UDF v2.0 格式）**:
```json
{
  "status": "success",
  "success": true,
  "data": [
    {
      "timestamp": "2026-02-01 00:00:00",
      "lat": 23.1291,
      "lon": 113.2644,
      "station_name": "广州",
      "measurements": {
        "temperature": 15.2,
        "humidity": 75.0,
        "wind_speed": 3.5,
        "wind_direction": 180.0,
        "surface_pressure": 1013.2,
        "precipitation": 0.0,
        "cloud_cover": 60.0,
        "boundary_layer_height": 450.0
      }
    }
  ],
  "metadata": {
    "data_id": "weather_data_xxx",
    "data_type": "weather",
    "schema_version": "v2.0",
    "record_count": 24,
    "field_mapping_applied": true
  }
}
```

**关键气象要素**:
- 温度 (`temperature`)
- 湿度 (`humidity`)
- 风速/风向 (`wind_speed`, `wind_direction`)
- 边界层高度 (`boundary_layer_height`)
- 气压 (`surface_pressure`)
- 降水 (`precipitation`)
- 云量 (`cloud_cover`)

**文件位置**: `app/tools/query/get_weather_data/tool.py`

---

#### 2.2 获取天气预报数据

**工具**: `get_weather_forecast`

**功能**:
- 获取未来 1-16 天天气预报
- 实时调用 Open-Meteo Forecast API
- 包含边界层高度预报（关键！）

**输入参数**（LLM 自动生成）:
```python
{
    "lat": 23.1291,
    "lon": 113.2644,
    "location_name": "广州",
    "forecast_days": 7,
    "hourly": true,
    "daily": true
}
```

**输出（UDF v2.0 格式）**:
```json
{
  "status": "DataStatus.SUCCESS",
  "success": true,
  "data": [
    {
      "timestamp": "2026-02-02 00:00:00",
      "lat": 23.1291,
      "lon": 113.2644,
      "station_name": "广州",
      "measurements": {
        "temperature": 9.8,
        "boundary_layer_height": 390.0,
        "wind_speed": 8.7,
        "precipitation_probability": 0
      }
    }
  ],
  "metadata": {
    "data_id": "weather_forecast_xxx",
    "data_type": "DataType.WEATHER",
    "schema_version": "v2.0",
    "record_count": 168,
    "parameters": {
      "forecast_days": 7,
      "hourly": true,
      "daily": true
    }
  },
  "summary": "天气预报查询成功（广州）。未来7天预报，温度范围7.8~25.3°C。包含边界层高度预报数据，可用于污染扩散条件分析。"
}
```

**预报关键数据**:
- 未来 7-16 天温度、风速、湿度变化
- **边界层高度预报**（判断扩散条件改善时机）
- 降水概率和预报
- 风向变化趋势

**文件位置**: `app/tools/query/get_weather_forecast/tool.py`

---

#### 2.3 后向轨迹分析

**工具**: `meteorological_trajectory_analysis`

**功能**:
- 计算 72 小时后向气流轨迹
- 识别污染传输路径和潜在源区
- 基于 NOAA HYSPLIT 模型

**输入参数**（LLM 自动生成）:
```python
{
    "lat": 23.1291,
    "lon": 113.2644,
    "start_time": "2026-02-01 12:00:00",
    "hours": 72,  # 后向 72 小时
    "heights": [100, 500, 1000],  # 3 个高度层
    "direction": "Backward"
}
```

**输出**:
```json
{
  "status": "success",
  "success": true,
  "data": {
    "endpoints": [
      {
        "time": "2026-02-01 12:00:00",
        "lat": 23.1291,
        "lon": 113.2644,
        "height": 100
      },
      {
        "time": "2026-01-31 12:00:00",
        "lat": 22.8,
        "lon": 112.5,
        "height": 150
      }
    ]
  },
  "visuals": [
    {
      "id": "trajectory_map",
      "type": "map",
      "payload": {
        "map_url": "https://gaode.com/..."
      }
    }
  ],
  "summary": "后向轨迹分析显示主要传输通道为西南方向..."
}
```

**分析内容**:
- 轨迹聚类和主要传输方向
- 潜在源区识别（PSCF/CWT 方法）
- 不同高度层传输差异
- 传输强度和距离

**文件位置**: `app/tools/analysis/meteorological_trajectory_analysis/tool.py`

---

#### 2.4 上风向企业分析

**工具**: `analyze_upwind_enterprises`

**功能**:
- 基于轨迹方向识别上风向企业
- 实时风向扇区匹配（< 5 秒）
- 企业距离分级（5km/20km/50km）

**输入参数**（LLM 自动生成）:
```python
{
    "lat": 23.1291,
    "lon": 113.2644,
    "wind_direction": 180,  # 主导风向（南风）
    "radius_km": 50,
    "include_grading": true  # 包含距离分级
}
```

**输出**:
```json
{
  "status": "success",
  "success": true,
  "data": {
    "total_enterprises": 25,
    "by_distance": {
      "5km": 3,
      "20km": 12,
      "50km": 10
    },
    "top_enterprises": [
      {
        "name": "XX石化公司",
        "distance": 8.5,
        "direction": "南",
        "industry": "石化"
      }
    ]
  },
  "visuals": [
    {
      "id": "enterprises_map",
      "type": "map",
      "payload": {
        "map_url": "https://gaode.com/..."
      }
    }
  ],
  "summary": "上风向企业分析：南风方向识别到 25 家企业..."
}
```

**企业分级管控**:
| 距离范围 | 管控等级 | 主要措施 |
|---------|---------|---------|
| 5km 核心区 | A 级 | 停产限产、实时监控 |
| 20km 重点区 | B 级 | 错峰生产、强化监管 |
| 50km 影响区 | C 级 | 定期巡查、跟踪监测 |

**文件位置**: `app/tools/analysis/analyze_upwind_enterprises/tool.py`

---

### 阶段 3: 统计信息提取

WeatherExecutor 从工具结果中提取关键统计信息：

```python
stats = {
    # 数据可用性
    "has_weather_data": True,
    "has_forecast_data": True,
    "has_trajectory": True,
    "has_fire_hotspots": False,
    "has_dust_data": False,
    "has_satellite_data": False,

    # 历史数据统计
    "weather_record_count": 24,
    "avg_temperature": 10.6,
    "avg_wind_speed": 6.8,
    "avg_humidity": 64.0,
    "dominant_wind_direction": "NE",

    # 预报数据统计
    "forecast_days": 7,
    "forecast_info": "未来7天预报，温度范围8.0~25.4°C...",

    # 轨迹分析
    "trajectory_info": "后向轨迹分析显示主要传输通道为西南方向...",

    # 可视化
    "has_charts": False,
    "has_maps": True,
    "chart_types": ["trajectory", "map"],
    "visualization_count": 2,

    # 数据质量
    "data_completeness": 0.5,  # 3/6 = 0.5
    "analysis_confidence": 0.4
}
```

**数据完整性计算**:
```python
total_possible = 6  # weather_data, forecast_data, trajectory, fire, dust, satellite
actual_has = sum([has_weather_data, has_forecast_data, has_trajectory, ...])
data_completeness = actual_has / total_possible
```

---

### 阶段 4: 生成气象分析报告

WeatherExecutor 调用 LLM 生成结构化的气象分析报告。

**LLM 提示词结构**:

1. **角色定义**: 资深大气环境气象分析专家
2. **核心职责**:
   - 污染传输路径和上风向企业识别
   - 大气扩散条件对污染形成的影响
   - 轨迹分析定位污染来源区域
   - 气象条件预测污染发展趋势

3. **输入数据**:
   - 任务目标
   - 执行统计
   - 数据摘要（JSON 格式）
   - 图表信息（地图可视化）

4. **输出要求（Markdown 格式）**:
   ```
   [WEATHER_SECTION_START]
   ## 气象分析

   ### 总体分析
   [2-3段总体分析，150-200字，通俗易懂]

   ### 图表解析
   [非地图类图表的 Markdown 图片链接]

   ### 详细分析
   [详细分析内容，包含具体数据、时间点、数值等]

   [WEATHER_SECTION_END]
   ```

**报告章节结构**:

#### 1. 大气扩散能力诊断
- **边界层结构分析**: PBLH 日变化、逆温层、垂直扩散能力
- **风场特征**: 主导风向、风速廓线、风向稳定性
- **湍流状态**: Ri 数、L 长度、湍流强度评估
- **静稳天气**: 风速 < 2m/s 持续时间和影响

#### 2. 光化学污染气象条件
- **关键气象因子**: 温湿条件、光照条件、光化学年龄
- **定量分析**: 适合光化学反应的温度范围和时段

#### 3. 轨迹传输路径分析
- **轨迹聚类与源区识别**: 主要传输通道、方向、距离
- **定量指标**: 主要传输通道的方向和距离、高贡献源区

#### 4. 上风向企业污染源识别 ⭐ 重点
- **企业分布与影响评估**: 距离分级、行业特征、影响评估
- **企业分级管控建议**: A/B/C 级企业差异化措施

#### 5. 不利扩散条件识别
- **静稳天气分析**: 低混合层、静稳持续、高湿环境
- **触发条件**: 静稳天气的气象阈值和持续时间

#### 6. 天气系统与环流
- **大尺度环流特征**: 高压脊、低压槽、冷锋影响
- **环流演变**: 风向转向前后的污染积累效应

#### 7. 光化学污染气象条件
- **二次生成条件**: 温度范围、湿度效应、辐射条件

#### 8. 气象预报与污染潜势 ⭐ 新增
- **天气预报数据分析**: 预报数据完整性、边界层高度预报、风场预报
- **污染趋势预测**: 未来 24-48h 污染潜势、污染过程持续性
- **改善时机**: 有利气象的时间窗口（PBLH 升高、风速增大、降水过程）

#### 9. 控制建议与应对方案
- **分级管控措施**: 应急响应、企业管控、区域联防
- **执行优先级**: A 级企业 → B 级企业 → 传输通道管控

#### 10. 数据质量与置信度评估
- **质量评估**: 气象数据完整性、轨迹分析可靠性

---

## 数据流转

### 输入数据流

```
用户自然语言查询
    ↓
StructuredQueryParser (LLM 提取关键信息)
    ↓
StructuredQuery {
    location, lat, lon,
    start_time, end_time,
    pollutants
}
    ↓
ExpertPlanGenerator (生成工具计划)
    ↓
default_plan (4 个工具)
```

### 工具执行流

```
ToolDependencyGraph (依赖图调度)
    ↓
并行执行:
    - get_weather_data (0)
    - get_weather_forecast (1)
    ↓
依赖执行:
    - meteorological_trajectory_analysis (2) [依赖 0]
    - analyze_upwind_enterprises (3) [依赖 0, 2]
```

### 输出数据流

```
工具结果 (UDF v2.0 格式)
    ↓
WeatherExecutor._extract_summary_stats()
    ↓
统计信息 + 工具结果
    ↓
WeatherExecutor._generate_summary()
    ↓
气象分析报告 (Markdown)
```

---

## 输出标准

### 1. 工具输出标准（UDF v2.0）

所有工具必须返回符合 UDF v2.0 规范的格式：

```json
{
  "status": "success|failed|partial|empty",
  "success": true|false,
  "data": [...],  // UnifiedDataRecord 列表
  "metadata": {
    "data_id": "...",
    "data_type": "weather|forecast|...",
    "schema_version": "v2.0",
    "field_mapping_applied": true,
    "field_mapping_info": {...}
  },
  "summary": "...",
  "visuals": [...]  // 可选，可视化块
}
```

### 2. 专家输出标准

**ExpertResult 结构**:

```python
{
    "status": "success|partial|failed",
    "expert_type": "weather",
    "task_id": "weather_xxx",
    "tool_results": [...],  # 工具执行结果列表
    "analysis": "...",  # 气象分析报告（Markdown）
    "execution_summary": {
        "tools_executed": 4,
        "tools_succeeded": 4,
        "tools_failed": 0,
        "errors": []
    },
    "visuals": [...],  # 聚合的可视化
    "data_ids": [...],  # 生成的 data_id 列表
    "skip_viz_data_ids": [...]  # 跳过可视化的 data_id
}
```

---

## 性能指标

### 工具执行时间

| 工具 | 平均耗时 | 超时设置 |
|------|---------|---------|
| get_weather_data | 2-5 秒 | 30 秒 |
| get_weather_forecast | 2-4 秒 | 30 秒 |
| meteorological_trajectory_analysis | 60-120 秒 | 180 秒 |
| analyze_upwind_enterprises | < 5 秒 | 30 秒 |

### 总体性能

- **快速溯源总耗时**: 1-2 分钟（主要是轨迹分析）
- **数据完整性**: 50% (3/6 数据源)
- **分析置信度**: 0.4-0.8

---

## 错误处理

### 工具执行失败

**降级策略**:
1. 单个工具失败不影响其他工具
2. 轨迹分析失败时，上风向企业分析无法执行（依赖关系）
3. 预报数据失败时，报告基于历史数据生成

**错误日志**:
```python
{
    "tool": "meteorological_trajectory_analysis",
    "status": "error",
    "error": "NOAA HYSPLIT model did not complete within timeout..."
}
```

### 数据质量评估

**数据完整性阈值**:
- `completeness >= 0.6`: 高置信度分析
- `0.3 <= completeness < 0.6`: 中等置信度，需要数据质量警告
- `completeness < 0.3`: 低置信度，建议补充数据

---

## 后续优化方向

### 1. 工具优化
- **轨迹分析超时**: 增加重试机制或使用替代模型
- **预报数据增强**: 添加更多预报要素（如能见度、UV 指数）

### 2. 数据质量
- **数据完整性提升**: 集成火点、沙尘、卫星数据
- **实时数据**: 接入更多实时气象站数据

### 3. 分析能力
- **机器学习**: 污染过程自动识别和预测
- **历史对比**: 与历史同期气象条件对比

---

## 相关文件

### 核心代码

| 文件 | 说明 |
|------|------|
| `app/agent/experts/expert_router_v3.py` | 专家路由器（调度） |
| `app/agent/experts/weather_executor.py` | 气象专家执行器 |
| `app/agent/core/expert_plan_generator.py` | 计划生成器 |
| `app/tools/query/get_weather_data/tool.py` | ERA5 历史数据工具 |
| `app/tools/query/get_weather_forecast/tool.py` | 天气预报工具（UDF v2.0） |
| `app/tools/analysis/meteorological_trajectory_analysis/tool.py` | 轨迹分析工具 |
| `app/tools/analysis/analyze_upwind_enterprises/tool.py` | 上风向企业分析工具 |

### 数据模型

| 文件 | 说明 |
|------|------|
| `app/schemas/unified.py` | UDF v2.0 统一数据格式 |
| `app/agent/experts/expert_executor.py` | ExpertExecutor 基类 |

### 外部 API

| 文件 | 说明 |
|------|------|
| `app/external_apis/openmeteo_client.py` | Open-Meteo API 客户端 |
| `app/external_apis/noaa_hysplit_api.py` | NOAA HYSPLIT API 客户端 |

---

## 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v1.0 | 2026-02-02 | 初始版本，包含默认计划和预报工具 |

---

## 附录

### A. 气象要素标准字段名

| 标准字段 | 原始 API 字段 | 单位 | 说明 |
|---------|--------------|------|------|
| temperature | temperature_2m | °C | 2米气温 |
| humidity | relative_humidity_2m | % | 2米相对湿度 |
| wind_speed | wind_speed_10m | km/h | 10米风速 |
| wind_direction | wind_direction_10m | degrees | 10米风向 |
| surface_pressure | surface_pressure | hPa | 地面气压 |
| precipitation | precipitation | mm | 降水量 |
| cloud_cover | cloud_cover | % | 总云量 |
| boundary_layer_height | boundary_layer_height | m | 边界层高度 |

### B. LLM 提示词关键部分

参见 `app/agent/experts/weather_executor.py` 中的 `_get_summary_prompt()` 方法。

---

**文档结束**
