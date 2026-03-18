# 颗粒物组分专家工作流程文档

**版本**: v1.0
**日期**: 2026-02-03
**专家类型**: ComponentExecutor (组分分析专家)

---

## 1. 专家概述

### 1.1 专家职责

ComponentExecutor（组分分析专家）负责污染物组分特征分析和源解析，是多专家系统中的核心分析专家。

**核心能力**:
- 空气质量数据查询与区域对比分析
- VOCs（挥发性有机化合物）组分分析
- PM2.5/PM10颗粒物组分分析（水溶性离子、碳组分、地壳元素、微量元素）
- PMF源解析（颗粒物源解析、VOCs源解析）
- OBM/OFP臭氧生成潜势分析
- 智能图表生成

**适用场景**:
- PM2.5/PM10颗粒物污染溯源
- 臭氧（O3）污染溯源
- VOCs前体物分析
- 污染源贡献率量化
- 区域传输vs本地生成诊断

---

## 2. 工具加载架构

### 2.1 工具分类

ComponentExecutor加载38个工具，按优先级分为7大类：

#### 2.1.1 区域对比查询工具（核心）
**优先级**: 最高

| 工具名称 | 数据源 | 查询方式 | 优先级 | 用途 |
|---------|--------|---------|--------|------|
| `get_jining_regular_stations` | 端口9096 | 自然语言 `question` | 1 (最高) | 济宁市区域对比 |
| `get_guangdong_regular_stations` | 端口9091 | 自然语言 `question` | 2 (次高) | 广东省区域对比 |
| `get_air_quality` | 全国API | 自然语言 `question` | 3 (备用) | 全国其他地区 |

**参数格式**:
```python
{
    "question": "查询广州市、深圳市、佛山市2026-02-01至2026-02-03的PM2.5小时数据"
}
```

**返回数据**: UDF v2.0格式（PM2.5、PM10、O3、NO2、SO2、CO、AQI）

#### 2.1.2 VOCs组分数据工具
| 工具名称 | 数据源 | 用途 |
|---------|--------|------|
| `get_vocs_data` | 端口9092 | VOCs组分查询（苯系物、烷烃、烯烃等） |

**返回组分**: 乙烷、丙烷、苯、甲苯、二甲苯、甲醛等具体物种浓度

#### 2.1.3 颗粒物组分数据工具（5个独立工具）

**设计理念**: 按组分类型分离查询，避免单次查询数据过大

| 工具名称 | 查询组分 | 用途 |
|---------|---------|------|
| `get_pm25_ionic` | F⁻、Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺ | 水溶性离子分析、二次气溶胶研究 |
| `get_pm25_carbon` | OC（有机碳）、EC（元素碳） | 碳组分分析、一次/二次有机碳 |
| `get_pm25_crustal` | Al、Si、Fe、Ca、Ti、Mn等 | 地壳元素分析、扬尘源识别 |
| `get_particulate_components` | Cl⁻、NO₃⁻、SO₄²⁻、NH₄⁺、OC、EC等 | PMF源解析（综合组分） |
| `get_pm25_component` | 32个因子完整组分 | PM2.5完整组分分析 |

**参数格式** (支持自动位置映射):
```python
{
    "locations": ["深圳"],  # 推荐：自动映射站点编码
    "start_time": "2026-01-31 00:00:00",
    "end_time": "2026-01-31 23:59:59",
    "time_granularity": 1  # 1=小时, 2=日, 3=月
}
```

#### 2.1.4 源解析工具
| 工具名称 | 分析对象 | 算法 | 用途 |
|---------|---------|------|------|
| `calculate_pm_pmf` | PM2.5/PM10 | PMF (NNLS+NIMFA双模式) | 颗粒物源解析 |
| `calculate_vocs_pmf` | VOCs | PMF | VOCs前体物源解析 |

**PMF输出源类型**:
- 颗粒物: 机动车尾气、工业排放、燃煤源、扬尘、生物质燃烧、二次硫酸盐、二次硝酸盐
- VOCs: 机动车尾气、石油化工、溶剂使用、燃烧源、工业过程、生物源

#### 2.1.5 光化学分析工具
| 工具名称 | 用途 | 计算内容 |
|---------|------|---------|
| `calculate_obm_full_chemistry` | 臭氧生成潜势分析 | EKMA曲面、RIR敏感性、PO3、RACM2化学机理 |

**输出内容**:
- VOCs控制型 vs NOx控制型诊断
- 臭氧生成潜势（OFP）排序
- 减排路径建议

#### 2.1.6 颗粒物组分分析工具（5个）
| 工具名称 | 分析内容 | 输出图表 |
|---------|---------|---------|
| `calculate_reconstruction` | 7大组分重构 | OM、NO3、SO4、NH4、EC、地壳、微量 |
| `calculate_soluble` | 水溶性离子分析 | 三元图、SOR/NOR、离子平衡 |
| `calculate_carbon` | 碳组分分析 | POC/SOC、EC/OC比值 |
| `calculate_crustal` | 地壳元素分析 | 氧化物转换、箱线图 |
| `calculate_trace` | 微量元素分析 | 富集因子、Taylor丰度 |

#### 2.1.7 可视化工具
| 工具名称 | 功能 | 支持图表类型 |
|---------|------|------------|
| `smart_chart_generator` | 智能图表生成 | 15种图表类型（时序图、饼图、柱图、玫瑰图、3D图、地图等） |
| `generate_chart` | 通用图表生成 | Chart v3.1格式 |

---

## 3. 工作流程详解

### 3.1 PM2.5/PM10颗粒物溯源流程

**触发条件**: `pollutants` 包含 `["PM2.5", "PM10", "颗粒物"]`

**执行计划**: `pm_tracing_plan`

#### 步骤1: 区域传输分析
**目的**: 判断本地生成 vs 区域传输

**工具选择**:
- 城市级查询: `get_guangdong_regular_stations` (param_template: `regional_city_comparison`)
- 站点级查询: `get_guangdong_regular_stations` (param_template: `regional_nearby_stations`)

**查询内容**:
```python
# 城市级示例
{
    "question": "查询广州市、深圳市、佛山市、东莞市2026-02-01 00:00:00至2026-02-03 23:59:59的PM2.5和PM10小时数据"
}

# 站点级示例（station_code不为空时）
{
    "question": "查询东城站及周边城市（深圳市、东莞市、惠州市）2026-02-01至2026-02-03的PM2.5和PM10小时数据"
}
```

**分析维度**:
- 时间滞后相关性: 周边先升高 → 区域传输；目标先升高 → 本地生成
- 峰值时间对比
- 浓度梯度分析

#### 步骤2: 气象数据获取
**工具**: `get_weather_data`

**目的**: 气象-污染协同分析

**查询参数**:
```python
{
    "data_type": "era5",
    "lat": 23.13,
    "lon": 113.26,
    "start_time": "2026-02-01",
    "end_time": "2026-02-03"
}
```

**返回数据**: 温度、湿度、风速、风向、边界层高度

#### 步骤3: 颗粒物组分数据获取（5个并行查询）

**3.1 水溶性离子** (`get_pm25_ionic`)
```python
{
    "locations": ["广州"],
    "start_time": "2026-01-31 00:00:00",
    "end_time": "2026-01-31 23:59:59",
    "time_granularity": 1  # 小时粒度
}
```
**返回**: SO4²⁻、NO3⁻、NH4⁺、Cl⁻、Ca²⁺、Mg²⁺、K⁺、Na⁺、F⁻

**3.2 碳组分** (`get_pm25_carbon`)
```python
{
    "locations": ["广州"],
    "start_time": "2026-01-31 00:00:00",
    "end_time": "2026-01-31 23:59:59",
    "time_granularity": 1
}
```
**返回**: OC（有机碳）、EC（元素碳）

**3.3 地壳元素** (`get_pm25_crustal`)
```python
{
    "locations": ["广州"],
    "start_time": "2026-01-31 00:00:00",
    "end_time": "2026-01-31 23:59:59",
    "time_granularity": 1
}
```
**返回**: Al、Si、Fe、Ca、Mg、K、Na、Ti

**3.4 微量元素** (`get_pm25_crustal` with elements filter)
```python
{
    "locations": ["广州"],
    "start_time": "2026-01-31 00:00:00",
    "end_time": "2026-01-31 23:59:59",
    "elements": ["Zn", "Pb", "Cu", "Ni", "Cr", "Mn", "Cd", "As", "Se"]
}
```
**返回**: 重金属和微量元素浓度

**3.5 常规污染物** (`get_guangdong_regular_stations`)
**目的**: 获取SO2、NO2用于SOR/NOR计算

**关键设计**: 使用 `skip_viz=true` 标记，此数据仅用于计算，不生成图表

#### 步骤4: 组分分析（6个分析工具）

**4.1 7大组分重构** (`calculate_reconstruction`)
**依赖**: 全部4种组分数据

**输入绑定**:
```python
{
    "data_id": "get_pm25_ionic[role=water-soluble].data_id",
    "data_id_carbon": "get_pm25_carbon[role=carbon].data_id",
    "data_id_crustal": "get_pm25_crustal[role=crustal].data_id",
    "data_id_trace": "get_pm25_crustal[role=trace].data_id"
}
```

**输出**:
- OM (有机物): OC × 1.4
- NO3⁻ (硝酸盐)
- SO4²⁻ (硫酸盐)
- NH4⁺ (铵盐)
- EC (元素碳)
- 地壳物质 (氧化物总和)
- 微量元素 (重金属总和)
- 重构闭合度: 重构总和 / 实测PM2.5 × 100%

**4.2 水溶性离子分析** (`calculate_soluble`)
**依赖**: 水溶性离子数据 + 气体数据（SO2/NO2）

**输入绑定**:
```python
{
    "data_id": "get_pm25_ionic[role=water-soluble].data_id",
    "gas_data_id": "get_guangdong_regular_stations[FIRST].data_id",
    "analysis_type": "full"
}
```

**输出**:
- 三元图 (S-N-A组成)
- SOR (硫酸盐生成率): SOR > 0.8表示二次生成主导
- NOR (硝酸盐生成率): NOR > 0.5表示二次生成主导
- 阴阳离子平衡
- 离子浓度时序变化

**4.3 碳组分分析** (`calculate_carbon`)
**依赖**: 碳组分数据

**输入绑定**:
```python
{
    "data_id": "get_pm25_carbon[role=carbon].data_id",
    "carbon_type": "pm25",
    "oc_to_om": 1.4,
    "poc_method": "ec_normalization"
}
```

**输出**:
- POC (一次有机碳)
- SOC (二次有机碳)
- EC/OC比值: >2 表明存在二次有机碳
- 碳组分时序变化

**4.4 地壳元素分析** (`calculate_crustal`)
**依赖**: 地壳元素数据

**输出**:
- 氧化物转换 (元素 → 氧化物)
- 地壳物质总量
- 箱线图 (各元素浓度分布)
- 扬尘源识别

**4.5 微量元素分析** (`calculate_trace`)
**依赖**: 微量元素数据

**输出**:
- 铝归一化 (元素/Al比值)
- Taylor丰度对比 (地壳vs样品)
- 富集因子 (EF): EF>10表示人为源
- 人为源识别 (工业排放、燃煤、交通)

**4.6 PMF源解析** (`calculate_pm_pmf`)
**依赖**: 水溶性离子 + 碳组分

**输入绑定**:
```python
{
    "data_id": "get_pm25_ionic[role=water-soluble].data_id",
    "gas_data_id": "get_pm25_carbon[role=carbon].data_id",
    "pollutant_type": "PM2.5"
}
```

**输出**:
- 源因子识别: 机动车、工业、燃煤、扬尘、生物质燃烧、二次硫酸盐、二次硝酸盐
- 贡献率量化: 各源类的浓度分担率 (%)
- 源谱特征: 典型污染源的化学指纹
- 双模式结果: NNLS vs NIMFA对比

#### 步骤5: 智能图表生成
**工具**: `smart_chart_generator`

**触发条件**: 所有分析工具执行完毕

**输入**: 所有上游工具的 `data_id` 列表

**输出图表类型**:
- 时序图: PM2.5浓度时序、组分时序
- 饼图: PMF源贡献比例、7大组分占比
- 柱图: 不同源类贡献对比
- 三元图: S-N-A水溶性离子组成
- 散点图: SOR/NOR关系、EC/OC关系
- 箱线图: 地壳元素浓度分布

---

### 3.2 臭氧（O3）溯源流程

**触发条件**: `pollutants` 包含 `["O3", "臭氧", "VOCs"]`

**执行计划**: `ozone_tracing_plan`

#### 步骤1: 区域传输分析
**同PM2.5流程**，但查询污染物为 O3

#### 步骤2: 常规污染物数据获取
**工具**: `get_guangdong_regular_stations`

**查询内容**: O3、NOx、NO2、PM2.5、AQI小时数据

**目的**:
- 判断O3峰值时间
- 分析NO2与O3的时序关系
- 评估NOx滴定效应

#### 步骤3: VOCs组分数据获取
**工具**: `get_vocs_data`

**查询参数**:
```python
{
    "question": "查询广州市2026-02-01至2026-02-03的VOCs挥发性有机化合物组分数据，包括苯、甲苯、二甲苯、乙烷、丙烷、甲醛等具体物种浓度"
}
```

**返回组分** (102种):
- 烷烃: C2-C12烷烃
- 烯烃: 乙烯、丙烯等
- 芳香烃: 苯、甲苯、二甲苯等
- 含氧VOCs: 甲醛、乙醛等
- 炔烃: 乙炔

#### 步骤4: PMF源解析（VOCs专用）
**工具**: `calculate_vocs_pmf`

**输入绑定**:
```python
{
    "data_id": "get_vocs_data[FIRST].data_id"
}
```

**输出**:
- 源因子识别: 机动车尾气、石油化工、溶剂使用、燃烧源、工业过程、生物源
- VOCs贡献率: 各源类对总VOCs和活性VOCs的贡献
- 源谱特征: 典型源的VOCs"指纹"

#### 步骤5: OBM光化学分析
**工具**: `calculate_obm_full_chemistry`

**输入绑定**:
```python
{
    "vocs_data_id": "get_vocs_data[FIRST].data_id",
    "nox_data_id": "get_guangdong_regular_stations[FIRST].data_id",
    "mode": "all"  # EKMA + RIR + PO3
}
```

**输出**:
- EKMA曲面图: O3-VOCs-NOx敏感性分析
- 敏感性诊断: VOCs-limited / NOx-limited / Transitional
- RIR排序: 各VOCs物种对O3生成的相对反应性
- OFP排序: 臭氧生成潜势最高的10个VOCs物种
- 减排路径建议: 基于敏感性分析的控制策略

**EKMA诊断逻辑**:
```
VOCs-limited区域: 削减VOCs有效降低O3
NOx-limited区域: 削减NOx可能导致O3升高（NO滴定效应）
Transitional区域: VOCs和NOx协同减排
```

#### 步骤6: 智能图表生成
**图表类型**:
- 时序图: O3浓度日变化、VOCs时序
- 饼图: PMF源贡献比例
- 柱图: OFP排序（Top 10活性物种）
- 3D曲面图: EKMA敏感性曲面
- 散点图: VOCs/NOx比值与O3浓度关系

---

## 4. 数据流转架构

### 4.1 工具依赖图

```
PM2.5溯源流程:
┌─────────────────────────────────────────────────────────────┐
│ 1. 区域传输分析 (get_guangdong_regular_stations)              │
│    → data_id: air_quality_unified:v1:xxx                     │
├─────────────────────────────────────────────────────────────┤
│ 2. 气象数据 (get_weather_data)                               │
│    → data_id: weather:v1:yyy                                 │
├─────────────────────────────────────────────────────────────┤
│ 3. 组分数据查询 (并行)                                        │
│    ├─ get_pm25_ionic [role=water-soluble]                   │
│    │   → data_id: particulate_unified:v1:aaa                │
│    ├─ get_pm25_carbon [role=carbon]                         │
│    │   → data_id: particulate_unified:v1:bbb                │
│    ├─ get_pm25_crustal [role=crustal]                       │
│    │   → data_id: particulate_unified:v1:ccc                │
│    └─ get_pm25_crustal [role=trace] (elements filter)       │
│        → data_id: particulate_unified:v1:ddd                │
├─────────────────────────────────────────────────────────────┤
│ 4. 常规污染物 (skip_viz=true, 仅用于计算)                     │
│    get_guangdong_regular_stations                            │
│    → data_id: air_quality_unified:v1:eee                    │
├─────────────────────────────────────────────────────────────┤
│ 5. 组分分析工具 (depends_on: 3.x)                            │
│    ├─ calculate_reconstruction (依赖: 3.1+3.2+3.3+3.4)      │
│    │   → data_id: reconstruction_result:v1:fff              │
│    ├─ calculate_soluble (依赖: 3.1+4)                       │
│    │   → data_id: soluble_result:v1:ggg                     │
│    ├─ calculate_carbon (依赖: 3.2)                          │
│    │   → data_id: carbon_result:v1:hhh                      │
│    ├─ calculate_crustal (依赖: 3.3)                         │
│    │   → data_id: crustal_result:v1:iii                     │
│    ├─ calculate_trace (依赖: 3.4)                           │
│    │   → data_id: trace_result:v1:jjj                       │
│    └─ calculate_pm_pmf (依赖: 3.1+3.2)                      │
│        → data_id: pmf_result:v1:kkk                         │
├─────────────────────────────────────────────────────────────┤
│ 6. 智能图表生成 (depends_on: 1+2+5.x)                        │
│    smart_chart_generator                                     │
│    → visuals: [{chart1}, {chart2}, ...]                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Input Bindings机制

**定义位置**: `app/agent/context/tool_dependencies.py`

**作用**: 自动解析工具间的数据依赖关系

**示例1: 7大组分重构**
```python
"calculate_reconstruction": {
    "input_bindings": {
        "data_id": "get_pm25_ionic[role=water-soluble].data_id",
        "data_id_carbon": "get_pm25_carbon[role=carbon].data_id",
        "data_id_crustal": "get_pm25_crustal[role=crustal].data_id",
        "data_id_trace": "get_pm25_crustal[role=trace].data_id"
    }
}
```

**解析逻辑**:
1. `[role=water-soluble]` - 角色匹配模式，匹配带有 `role="water-soluble"` 的工具调用
2. `.data_id` - 提取该工具返回的 data_id
3. 自动绑定到目标工具的 `data_id` 参数

**示例2: 水溶性离子分析**
```python
"calculate_soluble": {
    "input_bindings": {
        "data_id": "get_pm25_ionic[role=water-soluble].data_id",
        "gas_data_id": "get_guangdong_regular_stations[FIRST].data_id"
    }
}
```

**[FIRST] 模式**: 匹配第一个成功的工具调用（用于多次调用同一工具的场景）

### 4.3 Skip Viz机制

**目的**: 某些数据仅用于计算，不需要生成图表（如近30天空气质量数据用于SOR/NOR计算）

**触发条件**:
- 工具: `get_guangdong_regular_stations`
- 参数模板: `auto` (非区域对比)
- 时间范围: >= 25天

**标记方式**:
```python
tool_plan = ToolCallPlan(
    tool="get_guangdong_regular_stations",
    params={...},
    skip_viz=True  # 标记跳过可视化
)
```

**效果**:
- 该工具的 `data_id` 不会传递给 `smart_chart_generator`
- VizExecutor 不会为该数据生成图表
- 减少无意义的图表生成，提高效率

---

## 5. 分析总结生成

### 5.1 分析类型识别

**方法**: `_get_analysis_type_from_results()`

**判断逻辑**:
```python
# 从原始查询的 pollutants 判断
pollutants = context.get("pollutants", [])

# O3相关 → "ozone"
ozone_related = ["O3", "臭氧", "VOCs", "VOC", "NOx", "NO2"]

# PM相关 → "pm"
pm_related = ["PM2.5", "PM10", "颗粒物", "PM"]

if any(p in pollutants for p in ozone_related):
    return "ozone"
elif any(p in pollutants for p in pm_related):
    return "pm"
else:
    return "general"
```

### 5.2 分析提示词选择

**提示词映射**:
- `pm` → `PM_SUMMARY_PROMPT` (颗粒物溯源专用提示词)
- `ozone` → `OZONE_SUMMARY_PROMPT` (臭氧溯源专用提示词)
- `general` → `GENERAL_SUMMARY_PROMPT` (通用分析提示词)

### 5.3 PM2.5分析提示词结构

**文件位置**: `component_executor.py` 第670-814行

**提示词章节**:

1. **核心职责**
   - 颗粒物化学组分特征和二次生成过程
   - PMF源解析和主要贡献源识别
   - 7大组分重构分析
   - 颗粒物化学转化机制和来源解析

2. **分析框架**
   - 区域时序对比分析（本地生成 vs 区域传输）
   - 颗粒物组分诊断（离子、碳、地壳、微量元素）
   - PMF源解析深度分析
   - 7大组分重构分析
   - 二次颗粒物生成评估
   - 源贡献季节性变化

3. **颗粒物数据查询工具说明**
   - 4个独立查询工具的使用方法
   - 参数说明（locations推荐使用）
   - PMF源解析建议

4. **专业输出格式**
   - 总体评估
   - 关键发现（必须包含）
   - 机制解释
   - 控制建议

5. **专业术语库**
   - SOR、NOR、OC/EC、7大组分、PMF等

**关键要求**:
- 定量分析: 提供浓度、比率、贡献率等具体数值
- 化学机制: 详细描述反应路径和动力学过程
- 溯源判断: 基于化学指纹的污染源识别
- 控制策略: 科学的前体物减排建议

### 5.4 O3分析提示词结构

**文件位置**: `component_executor.py` 第816-918行

**提示词章节**:

1. **核心职责**
   - VOCs化学组分特征和臭氧生成潜势（OFP）
   - OBM敏感性分析：VOCs控制型 vs NOx控制型
   - PMF源解析：VOCs前体物的来源识别
   - 光化学年龄和臭氧生成效率（OPE）

2. **分析框架**
   - 区域时序对比分析（本地生成 vs 区域传输）
   - VOCs组分诊断（烷烃、烯烃、芳香烃）
   - PMF源解析深度分析
   - OBM/OFP臭氧生成潜势分析
   - O3-NOx-VOCs敏感性分析
   - 光化学进程分析

3. **专业输出格式**
   - 总体评估（控制型判定）
   - 关键发现（OFP Top 5、敏感性类型）
   - 机制解释（反应活性、自由基化学）
   - 控制建议（VOCs/NOx减排策略）

4. **专业术语库**
   - MIR、OFP、OPE、RIR、EKMA、P(Ox)、L(VOC)

**关键输出**:
- VOCs控制型/NOx控制型/过渡型诊断
- 臭氧生成潜势最高的5个VOCs物种
- 光化学年龄评估
- 减排路径优化建议

---

## 6. 数据格式规范

### 6.1 UDF v2.0统一格式

**所有工具输出必须遵循UDF v2.0格式**:

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
        "generator": "tool_name",      # 生成工具名称
        "scenario": "scenario",        # 场景标识
        "record_count": 100,           # 记录数量
        "generator_version": "2.0.0"   # 工具版本
    },
    "summary": "...",                  # 摘要信息
    "visuals": [...]                   # 图表数据（可选）
}
```

### 6.2 图表数据格式（Chart v3.1）

**多图表场景**:
```python
{
    "status": "success",
    "success": true,
    "data": null,                      # v2.0不使用data承载图表
    "visuals": [                       # ✅ 统一visuals字段
        {
            "id": "visual_001",
            "type": "chart|map|table",
            "schema": "chart_config",
            "payload": {
                "id": "chart_001",
                "type": "timeseries",
                "title": "PM2.5浓度时序变化",
                "data": {...},
                "meta": {
                    "schema_version": "3.1",
                    "generator": "tool_name",
                    "layout_hint": "wide"
                }
            },
            "meta": {
                "schema_version": "v2.0",
                "source_data_ids": ["..."],
                "generator": "tool_name"
            }
        }
    ],
    "metadata": {...}
}
```

### 6.3 字段映射系统

**文件**: `app/utils/data_standardizer.py`

**总映射数**: 260个字段

**类别覆盖**:
- 时间字段: 10个映射
- 站点字段: 15个映射
- 坐标字段: 8个映射
- 污染物字段: 80个映射
- AQI字段: 12个映射
- VOCs字段: 55个映射
- 颗粒物字段: 35个映射
- 气象字段: 45个映射

**示例**:
```python
# 原始字段 → 标准字段
"气温" → "temperature_2m"
"PM2.5" → "pm25"
"硫酸盐" → "sulfate"
"OC" → "organic_carbon"
```

---

## 7. 工具执行监控

### 7.1 日志追踪

**关键日志事件**:

```python
# 工具加载
logger.info("tool_loaded", tool="get_guangdong_regular_stations")

# 工具执行开始
logger.info("tool_execution_start", tool="calculate_pm_pmf", params={...})

# 工具执行成功
logger.info("tool_execution_success", tool="calculate_pm_pmf", data_id="pmf_result:v1:xxx")

# Input Bindings解析
logger.info("input_bindings_extracted", tool="calculate_soluble", bindings={...})

# Skip Viz标记
logger.info("tool_plan_skip_viz_set", tool="get_guangdong_regular_stations", reason="计算型数据")

# 统计信息提取
logger.info("component_analysis_type_detected", analysis_type="pm", pollutants=["PM2.5"])
```

### 7.2 性能指标

**关键指标**:
- 工具执行时长
- 数据记录数量
- 字段映射成功率
- 图表生成数量
- PMF源解析因子数

**监控方法**:
```python
# 工具结果统计
stats = {
    "has_air_quality": bool,      # 是否有空气质量数据
    "has_component": bool,        # 是否有组分数据
    "has_pmf": bool,              # 是否执行PMF
    "has_obm_ofp": bool,          # 是否执行OBM
    "record_count": int,          # 数据记录数
    "pmf_factors": int,           # PMF源因子数
    "top_sources": List[Tuple],   # PMF Top 3源类
    "main_source": str,           # 主要污染源
    "main_contribution": float    # 主要源贡献率
}
```

---

## 8. 常见问题与解决

### 8.1 工具加载失败

**问题**: 某个工具导入失败

**原因**:
- 工具依赖的Python包未安装
- 工具代码路径错误
- 工具类名错误

**解决**:
```python
# 查看日志
logger.warning("tool_import_failed", tool="calculate_pm_pmf", error=str(e))

# 检查依赖
pip install -r requirements.txt

# 检查工具路径
from app.tools.analysis.calculate_pm_pmf.tool import CalculatePMFTool
```

### 8.2 Input Bindings匹配失败

**问题**: 依赖工具的data_id无法传递到下游工具

**原因**:
- 角色标识 `role` 不匹配
- 上游工具未返回data_id
- Input Bindings配置错误

**解决**:
```python
# 检查日志
logger.warning("input_bindings_not_found", tool="calculate_reconstruction")

# 验证role标识
tool_plan = ToolCallPlan(
    tool="get_pm25_ionic",
    role="water-soluble"  # ✅ 必须与binding一致
)

# 验证data_id返回
result = {
    "data_id": "particulate_unified:v1:xxx"  # ✅ 必须返回
}
```

### 8.3 PMF执行失败

**问题**: PMF源解析无法执行

**原因**:
- 数据样本数不足（<20个样本）
- 组分数据缺失（离子或碳组分）
- 数据质量差（过多缺失值）

**解决**:
```python
# 增加时间范围，确保至少20个小时数据
{
    "start_time": "2026-01-31 00:00:00",
    "end_time": "2026-01-31 23:59:59",  # 24小时数据
    "time_granularity": 1  # 小时粒度
}

# 检查组分数据完整性
# PMF需要: SO4、NO3、NH4、OC、EC等核心组分
```

### 8.4 图表生成失败

**问题**: smart_chart_generator未生成图表

**原因**:
- 上游data_id被skip_viz过滤
- 数据格式不符合Chart v3.1
- 图表模板不存在

**解决**:
```python
# 检查skip_viz标记
logger.info("upstream_data_ids_filtered_by_skip_viz", filtered_count=3)

# 确保数据格式正确
{
    "data": [...],
    "metadata": {
        "schema_version": "v2.0",  # ✅ 必需
        "field_mapping_applied": true
    }
}
```

---

## 9. 最佳实践

### 9.1 颗粒物溯源最佳实践

1. **完整组分数据**
   - 必须获取: 水溶性离子 + 碳组分（PMF必需）
   - 推荐获取: 地壳元素 + 微量元素（7大组分重构）

2. **时间粒度选择**
   - PMF分析: 小时粒度（至少20个样本）
   - 组分分析: 小时粒度（精细化分析）
   - 长期趋势: 日粒度或月粒度

3. **区域对比策略**
   - 城市级: 查询目标城市 + 周边3-4个城市
   - 站点级: 查询目标站点 + 周边城市

4. **SOR/NOR计算**
   - 需要近30天空气质量数据（SO2/NO2）
   - 使用skip_viz=true避免生成无意义图表

### 9.2 臭氧溯源最佳实践

1. **VOCs数据获取**
   - 时间范围: 覆盖O3峰值时段（10:00-16:00）
   - 时间粒度: 小时粒度

2. **OBM分析**
   - 确保NOx数据完整（NO2、NO）
   - mode="all"获取完整分析（EKMA+RIR+PO3）

3. **PMF源解析**
   - VOCs样本数至少20个
   - 包含活性物种（烯烃、芳香烃）

4. **敏感性诊断**
   - 结合EKMA曲面和RIR排序
   - 考虑季节差异（夏季VOCs-limited，冬季NOx-limited）

### 9.3 数据质量控制

1. **数据完整性检查**
   - 缺失率 < 30%
   - 核心组分不能缺失（SO4、NO3、NH4、OC、EC）

2. **数据合理性检查**
   - 浓度范围: PM2.5 0-500 µg/m³, O3 0-400 µg/m³
   - 离子平衡: AE/CE比值 0.8-1.2
   - EC/OC比值: 0.1-1.0

3. **异常值处理**
   - 识别并标记异常值
   - PMF分析前进行数据清洗

---

## 10. 附录

### 10.1 工具完整列表

| 工具名称 | 类别 | 优先级 | 用途 |
|---------|------|--------|------|
| get_weather_data | 气象 | - | 气象数据查询 |
| get_jining_regular_stations | 查询 | 1 | 济宁市区域对比 |
| get_guangdong_regular_stations | 查询 | 2 | 广东省区域对比 |
| get_air_quality | 查询 | 3 | 全国空气质量 |
| get_vocs_data | 查询 | - | VOCs组分查询 |
| get_pm25_ionic | 查询 | - | 水溶性离子 |
| get_pm25_carbon | 查询 | - | 碳组分 |
| get_pm25_crustal | 查询 | - | 地壳元素 |
| get_particulate_components | 查询 | - | PM2.5综合组分 |
| get_pm25_component | 查询 | - | PM2.5完整组分(32因子) |
| calculate_pm_pmf | 分析 | - | PMF源解析(颗粒物) |
| calculate_vocs_pmf | 分析 | - | PMF源解析(VOCs) |
| calculate_obm_full_chemistry | 分析 | - | OBM臭氧分析 |
| calculate_reconstruction | 分析 | - | 7大组分重构 |
| calculate_soluble | 分析 | - | 水溶性离子分析 |
| calculate_carbon | 分析 | - | 碳组分分析 |
| calculate_crustal | 分析 | - | 地壳元素分析 |
| calculate_trace | 分析 | - | 微量元素分析 |
| smart_chart_generator | 可视化 | - | 智能图表生成 |
| generate_chart | 可视化 | - | 通用图表生成 |

### 10.2 参考文档

- UDF v2.0规范: `backend/docs/udf_v2_specification.md`
- Chart v3.1规范: `backend/docs/chart_v3_specification.md`
- 气象专家流程: `backend/docs/weather_expert_workflow.md`
- 工具依赖配置: `backend/app/agent/context/tool_dependencies.py`
- 字段映射系统: `backend/app/utils/data_standardizer.py`

### 10.3 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-02-03 | 初始版本，完整颗粒物组分专家工作流程 |

---

**文档维护**: 请在修改组分专家相关代码后及时更新本文档
