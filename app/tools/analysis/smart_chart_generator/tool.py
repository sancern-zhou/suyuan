"""
Smart Chart Generator - 智能图表生成器

统一的数据驱动图表生成工具，支持：
1. 自动调取数据
2. 智能格式转换
3. 多图表生成
4. 统一数据存储

解决工具主动调用和数据格式统一问题。
"""

from typing import Any, Dict, List, Optional
import structlog
import uuid

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.chart_data_converter import convert_chart_data

logger = structlog.get_logger()


class SmartChartGenerator(LLMTool):
    """
    智能图表生成器 - 固定格式数据专用

    核心职责：
    1. 从统一存储加载已分析的固定格式数据
    2. 智能推荐最适合的图表类型
    3. 统一数据转换和存储

    ⚠️ 重要：data_id必须是实际存在的ID，不能使用示例ID！

    适用场景（固定格式数据）：
    ✅ PMF源解析结果 → 自动生成污染源贡献图
    ✅ OBM/OFP分析结果 → 自动生成VOC物种OFP图
    ✅ 组分数据 → 自动生成浓度分布图
    ✅ 气象+污染数据 → 自动生成双轴时序图
    ✅ 任何存储在统一存储中的数据

    决策规则：
    - 如果有data_id（数据已存储）→ 使用smart_chart_generator
    - 如果是PMF/OBM分析结果 → 使用smart_chart_generator
    - 如果需要智能推荐图表类型 → 使用smart_chart_generator

    使用示例：
    1. PMF分析结果：smart_chart_generator(data_id="pmf_result:v1:[实际ID]")
    2. OBM分析结果：smart_chart_generator(data_id="obm_ofp_result:v1:[实际ID]")
    3. VOCs组分数据：smart_chart_generator(data_id="vocs:v1:[实际ID]")

    注意：此工具专门处理固定格式数据，不适用于动态生成的原始数据。
    对于动态数据，请使用 generate_chart 工具。
    """

    def __init__(self):
        function_schema = {
            "name": "smart_chart_generator",
            "description": """
智能图表生成器 - 统一数据驱动的图表生成

功能：
1. 自动从统一存储加载数据（支持PMF、OBM、原始数据）
2. 智能格式转换和数据适配
3. 自动推荐最佳图表类型
4. 生成完整的图表配置（前端直接可用）

支持的数据类型：
- PMF结果 (pmf_result) → 饼图/柱状图/时序图
- OBM/OFP结果 (obm_ofp_result) → 饼图/柱状图/雷达图
- VOCs数据 (vocs) → 饼图/柱状图
- 颗粒物数据 (particulate) → 饼图/柱状图

⚠️ 重要：data_id必须是实际存在的ID，不能使用示例ID！

使用示例：
1. 基于PMF结果生成污染源贡献饼图
   smart_chart_generator(
       data_id="pmf_result:v1:[实际ID]",  # 来自calculate_pmf的返回值
       chart_type="pie"  # 自动推荐
   )

2. 基于OBM结果生成图表
   smart_chart_generator(
       data_id="obm_full_chemistry_result:v1:[实际ID]",  # 来自calculate_obm_full_chemistry的返回值
       chart_type="auto"
   )

3. 基于原始数据生成图表
   smart_chart_generator(
       data_id="vocs:v1:[实际ID]",  # 来自get_component_data的返回值
       chart_type="pie",
       title="VOCs浓度分布"
   )
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": """
## data_id 参数说明

**核心规则**: data_id 必须来自之前工具调用的返回值，绝对不能自己编造！

### 如何获取正确的 data_id

data_id 来自以下工具的返回结果中的 `data_id` 或 `metadata.data_id` 字段：

1. **空气质量数据**: 来自 `get_guangdong_stations` 返回
   - 示例: `"guangdong_stations:v1:a1b2c3d4"`
   - 示例: `"air_quality_unified:v1:e5f6g7h8"`

2. **PMF分析结果**: 来自 `calculate_pmf` 返回
   - 示例: `"pmf_result:v1:i9j0k1l2"`

3. **OBM完整化学机理分析结果**: 来自 `calculate_obm_full_chemistry` 返回
   - 示例: `"obm_full_chemistry_result:v1:m3n4o5p6"`

4. **VOCs组分数据**: 来自 `get_component_data` 返回
   - 示例: `"vocs_unified:v1:q7r8s9t0"`

### 禁止使用的值（会导致错误）

以下格式的值都是错误的，系统会报"未找到数据引用"错误：

- `"air_quality_unified:v1:abc123"` - 虚假的占位ID
- `"pmf_result:v1:xxx"` - 虚假的占位ID
- `"guangdong_stations:v1:12345"` - 编造的ID
- `"[实际ID]"` - 未替换的模板
- 任何你自己编造的ID

### 正确做法

1. 先调用数据获取工具（如 get_guangdong_stations）
2. 从返回结果中提取 data_id 字段的实际值
3. 将该实际值传递给 smart_chart_generator

### 错误示例

```
# 错误！abc123 是虚假ID
smart_chart_generator(data_id="air_quality_unified:v1:abc123")
```

### 正确示例

```
# 第一步：获取数据
result = get_guangdong_stations(...)
# 返回: {"data_id": "guangdong_stations:v1:f8e7d6c5", ...}

# 第二步：使用返回的实际ID
smart_chart_generator(data_id="guangdong_stations:v1:f8e7d6c5")
```
                        """.strip()
                    },
                    "chart_type": {
                        "type": "string",
                        "description": """
图表类型，请根据数据特征和用户意图智能选择最合适的类型。

## 可用图表类型（15种）

### 基础图表（适用于常规数据分析）

**pie（饼图）**
- 适用场景: 展示占比/组成关系
- 最佳实践: 污染源贡献率、物种占比、组分分布等
- 数据要求: 包含分类字段 + 数值字段
- 示例: PMF源解析结果 → pie

**bar（柱状图）**
- 适用场景: 对比不同类别的数值
- 最佳实践: 不同站点对比、不同污染物对比、排名展示等
- 数据要求: 分类字段 + 数值字段
- 示例: 各站点PM2.5浓度对比 → bar

**line（折线图）**
- 适用场景: 展示单一指标的趋势变化
- 最佳实践: 单一污染物随时间变化
- 数据要求: 时间字段 + 单一数值字段
- 示例: PM2.5浓度时间变化 → line

**timeseries（时序图）**
- 适用场景: 展示多系列时间序列，支持多条线对比
- 最佳实践: 多污染物时序对比、多站点时序对比
- 数据要求: 时间字段 + 多个数值系列
- 示例: 多污染物浓度时序变化 → timeseries
- ⚠️ 重要: 如果数据包含多个污染物且有时间序列，优先推荐timeseries而不是bar

**radar（雷达图）**
- 适用场景: 多维度对比
- 最佳实践: 敏感性分析、多指标综合评价
- 数据要求: 多个维度 + 数值
- 示例: O3生成敏感性诊断 → radar

---

### 颗粒物专业图表（适用于颗粒物组分数据）

**carbon_stacked_bar（碳组分堆积图）**
- 适用场景: 展示碳组分（SOC、POC、EC）时序变化，同时叠加PM2.5浓度曲线和EC/OC比值曲线
- 最佳实践: 碳组分分析、OC/EC比值变化趋势
- 数据要求: **必须包含SOC、POC、EC字段**，可选PM2.5和EC_OC字段
- 触发条件: schema_type包含"particulate"或"carbon"，且数据包含碳组分字段
- 示例: 颗粒物碳组分数据 → carbon_stacked_bar

---

### 气象专业图表（适用于气象数据）

**wind_rose（风向玫瑰图）**
- 适用场景: 展示风向风速分布
- 最佳实践: 风向分析、风场特征展示
- 数据要求: **必须包含wind_speed和wind_direction字段**
- 触发条件: schema_type包含"weather"或"meteorology"，且数据包含风向风速
- 示例: 气象数据包含风向风速 → wind_rose

**profile（边界层廓线图）**
- 适用场景: 展示大气垂直结构（高度-参数关系）
- 最佳实践: 温度廓线、风速廓线、边界层分析
- 数据要求: **必须包含altitude/height字段 + 气象参数**
- 触发条件: 数据包含高度字段
- 示例: 边界层气象数据 → profile

---

### 空间图表（适用于地理数据）

**map（地图）**
- 适用场景: 展示地理分布、站点位置
- 最佳实践: 站点分布、污染源位置、区域分布
- 数据要求: **必须包含longitude和latitude字段**
- 触发条件: 数据包含经纬度，需要展示空间位置
- 示例: 监测站点分布 → map

**heatmap（热力图）**
- 适用场景: 展示空间密度/强度分布
- 最佳实践: 污染物浓度空间分布、热点区域识别
- 数据要求: **必须包含longitude、latitude和value字段**
- 触发条件: 数据包含经纬度和数值，需要展示空间强度分布
- 示例: 污染物空间浓度分布 → heatmap

---

### 3D图表（适用于三维空间数据）

**scatter3d（3D散点图）**
- 适用场景: 展示3维空间分布
- 数据要求: **必须包含x、y、z三个坐标字段**
- 示例: 三维空间污染物分布 → scatter3d

**surface3d（3D曲面图）**
- 适用场景: 展示3维连续曲面
- 数据要求: 网格化的3维数据
- 示例: 污染物三维扩散曲面 → surface3d

**line3d（3D线图）**
- 适用场景: 展示3维轨迹
- 数据要求: 有序的3维坐标序列
- 示例: 气团后向轨迹 → line3d

**bar3d（3D柱状图）**
- 适用场景: 3维柱状对比
- 数据要求: 两个分类维度 + 数值
- 示例: 双分类三维对比 → bar3d

**volume3d（3D体素图）**
- 适用场景: 展示3维体积数据
- 数据要求: 3维网格 + 数值
- 示例: 三维污染物体积分布 → volume3d

---

### auto（自动推荐）

**auto**
- 说明: 工具内部使用简单规则推荐
- 建议: **建议优先根据上述规则智能推荐，而不是传入auto**
- 兜底: 如果实在无法判断，可以使用auto让工具用规则推荐

---

## 推荐决策流程

### Step 1: 分析数据schema_type
从data_id的schema_type判断，例如：
- `"pmf_result"` → 直接推荐 `"pie"`
- `"obm_ofp_result"` → 直接推荐 `"bar"`
- `"vocs_unified"` → 直接推荐 `"timeseries"`
- `"weather"` 或 `"meteorology"` → 继续Step 2

### Step 2: 检查数据字段特征

**气象数据检测**:
- 如果包含 `wind_speed` + `wind_direction` → 推荐 `"wind_rose"`
- 如果包含 `altitude` 或 `height` → 推荐 `"profile"`
- 否则 → 推荐 `"timeseries"`

**空间数据检测**:
- 如果包含 `longitude` + `latitude` + `value` → 推荐 `"heatmap"`
- 如果包含 `longitude` + `latitude` → 推荐 `"map"`

**3D数据检测**:
- 如果包含 `x` + `y` + `z` → 推荐 `"scatter3d"`（或其他3D图表）

**时间序列检测**:
- 如果包含时间字段 + 多个污染物 → 推荐 `"timeseries"`
- 如果包含时间字段 + 单一污染物 → 推荐 `"line"` 或 `"timeseries"`
- 如果只有单一时间点 → 推荐 `"bar"`

### Step 3: 结合用户意图
用户明确要求时优先满足：
- 用户说"分析风向" → `"wind_rose"`
- 用户说"查看分布" → `"map"` 或 `"heatmap"`
- 用户说"对比" → `"bar"` 或 `"timeseries"`
- 用户说"占比" → `"pie"`

---

## 示例决策

### 示例1: 气象数据分析

**场景**: 获取了气象数据，包含风速、风向字段
**推荐**: `chart_type="wind_rose"`
**理由**: 气象数据 + 风向风速字段 → 最适合用风向玫瑰图展示

### 示例2: 多污染物时序分析

**场景**: 空气质量数据包含多个污染物（PM2.5、O3、NO2）+ 时间序列
**推荐**: `chart_type="timeseries"`
**理由**: 多污染物+时间序列 → 时序图可展示多条曲线对比

### 示例3: PMF源解析

**场景**: PMF分析结果（schema_type="pmf_result"）
**推荐**: `chart_type="pie"`
**理由**: PMF结果 → 饼图展示源贡献占比

---

## 重要提示

1. **优先自己推荐**: 不要轻易使用 `chart_type="auto"`，优先基于上述规则自己推荐
2. **多污染物场景**: 如果数据包含多个污染物且有时间序列，`timeseries`比`bar`更适合
3. **气象数据特殊处理**: 如果是气象数据，检查是否包含风向风速字段，有则推荐`wind_rose`
4. **空间数据优先**: 如果数据包含经纬度，优先考虑`map`或`heatmap`
5. **用户意图优先**: 如果用户明确说明分析目的，优先满足用户需求

---

## ⚠️ 重要限制（避免Agent误用）

**不适合使用smart_chart_generator的场景**:
- ❌ 需要指定特定时间段的数据筛选（如"2024年1月数据"）
- ❌ 需要指定特定污染物类型（如"只看O3数据"）
- ❌ 原始连续时间序列+多污染物数据需要灵活分析
- ❌ 需要对图表数据进行动态过滤或转换

**正确选择**:
- ✅ 已存储的分析结果（PMF/OBM等）→ 使用 `smart_chart_generator`
- ✅ 原始时间序列数据需灵活处理 → 使用 `generate_chart`（直接传数据）
- ✅ 修改已有图表的配置/样式 → 使用 `revise_chart`（传入原图表data_id）

**决策规则**:
- 有data_id且是固定格式分析结果 → `smart_chart_generator`
- 原始数据需要灵活筛选/时间段 → `generate_chart`
- 修改现有图表 → `revise_chart`
                        """.strip(),
                        "enum": [
                            # 基础图表
                            "pie", "bar", "line", "timeseries", "radar",
                            # 气象图表
                            "weather_timeseries", "wind_rose", "profile",
                            # 颗粒物图表（新增）
                            "carbon_stacked_bar",
                            # 空气质量专用图表（新增）
                            "facet_timeseries",
                            # 空间图表
                            "map", "heatmap",
                            # 3D图表
                            "scatter3d", "surface3d", "line3d", "bar3d", "volume3d",
                            # 兜底
                            "auto"
                        ],
                        "default": "auto"
                    },
                    "title": {
                        "type": "string",
                        "description": "图表标题（可选）"
                    },
                    "options": {
                        "type": "object",
                        "description": "额外选项（可选），包含：top_n（整数，取前N项，默认10）、show_legend（布尔，是否显示图例，默认true）",
                        "properties": {
                            "top_n": {
                                "type": "integer",
                                "description": "取前N项（用于排序）",
                                "default": 10
                            },
                            "show_legend": {
                                "type": "boolean",
                                "description": "是否显示图例",
                                "default": True
                            }
                        }
                    },
                    "selected_pollutants": {
                        "type": "array",
                        "description": """
⚠️ 此参数用于筛选【污染物指标】，不是城市/站点名称！

**默认行为（不指定此参数）**:
- 显示所有检测到的污染物指标（PM2.5、PM10、O3、NO2、SO2、CO、AQI等）
- 适用于：展示完整的污染物浓度对比

**什么时候使用此参数**:
- 用户明确说"只看PM2.5" → 传 ["PM2_5"]
- 用户说"对比PM2.5和臭氧" → 传 ["PM2_5", "O3"]
- 用户说"看所有污染物" → 不传此参数（默认全部显示）

**⚠️ 重要：只传污染物字段名，不要传城市/站点名称！**
- ✅ 正确示例：["PM2_5", "O3", "NO2"]
- ❌ 错误示例：["肇庆市", "佛山市"] ← 这是城市名，应该用selected_stations参数！

**标准字段名（必须使用下列名称）**:
- PM2_5 (细颗粒物)
- PM10 (可吸入颗粒物)
- O3 (臭氧)
- O3_8h (臭氧8小时)
- NO2 (二氧化氮)
- SO2 (二氧化硫)
- CO (一氧化碳)
- AQI (空气质量指数)

**错误示例（字段名不匹配会导致筛选失效）**:
- ❌ ["PM2.5"] - 错误！应该用下划线: PM2_5
- ❌ ["pm2_5", "o3"] - 错误！大小写敏感
- ❌ ["肇庆市", "佛山市"] - 错误！这是城市名，不是污染物名称

**适用场景**:
- 仅适用于 guangdong_stations 和 air_quality_unified 类型的数据
- 如果不指定，默认显示所有污染物
                        """.strip(),
                        "items": {
                            "type": "string"
                        },
                        "default": None
                    },
                    "selected_stations": {
                        "type": "array",
                        "description": """
⚠️ 此参数用于筛选【城市/站点名称】，不是污染物指标！

**默认行为（不指定此参数）**:
- 显示所有检测到的城市/站点的对比
- 例如：数据包含肇庆、佛山、广州、清远、云浮五个城市时，默认全部显示

**什么时候使用此参数**:
- 用户说"只看肇庆市的数据" → 传 ["肇庆市"]
- 用户说"对比肇庆、佛山、广州" → 传 ["肇庆市", "佛山市", "广州市"]
- 用户说"查看周边所有城市" → 不传此参数（默认全部显示）

**⚠️ 重要：只传城市/站点名称，不要传污染物字段名！**
- ✅ 正确示例：["肇庆市", "佛山市", "广州市"]
- ❌ 错误示例：["PM2_5", "O3"] ← 这是污染物名，应该用selected_pollutants参数！

**城市级别数据（guangdong_stations）示例**:
- ["肇庆市"] - 只显示肇庆市
- ["肇庆市", "佛山市", "广州市"] - 显示这三个城市
- ["云浮", "清远"] - 部分数据可能不带"市"后缀，需根据实际数据调整

**站点级别数据示例**:
- ["四会威整"] - 只显示四会威整站点
- ["四会威整", "临江", "综合观测点"] - 显示这三个站点

**智能分组规则（自动应用）**:
- 多城市/站点 + 单污染物 → 每个城市/站点一条线
- 单城市/站点 + 多污染物 → 每个污染物一条线
- 多城市/站点 + 多污染物 → 每个城市/站点×污染物组合一条线（图例会显示"城市 - 污染物"）

**使用场景示例**:
- 用户说"肇庆及周边城市的臭氧对比" → selected_stations不传（全部城市），selected_pollutants=["O3"]
- 用户说"只看肇庆和佛山" → selected_stations=["肇庆市", "佛山市"]，selected_pollutants不传（全部污染物）
- 用户说"肇庆市的PM2.5和臭氧变化" → selected_stations=["肇庆市"]，selected_pollutants=["PM2_5", "O3"]

**适用场景**:
- 仅适用于 guangdong_stations 和 air_quality_unified 类型的数据
- 城市/站点名称必须在数据中实际存在
- 如果不指定，默认显示所有城市/站点
                        """.strip(),
                        "items": {
                            "type": "string"
                        },
                        "default": None
                    }
                },
                "required": ["data_id"]
            }
        }

        super().__init__(
            name="smart_chart_generator",
            description="Smart chart generator with unified data conversion",
            category=ToolCategory.VISUALIZATION,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(
        self,
        context: Any,
        data_id: str,
        chart_type: str = "auto",
        title: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        selected_pollutants: Optional[List[str]] = None,
        selected_stations: Optional[List[str]] = None,
        enable_multi_chart: Optional[bool] = False,
        multi_chart_layout: Optional[str] = "main",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行智能图表生成

        Args:
            context: 执行上下文（用于加载数据）
            data_id: 数据引用ID
            chart_type: 图表类型（auto=智能推荐）
            title: 图表标题
            options: 额外选项
            selected_pollutants: 可选，指定要显示的污染物列表
                - 为None或空列表时，显示所有检测到的污染物（默认行为）
                - 指定后，只显示选定的污染物（如["PM2_5", "O3"]）
                - 重要：必须使用标准字段名（PM2_5, O3, NO2等）
            selected_stations: 可选，指定要显示的站点/城市列表
                - 为None或空列表时，显示所有检测到的站点/城市（默认行为）
                - 指定后，只显示选定的站点/城市（如["肇庆市", "佛山市"]）

        Returns:
            生成的图表配置和数据
        """
        try:
            logger.info(
                "smart_chart_generation_start",
                data_id=data_id,
                chart_type=chart_type,
                session_id=context.session_id
            )

            # Step 1: 加载数据
            try:
                handle = context.get_handle(data_id)
            except KeyError:
                # 【方案A】所有返回都必须是UDF v1.0格式
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "smart_chart_generator",
                        "error_type": "data_not_found"
                    },
                    "summary": f"[FAIL] 未找到数据引用 {data_id}"
                }

            # Step 3: 解析数据类型
            schema_type = handle.schema

            # Step 4: 加载实际数据 - Context-Aware V2模式
            # 智能选择加载方式：原始数据（字典） vs 类型化数据（Pydantic）
            try:
                # 【快速修复】regional_city_comparison 必须强制标准化
                # 这些类型需要始终走标准转换流程，避免零数据问题
                force_standard_types = ["regional_city_comparison", "regional_station_comparison", "air_quality_unified"]

                if schema_type in force_standard_types:
                    # 强制使用 get_data() 确保经过 DataContextManager 的标准化流程
                    raw_data = context.get_data(data_id)
                    logger.info(f"快速修复：强制标准化 {schema_type} 数据")
                elif schema_type in ["pmf_result", "obm_ofp_result", "chart_config", "guangdong_stations"]:
                    # 分析结果/字典格式数据：使用get_raw_data获取原始字典数据
                    raw_data = context.get_raw_data(data_id)
                elif schema_type in ["vocs_unified", "particulate_unified"]:
                    # 统一格式数据：使用get_data()进行类型化加载
                    raw_data = context.get_data(data_id)
                elif schema_type in ["weather", "meteorology", "meteorology_unified"]:
                    # 气象数据：使用get_raw_data获取原始字典数据（避免类型化转换问题）
                    raw_data = context.get_raw_data(data_id)
                    logger.info(
                        "smart_chart_meteorology_data_loaded",
                        data_id=data_id,
                        record_count=len(raw_data) if raw_data else 0
                    )
                else:
                    # Pydantic类型数据：使用get_data()进行类型化加载
                    raw_data = context.get_data(data_id)

                # 如果是Pydantic对象列表，转换为字典列表
                if raw_data and hasattr(raw_data[0], 'dict'):
                    raw_data = [item.dict() for item in raw_data]

                # 【调试】记录加载后的数据信息
                if raw_data:
                    logger.debug(
                        "smart_chart_data_loaded_debug",
                        schema_type=schema_type,
                        record_count=len(raw_data),
                        first_record_fields=list(raw_data[0].keys()) if raw_data else []
                    )

            except Exception as exc:
                logger.error(
                    "smart_chart_data_load_failed",
                    data_id=data_id,
                    error=str(exc)
                )
                # 【方案A】所有返回都必须是UDF v1.0格式
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "smart_chart_generator",
                        "error_type": "data_load_failed",
                        "data_id": data_id
                    },
                    "summary": f"[FAIL] 无法加载数据 {data_id}: {str(exc)}"
                }

            logger.info(
                "smart_chart_data_loaded",
                data_id=data_id,
                schema=schema_type,
                record_count=handle.record_count
            )

            # 【优化2】检查上游工具是否已包含visuals，跳过smart_chart_generator
            has_existing_visuals = self._check_existing_visuals(raw_data, schema_type)
            if has_existing_visuals:
                logger.info(
                    "skipping_smart_chart_visuals_exist",
                    reason="上游工具已包含可视化配置，跳过smart_chart_generator",
                    data_id=data_id,
                    schema_type=schema_type
                )
                return self._build_skipped_result(raw_data, data_id, schema_type)

            # 【Task 8】记录Agent传入的原始chart_type，用于评估推荐准确率
            agent_requested_chart_type = chart_type  # 保存Agent原始推荐
            data_time_count = self._count_time_points(raw_data)
            data_pollutant_count = self._count_pollutants(raw_data)
            data_has_time = data_time_count > 0

            logger.info(
                "agent_chart_type_selection_tracking",
                agent_requested_chart_type=agent_requested_chart_type,
                data_id=data_id,
                schema_type=schema_type,
                data_features={
                    "record_count": handle.record_count,
                    "time_count": data_time_count,
                    "pollutant_count": data_pollutant_count,
                    "has_time_field": data_has_time
                },
                selected_pollutants=selected_pollutants,
                note="Agent推荐追踪 - 用于评估准确率"
            )

            # 默认根据元数据锁定区域对比的目标污染物，避免一次性展示所有指标
            if schema_type in ["regional_city_comparison", "regional_station_comparison"] and not selected_pollutants:
                metadata_pollutants = self._infer_pollutants_from_metadata(handle.metadata)
                if metadata_pollutants:
                    selected_pollutants = metadata_pollutants
                    logger.info(
                        "selected_pollutants_inferred_from_metadata",
                        inferred_pollutants=selected_pollutants,
                        schema_type=schema_type,
                        data_id=data_id
                    )

            # Step 5: 智能推荐图表类型
            if chart_type == "auto":
                chart_type = self._recommend_chart_type(schema_type, raw_data, selected_pollutants)
                logger.info(
                    "smart_chart_type_recommended",
                    original_request="auto",
                    recommended=chart_type,
                    schema=schema_type
                )
            else:
                # 容错处理：自动纠正常见的图表类型命名错误
                chart_type = self._normalize_chart_type(chart_type)
                logger.info(
                    "smart_chart_type_normalized",
                    original_request=chart_type,
                    normalized=chart_type
                )

            # Step 5.5: 兜底逻辑 - 验证chart_type与schema_type兼容性
            compatibility_result = self._validate_chart_type_compatibility(
                schema_type=schema_type,
                chart_type=chart_type,
                data=raw_data
            )

            # 【Task 8】记录兼容性验证结果和最终使用的chart_type
            final_chart_type_used = chart_type  # 初始值
            was_downgraded = False

            if not compatibility_result["compatible"]:
                # 不兼容，尝试降级
                logger.warning(
                    "smart_chart_type_incompatible",
                    schema_type=schema_type,
                    requested_chart_type=chart_type,
                    reason=compatibility_result.get("reason"),
                    suggested_fallback=compatibility_result.get("fallback")
                )

                if compatibility_result.get("fallback"):
                    # 自动降级到推荐的图表类型
                    original_chart_type = chart_type
                    chart_type = compatibility_result["fallback"]
                    final_chart_type_used = chart_type
                    was_downgraded = True

                    logger.info(
                        "smart_chart_type_fallback",
                        original=original_chart_type,
                        fallback=chart_type,
                        reason=compatibility_result.get("reason")
                    )

                    # 【Task 8】记录降级事件，用于评估Agent推荐质量
                    logger.info(
                        "agent_chart_type_downgraded",
                        agent_requested=agent_requested_chart_type,
                        final_used=final_chart_type_used,
                        schema_type=schema_type,
                        downgrade_reason=compatibility_result.get("reason"),
                        available_types=compatibility_result.get("available_types", []),
                        note="Agent推荐不兼容，已自动降级"
                    )
                else:
                    # 无法降级，返回结构化错误
                    return {
                        "status": "failed",
                        "success": False,
                        "data": None,
                        "metadata": {
                            "tool_name": "smart_chart_generator",
                            "error_type": "chart_type_incompatible",
                            "schema_type": schema_type,
                            "requested_chart_type": chart_type,
                            "reason": compatibility_result.get("reason"),
                            "available_types": compatibility_result.get("available_types", [])
                        },
                        "summary": f"[FAIL] 图表类型不兼容: {compatibility_result.get('reason')}"
                    }
            else:
                # 兼容性验证通过
                logger.info(
                    "smart_chart_type_compatible",
                    agent_requested=agent_requested_chart_type,
                    final_used=chart_type,
                    schema_type=schema_type,
                    compatible=True,
                    note="Agent推荐兼容，直接使用"
                )

            # 【Task 8】记录最终决策结果，用于统计Agent推荐准确率
            logger.info(
                "agent_chart_type_final_decision",
                agent_requested=agent_requested_chart_type,
                final_used=final_chart_type_used if was_downgraded else chart_type,
                was_downgraded=was_downgraded,
                schema_type=schema_type,
                data_features={
                    "record_count": handle.record_count,
                    "time_count": data_time_count,
                    "pollutant_count": data_pollutant_count
                },
                compatibility_result={
                    "compatible": compatibility_result.get("compatible", True),
                    "reason": compatibility_result.get("reason")
                },
                accuracy_metric={
                    "agent_correct": not was_downgraded and agent_requested_chart_type != "auto",
                    "agent_used_auto": agent_requested_chart_type == "auto",
                    "recommendation_source": "agent" if agent_requested_chart_type != "auto" else "tool_fallback"
                },
                note="用于统计Agent推荐准确率和质量评估"
            )

            # Step 6: 数据转换
            converted_data = self._convert_data_for_chart(
                data=raw_data,
                schema_type=schema_type,
                chart_type=chart_type,
                options=options or {},
                selected_pollutants=selected_pollutants,
                selected_stations=selected_stations
            )

            if "error" in converted_data:
                # 【方案A】所有返回都必须是UDF v1.0格式
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "smart_chart_generator",
                        "error_type": "data_convert_failed",
                        "data_id": data_id
                    },
                    "summary": f"[FAIL] 数据转换失败: {converted_data['error']}"
                }

            # 【v2.1优化】气象数据自动启用多图分组模式
            # 气象数据包含多种不同单位/量级的要素，必须分组展示
            if schema_type in ["weather", "meteorology", "meteorology_unified"]:
                enable_multi_chart = True
                logger.info(
                    "meteorology_auto_multi_chart_enabled",
                    schema_type=schema_type,
                    reason="气象数据自动启用专业分组图表"
                )

            # 【新增】多站点+多污染物场景自动启用分面图
            # 检测条件：站点>=3 且 污染物>=2 且 时间点>1
            station_count = self._count_stations(raw_data)
            pollutant_count = self._count_pollutants(raw_data)
            time_count = self._count_time_points(raw_data)
            is_multi_station_multi_pollutant = station_count >= 3 and pollutant_count >= 2 and time_count > 1

            if schema_type in ["air_quality_unified", "guangdong_stations"] and is_multi_station_multi_pollutant and not enable_multi_chart:
                enable_multi_chart = True
                logger.info(
                    "auto_multi_chart_for_facet_enabled",
                    schema_type=schema_type,
                    station_count=station_count,
                    pollutant_count=pollutant_count,
                    time_count=time_count,
                    reason=f"检测到多站点({station_count}个)+多污染物({pollutant_count}个)数据，自动启用分面图组合"
                )

            # 【新增】单日多图智能生成
            if enable_multi_chart:
                logger.info(
                    "smart_chart_multi_chart_enabled",
                    layout=multi_chart_layout,
                    schema_type=schema_type,
                    original_chart_type=chart_type
                )

                # 生成多图组合
                multi_charts = await self._generate_intelligent_chart_combination(
                    context=context,
                    data=raw_data,
                    schema_type=schema_type,
                    base_chart_type=chart_type,
                    layout=multi_chart_layout,
                    options=options or {},
                    selected_pollutants=selected_pollutants,
                    selected_stations=selected_stations,
                    data_id=data_id
                )

                if multi_charts:
                    logger.info(
                        "smart_chart_multi_chart_generated",
                        chart_count=len(multi_charts),
                        charts=[c.get("type") for c in multi_charts]
                    )

                    # 保存每个图表到 chart_config（关键修复：确保图表被保存）
                    from datetime import datetime
                    from app.schemas.chart import ChartConfig
                    
                    saved_chart_ids = []
                    visual_blocks = []
                    
                    for i, chart_cfg in enumerate(multi_charts):
                        # 创建 ChartConfig 模型
                        chart_config_model = ChartConfig(
                            chart_id=chart_cfg.get("id", f"chart_{uuid.uuid4().hex[:8]}"),
                            chart_type=chart_cfg.get("type", "timeseries"),
                            title=chart_cfg.get("title", f"图表{i+1}"),
                            payload=chart_cfg,
                            method="smart_chart_generator_multi",
                            template_used=None,
                            scenario=f"multi_chart_{multi_chart_layout}",
                            data_record_count=1,
                            pollutant=None,
                            station_name=chart_cfg.get("meta", {}).get("station_name"),
                            venue_name=None,
                            generated_at=datetime.now().isoformat(),
                            metadata={
                                "source_data_id": data_id,
                                "source_schema": schema_type,
                                "chart_index": i
                            }
                        )
                        
                        try:
                            chart_data_id = context.save_data(
                                data=[chart_config_model],
                                schema="chart_config",
                                metadata={
                                    "source_data_id": data_id,
                                    "source_schema": schema_type,
                                    "chart_type": chart_cfg.get("type"),
                                    "generated_by": "smart_chart_generator_multi",
                                    "chart_index": i
                                }
                            )
                            saved_chart_ids.append(chart_data_id)
                            logger.info(
                                "smart_chart_multi_saved",
                                chart_data_id=chart_data_id,
                                chart_type=chart_cfg.get("type"),
                                chart_index=i,
                                source_data_id=data_id
                            )
                        except Exception as exc:
                            logger.error(
                                "smart_chart_multi_save_failed",
                                error=str(exc),
                                chart_index=i,
                                chart_type=chart_cfg.get("type")
                            )
                        
                        # 构建 visual block
                        visual_block = self._create_visual_block(
                            chart_config=chart_cfg,
                            index=i,
                            source_data_id=data_id,
                            generator="smart_chart_generator_multi",
                            layout_hint=multi_chart_layout,
                            schema_type=schema_type
                        )
                        visual_blocks.append(visual_block.dict())

                    # 返回多图结果
                    from app.schemas.unified import create_visual_unified_data
                    visual_unified_data = create_visual_unified_data(
                        visuals=visual_blocks,
                        source_data_ids=[data_id],
                        scenario=f"multi_chart_{multi_chart_layout}",
                        generator="smart_chart_generator",
                        station_name=converted_data.get("meta", {}).get("station_name"),
                        source="smart_chart_generator"
                    )

                    return {
                        "status": "success",
                        "success": True,
                        "data": None,
                        "visuals": visual_blocks,
                        "metadata": {
                            "tool_name": "smart_chart_generator",
                            "data_id": data_id,
                            "source_data_id": data_id,
                            "chart_type": "multi_chart",
                            "schema_type": schema_type,
                            "schema_version": "v2.0",
                            "record_count": len(multi_charts),
                            "source_data_ids": [data_id],
                            "saved_chart_ids": saved_chart_ids,
                            "scenario": f"multi_chart_{multi_chart_layout}",
                            "generator": "smart_chart_generator",
                            "registry_schema": "chart_config",
                            "multi_chart": True,
                            "layout": multi_chart_layout,
                            "chart_types": [c.get("type") for c in multi_charts]
                        },
                        "summary": f"[OK] 智能多图生成完成 - 生成了{len(multi_charts)}个图表: {', '.join([c.get('type') for c in multi_charts])}"
                    }

            # Step 6.5: 增强图表为v3.1格式（新增）
            from app.utils.chart_data_converter import _validate_and_enhance_chart_v3_1

            enhanced_chart = _validate_and_enhance_chart_v3_1(
                chart=converted_data,
                generator="smart_chart_generator",
                original_data_ids=[data_id],
                scenario=chart_type
            )

            if "error" in enhanced_chart:
                # 验证失败
                logger.warning(
                    "smart_chart_v3_1_enhancement_failed",
                    error=enhanced_chart.get("error"),
                    data_id=data_id
                )
                # 继续使用原始数据（向后兼容）
                enhanced_chart = converted_data

            # Step 7: 构建最终图表配置
            final_chart = self._build_chart_config(
                converted_data=enhanced_chart,
                title=title,
                chart_type=chart_type,
                original_data_id=data_id,
                options=options or {}
            )

            # Step 8: 保存图表配置到统一存储
            # 【方案A】图表配置必须保存，否则返回失败
            from datetime import datetime
            from app.schemas.chart import ChartConfig

            # 创建ChartConfig模型
            chart_config_model = ChartConfig(
                chart_id=final_chart.get("id", "chart_" + uuid.uuid4().hex[:8]),
                chart_type=final_chart.get("type", "pie"),
                title=final_chart.get("title", title or "图表"),
                payload=final_chart,
                method="smart_chart_generator",
                template_used=None,
                scenario="auto",
                data_record_count=1,
                pollutant=None,
                station_name=None,
                venue_name=None,
                generated_at=datetime.now().isoformat(),
                metadata={
                    "source_data_id": data_id,
                    "source_schema": schema_type
                }
            )

            try:
                chart_data_id = context.save_data(
                    data=[chart_config_model],
                    schema="chart_config",
                    metadata={
                        "source_data_id": data_id,
                        "source_schema": schema_type,
                        "chart_type": chart_type,
                        "generated_by": "smart_chart_generator"
                    }
                )

                logger.info(
                    "smart_chart_saved",
                    chart_data_id=chart_data_id,
                    source_data_id=data_id
                )
            except Exception as exc:
                # 【方案A】保存失败则返回错误，不生成无用备用ID
                logger.error(
                    "smart_chart_save_failed",
                    error=str(exc),
                    exc_info=True
                )
                return {
                    "status": "failed",
                    "success": False,
                    "data": None,
                    "metadata": {
                        "tool_name": "smart_chart_generator",
                        "error_type": "data_save_failed",
                        "data_id": data_id
                    },
                    "summary": f"[FAIL] 图表配置保存失败: {str(exc)}"
                }

            # Step 9: 构建返回结果（UDF v1.0标准格式）
            # 确保final_chart是纯字典格式（没有Pydantic对象）
            chart_dict = final_chart
            if hasattr(chart_dict, 'model_dump'):
                # 如果是Pydantic对象，转换为字典
                chart_dict = chart_dict.model_dump()
            elif hasattr(chart_dict, 'dict'):
                # 旧版本Pydantic
                chart_dict = chart_dict.dict()
            
            # 【关键修复】确保chart_dict.meta中包含source_data_id，用于报告导出时的图表分类
            if "meta" not in chart_dict:
                chart_dict["meta"] = {}
            chart_dict["meta"]["source_data_id"] = data_id
            chart_dict["meta"]["data_id"] = data_id  # 也添加data_id字段，方便查找
            # 如果已有original_data_ids，确保source_data_id也在其中
            if "original_data_ids" not in chart_dict["meta"]:
                chart_dict["meta"]["original_data_ids"] = [data_id]
            elif data_id not in chart_dict["meta"]["original_data_ids"]:
                chart_dict["meta"]["original_data_ids"].append(data_id)

            # 【新增】分析数据有效性（用于LLM观测）
            from datetime import datetime
            data_analysis = self._analyze_chart_data_validity(chart_dict, raw_data)

            # 【关键修复】如果数据无效，跳过图表生成
            if not data_analysis["is_valid"]:
                logger.info(
                    "skipping_chart_generation_for_invalid_data",
                    data_id=data_id,
                    chart_type=chart_type,
                    issue=data_analysis.get("issue", "unknown"),
                    recommendation=data_analysis.get("recommendation", "")
                )
                return self._build_skipped_result(raw_data, data_id, schema_type)

            # 【新增】记录详细的生成过程
            generation_process = {
                "initial_request": {
                    "agent_requested_chart_type": agent_requested_chart_type,
                    "chart_type_parameter": chart_type,
                    "schema_type": schema_type,
                    "data_id": data_id
                },
                "intelligence_used": {
                    "auto_recommended": agent_requested_chart_type == "auto",
                    "type_normalized": agent_requested_chart_type != self._normalize_chart_type(agent_requested_chart_type),
                    "downgrade_applied": was_downgraded,
                    "compatibility_check_passed": compatibility_result.get("compatible", True),
                    "fallback_reason": compatibility_result.get("reason") if was_downgraded else None
                },
                "data_characteristics": {
                    "record_count": handle.record_count,
                    "time_points": data_time_count,
                    "pollutant_count": data_pollutant_count,
                    "selected_pollutants": selected_pollutants
                },
                "final_result": {
                    "chart_type_final": final_chart_type_used if was_downgraded else chart_type,
                    "chart_id": final_chart.get("id"),
                    "data_id": chart_data_id,
                    "generation_timestamp": datetime.now().isoformat(),
                    "schema_type": schema_type,
                    "data_valid": data_analysis["is_valid"]
                }
            }

            # 构建符合UDF v1.0标准的结果
            result_data = {
                "success": True,
                "chart": chart_dict,  # v3.0图表格式
                "data_id": chart_data_id,     # 图表存储ID
                "source_data_id": data_id,    # 原始数据ID
                "schema_type": schema_type,   # 原始数据类型
                "chart_type": chart_type,
                "detailed_summary": self._build_summary(
                    final_chart=chart_dict,
                    source_data_id=data_id,
                    schema_type=schema_type,
                    chart_type=chart_type,
                    options=options or {}
                )
            }

            # 【方案A关键】确保observation中包含registry_schema，让HybridMemoryManager正确识别
            result_data["registry_schema"] = "chart_config"

            # UDF v1.0最终检查：确保所有字段都是JSON可序列化
            import json
            try:
                json.dumps(result_data, ensure_ascii=False, default=str)
            except TypeError as e:
                logger.error(
                    "smart_chart_result_not_json_serializable",
                    error=str(e),
                    message="结果包含不可序列化的对象，违反UDF v1.0规范"
                )
                # 尝试清理不可序列化的对象
                for key, value in result_data.items():
                    if hasattr(value, 'model_dump'):
                        result_data[key] = value.model_dump()
                    elif hasattr(value, 'dict'):
                        result_data[key] = value.dict()

            logger.info(
                "smart_chart_generation_complete",
                data_id=data_id,
                chart_type=chart_type,
                chart_id=final_chart.get("id"),
                success=True,
                data_valid=data_analysis["is_valid"]
            )

            # 【UDF v2.0】构建visuals结构
            from app.schemas.unified import VisualBlock, create_visual_unified_data
            from datetime import datetime

            # 生成时间戳
            current_timestamp = datetime.now().isoformat()

            # 根据schema_type推断expert_source（用于前端大屏分类）
            expert_source = self._infer_expert_source(schema_type, data_id)
            
            # 【关键修复】确保chart_dict.meta中包含expert信息，用于报告导出时的图表分类
            if "meta" not in chart_dict:
                chart_dict["meta"] = {}
            chart_dict["meta"]["expert"] = expert_source  # 添加expert字段，用于分类
            chart_dict["meta"]["generator"] = "smart_chart_generator"  # 确保generator字段存在

            # 【关键修复】统一ID格式：只使用简洁格式，避免完整的data_id格式
            # 从final_chart中提取ID，如果包含":"则生成简洁ID
            final_chart_id = final_chart.get("id", "")
            if ":" in final_chart_id or not final_chart_id:
                # 如果ID包含":"（完整data_id格式）或为空，生成简洁ID
                # 格式：{类型}_{短hash}
                short_hash = uuid.uuid4().hex[:8]
                chart_type_short = chart_type[:10]
                final_chart_id = f"{chart_type_short}_{short_hash}"
                logger.debug(
                    "visual_block_id_generated",
                    original_id=final_chart.get("id"),
                    generated_id=final_chart_id,
                    chart_type=chart_type
                )

            # 创建VisualBlock
            visual_block = VisualBlock(
                id=final_chart_id,
                type="chart",
                schema="chart_config",
                payload=chart_dict,
                meta={
                    "schema_version": "v2.0",  # UDF v2.0版本
                    "generator": "smart_chart_generator",  # 生成工具
                    "generator_version": "2.0.0",  # 工具版本
                    "source_data_id": data_id,  # 【新增】单个source_data_id，方便报告导出逻辑读取
                    "source_data_ids": [data_id],  # 源数据ID列表
                    "original_data_ids": [data_id],  # 原始数据ID列表
                    "expert": expert_source,  # 【新增】expert字段，用于报告导出分类
                    "expert_source": expert_source,  # 数据来源专家类型（用于前端大屏分类）
                    "data_source": schema_type,  # 原始数据类型
                    "scenario": chart_type,  # 场景标识
                    "interaction_group": "chart_interaction",  # 交互组
                    "data_flow": ["source_data", "chart_config"],  # 数据流
                    "layout_hint": "main",  # 布局提示
                    "timestamp": current_timestamp,  # 时间戳
                    "created_at": current_timestamp,  # 创建时间
                    # 【保留】详细的生成过程信息
                    "generation_details": {
                        "intelligent_decision": {
                            "initial_request": agent_requested_chart_type,
                            "final_used": final_chart_type_used if was_downgraded else chart_type,
                            "was_downgraded": was_downgraded,
                            "compatibility_check": compatibility_result.get("compatible", True),
                            "reason": compatibility_result.get("reason") if was_downgraded else "initial_request_accepted"
                        },
                        "data_characteristics": {
                            "record_count": handle.record_count,
                            "time_points": data_time_count,
                            "pollutant_count": data_pollutant_count,
                            "schema_type": schema_type,
                            "selected_pollutants": selected_pollutants
                        },
                        "data_analysis": data_analysis
                    }
                }
            )

            # 创建UDF v2.0可视化数据
            visual_unified_data = create_visual_unified_data(
                visuals=[visual_block],
                source_data_ids=[data_id],
                scenario="chart_generation",
                generator="smart_chart_generator",
                station_name=final_chart.get("meta", {}).get("station_name"),
                source="smart_chart_generator"
            )

            # 返回UDF v2.0格式
            return {
                "status": "success",
                "success": True,
                "data": None,  # v2.0格式使用visuals字段
                "visuals": [visual_block.dict()],  # v2.0新增字段
                "metadata": {
                    "tool_name": "smart_chart_generator",
                    "data_id": chart_data_id,  # 图表存储ID
                    "source_data_id": data_id,  # 原始数据ID
                    "chart_type": chart_type,
                    "schema_type": schema_type,
                    "schema_version": "v2.0",  # UDF v2.0 标记
                    "record_count": 1,  # 图表数量
                    "source_data_ids": [data_id],
                    "scenario": "chart_generation",
                    "generator": "smart_chart_generator",
                    "registry_schema": "chart_config",  # 让HybridMemoryManager识别
                    # 【新增】详细的生成过程和数据分析
                    "generation_debug": {
                        "process": generation_process,  # 详细生成过程
                        "data_analysis": data_analysis,  # 数据有效性分析
                        "intelligence_metrics": {
                            "agent_correct": not was_downgraded and agent_requested_chart_type != "auto",
                            "agent_used_auto": agent_requested_chart_type == "auto",
                            "recommendation_source": "agent" if agent_requested_chart_type != "auto" else "tool_fallback",
                            "compatibility_validation": "passed" if compatibility_result.get("compatible", True) else "failed"
                        }
                    }
                },
                "summary": f"[OK] 智能图表生成完成，基于{schema_type}数据生成{chart_type}图表，数据有效性: {'有效' if data_analysis['is_valid'] else '异常'} (UDF v2.0)"
            }

        except Exception as e:
            logger.error(
                "smart_chart_generation_failed",
                error=str(e),
                exc_info=True
            )
            # 【方案A】所有返回都必须是UDF v1.0格式
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "tool_name": "smart_chart_generator",
                    "error_type": "execution_failed",
                    "data_id": data_id
                },
                "summary": f"[FAIL] 智能图表生成失败: {str(e)[:50]}"
            }

    async def _generate_intelligent_chart_combination(
        self,
        context: Any,
        data: Any,
        schema_type: str,
        base_chart_type: str,
        layout: str,
        options: Dict[str, Any],
        selected_pollutants: Optional[List[str]],
        selected_stations: Optional[List[str]],
        data_id: str
    ) -> List[Dict[str, Any]]:
        """
        生成智能多图组合

        Args:
            context: 执行上下文
            data: 数据
            schema_type: 数据类型
            base_chart_type: 基础图表类型
            layout: 布局类型
            options: 选项
            selected_pollutants: 选中的污染物
            selected_stations: 选中的站点
            data_id: 数据ID

        Returns:
            图表配置列表
        """
        charts = []

        # 气象数据专用分组图表生成（v2.1优化）
        # 直接使用 MeteorologyChartConverter.convert_to_chart_group() 生成专业分组
        if schema_type in ["weather", "meteorology", "meteorology_unified"]:
            logger.info(
                "smart_chart_meteorology_detected",
                schema_type=schema_type,
                data_id=data_id,
                data_type=type(data).__name__ if hasattr(data, '__class__') else str(type(data)),
                record_count=len(data) if isinstance(data, list) else 'N/A'
            )

            try:
                from app.utils.chart_converters.meteorology_converter import MeteorologyChartConverter

                # 获取站点名称
                station_name = options.get("station_name", "气象站点")
                if isinstance(data, list) and len(data) > 0:
                    first_record = data[0] if isinstance(data[0], dict) else {}
                    station_name = first_record.get("station_name", first_record.get("stationName", station_name))
                elif isinstance(data, dict):
                    station_name = data.get("station_name", data.get("stationName", station_name))

                logger.info(
                    "smart_chart_meteorology_station_name",
                    station_name=station_name,
                    data_id=data_id
                )

                # 使用专业分组方法生成图表
                grouped_charts = MeteorologyChartConverter.convert_to_chart_group(
                    data=data,
                    station_name=station_name,
                    generator="smart_chart_generator"
                )

                logger.info(
                    "meteorology_chart_group_generated",
                    chart_count=len(grouped_charts),
                    chart_types=[c.get("type") for c in grouped_charts if "error" not in c],
                    errors=[c.get("error") for c in grouped_charts if "error" in c]
                )

                # 过滤掉错误的图表
                for chart in grouped_charts:
                    if "error" not in chart:
                        charts.append(chart)
                    else:
                        logger.warning(
                            "smart_chart_meteorology_chart_skipped",
                            error=chart.get("error"),
                            chart_type=chart.get("type", "unknown")
                        )

                if charts:
                    logger.info(
                        "smart_chart_meteorology_success",
                        generated_chart_count=len(charts),
                        chart_types=[c.get("type") for c in charts],
                        data_id=data_id
                    )
                else:
                    logger.warning(
                        "smart_chart_meteorology_no_charts_generated",
                        reason="所有气象图表生成都失败了",
                        data_id=data_id
                    )

                return charts

            except Exception as e:
                logger.warning(
                    "meteorology_chart_group_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    data_id=data_id,
                    fallback="using generic method"
                )
                # 失败时回退到通用方法

        # 智能推荐多图组合（通用方法）
        recommended_combinations = self._get_recommended_chart_combinations(
            schema_type=schema_type,
            data=data,
            layout=layout,
            selected_pollutants=selected_pollutants,
            selected_stations=selected_stations
        )

        # 生成每个图表
        for chart_config in recommended_combinations:
            try:
                chart_type = chart_config["type"]
                title = chart_config.get("title")
                chart_options = chart_config.get("options", {})

                # 转换数据
                converted_data = self._convert_data_for_chart(
                    data=data,
                    schema_type=schema_type,
                    chart_type=chart_type,
                    options=chart_options,
                    selected_pollutants=selected_pollutants,
                    selected_stations=selected_stations
                )

                if "error" not in converted_data:
                    # 构建图表配置
                    chart_config_final = self._build_chart_config(
                        converted_data=converted_data,
                        title=title,
                        chart_type=chart_type,
                        original_data_id=data_id,
                        options=chart_options
                    )
                    charts.append(chart_config_final)
            except Exception as e:
                logger.warning(
                    "smart_chart_multi_chart_generation_failed",
                    chart_type=chart_config.get("type"),
                    error=str(e)
                )

        return charts

    def _get_recommended_chart_combinations(
        self,
        schema_type: str,
        data: Any,
        layout: str,
        selected_pollutants: Optional[List[str]],
        selected_stations: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """
        根据数据特征推荐多图组合

        Args:
            schema_type: 数据类型
            data: 数据
            layout: 布局
            selected_pollutants: 选中的污染物
            selected_stations: 选中的站点

        Returns:
            推荐的图表组合
        """
        combinations = []

        # 【新增】检测是否为多站点+多污染物场景（用于分面图）
        station_count = self._count_stations(data)
        pollutant_count = self._count_pollutants(data)
        time_count = self._count_time_points(data)
        is_multi_station_multi_pollutant = station_count >= 3 and pollutant_count >= 2 and time_count > 1

        logger.info(
            "facet_plot_detection",
            station_count=station_count,
            pollutant_count=pollutant_count,
            time_count=time_count,
            is_multi_station_multi_pollutant=is_multi_station_multi_pollutant
        )

        # 基于数据类型的智能推荐
        if schema_type in ["air_quality_unified", "guangdong_stations"]:
            # 【新增】分面图模式：多站点+多污染物场景
            if is_multi_station_multi_pollutant:
                # 生成分面图：每个污染物一个子图，避免线条过多
                logger.info(
                    "facet_plot_mode_enabled",
                    reason=f"检测到多站点({station_count}个)+多污染物({pollutant_count}个)数据，使用分面图展示",
                    station_count=station_count,
                    pollutant_count=pollutant_count
                )
                # 生成分面时序图配置
                combinations = [
                    {
                        "type": "facet_timeseries",
                        "title": "多站点污染物时序变化（分面图）",
                        "options": {
                            "show_legend": True,
                            "facet_by": "pollutant",  # 按污染物分面
                            "station_count": station_count,
                            "pollutant_count": pollutant_count
                        }
                    }
                ]
            # 常规多图组合
            elif layout == "main":
                combinations = [
                    {"type": "timeseries", "title": "污染物时序变化", "options": {"show_legend": True}},
                    {"type": "heatmap", "title": "站点污染物分布", "options": {}},
                    {"type": "radar", "title": "多站点综合评估", "options": {}}
                ]
            elif layout == "side":
                combinations = [
                    {"type": "bar", "title": "站点对比", "options": {}},
                    {"type": "pie", "title": "污染物占比", "options": {}}
                ]
            elif layout == "bottom":
                combinations = [
                    {"type": "timeseries", "title": "时间趋势", "options": {}}
                ]
            else:
                # 默认布局
                combinations = [
                    {"type": "timeseries", "title": "污染物时序变化", "options": {"show_legend": True}}
                ]

        elif schema_type in ["regional_city_comparison", "regional_station_comparison"]:
            # 区域对比数据也支持分面图
            if is_multi_station_multi_pollutant:
                logger.info(
                    "facet_plot_mode_enabled_for_regional",
                    reason=f"区域对比数据检测到多站点({station_count}个)+多污染物({pollutant_count}个)，使用分面图",
                    station_count=station_count,
                    pollutant_count=pollutant_count
                )
                combinations = [
                    {
                        "type": "facet_timeseries",
                        "title": "区域污染物时序变化（分面图）",
                        "options": {
                            "show_legend": True,
                            "facet_by": "pollutant",
                            "station_count": station_count,
                            "pollutant_count": pollutant_count
                        }
                    }
                ]
            else:
                combinations = [
                    {"type": "timeseries", "title": "区域污染物时序变化", "options": {"show_legend": True}}
                ]

        elif schema_type in ["weather", "meteorology", "meteorology_unified"]:
            # 气象数据的专业分组图表（v2.3优化）
            # 注意：实际由MeteorologyChartConverter.convert_to_chart_group()生成2张图表：
            # 1. weather_timeseries - 气象要素时序图（温度、湿度、风速、降水、云量+风向指针）
            # 2. pressure_pbl_timeseries - 气压+边界层高度合并图（双Y轴）
            combinations = [
                {"type": "weather_timeseries", "title": "气象要素时序变化（含风向）", "options": {
                    "show_elements": ["wind_speed", "temperature", "humidity"]
                }, "layout_hint": "wide"},
                {"type": "pressure_pbl_timeseries", "title": "气压与边界层高度变化", "options": {
                    "show_elements": ["pressure", "boundaryLayerHeight"]
                }, "layout_hint": "wide"}
            ]

        elif schema_type == "pmf_result":
            # PMF结果的多图组合
            combinations = [
                {"type": "pie", "title": "污染源贡献", "options": {}},
                {"type": "bar", "title": "源贡献排名", "options": {"top_n": 10}},
                {"type": "timeseries", "title": "源贡献变化", "options": {}}
            ]

        elif schema_type == "obm_ofp_result":
            # OBM结果的多图组合
            combinations = [
                {"type": "bar", "title": "VOC物种OFP值", "options": {"top_n": 15}},
                {"type": "radar", "title": "多物种评估", "options": {}}
            ]

        else:
            # 通用多图组合
            combinations = [
                {"type": "timeseries", "title": "时序分析", "options": {}},
                {"type": "bar", "title": "分类对比", "options": {}}
            ]

        return combinations

    def _create_visual_block(
        self,
        chart_config: Dict[str, Any],
        index: int,
        source_data_id: str,
        generator: str,
        layout_hint: str,
        schema_type: str = None
    ) -> Any:
        """创建VisualBlock对象"""
        from app.schemas.unified import VisualBlock
        from datetime import datetime

        # 推断expert_source用于前端大屏分类
        expert_source = self._infer_expert_source(schema_type or "", source_data_id)

        # 【关键修复】确保chart_config.meta中包含source_data_id和expert信息
        if "meta" not in chart_config:
            chart_config["meta"] = {}
        chart_config["meta"]["source_data_id"] = source_data_id
        chart_config["meta"]["data_id"] = source_data_id
        chart_config["meta"]["expert"] = expert_source
        chart_config["meta"]["generator"] = generator
        
        # 【关键修复】统一ID格式：只使用简洁格式，避免完整的data_id格式
        # 从chart_config中提取简洁ID，如果没有则生成一个
        chart_simple_id = chart_config.get('id', '')
        if not chart_simple_id or ':' in chart_simple_id:
            # 如果ID为空或包含":"（完整data_id格式），生成简洁ID
            # 格式：chart_{index}_{类型}_{短hash}
            short_hash = uuid.uuid4().hex[:8]
            chart_type_short = chart_config.get('type', 'chart')[:10]  # 限制长度
            chart_simple_id = f"chart_{index}_{chart_type_short}_{short_hash}"
            logger.debug(
                "chart_id_generated",
                original_id=chart_config.get('id'),
                generated_id=chart_simple_id,
                chart_index=index,
                chart_type=chart_config.get('type')
            )

        visual_block = VisualBlock(
            id=chart_simple_id,
            type="chart",
            schema="chart_config",
            payload=chart_config,
            meta={
                "schema_version": "v2.0",
                "generator": generator,
                "source_data_id": source_data_id,  # 【新增】单个source_data_id
                "source_data_ids": [source_data_id],
                "original_data_ids": [source_data_id],
                "expert": expert_source,  # 【新增】expert字段，用于报告导出分类
                "expert_source": expert_source,  # 数据来源专家类型
                "data_source": schema_type,  # 原始数据类型
                "scenario": f"multi_chart_{layout_hint}",
                "interaction_group": "chart_interaction",
                "data_flow": ["source_data", "chart_config"],
                "layout_hint": layout_hint,
                "timestamp": datetime.now().isoformat(),
                "chart_index": index
            }
        )

        return visual_block

    def _recommend_chart_type(
        self,
        schema_type: str,
        data: Any,
        selected_pollutants: Optional[List[str]] = None
    ) -> str:
        """
        智能推荐图表类型

        Args:
            schema_type: 数据schema类型
            data: 实际数据
            selected_pollutants: 选定的污染物列表（可选）

        Returns:
            推荐的图表类型
        """
        # 基于数据类型推荐
        if schema_type == "pmf_result":
            return "pie"  # PMF结果适合饼图
        elif schema_type == "obm_ofp_result":
            # OBM结果：如果指定了多个污染物，使用柱状图；否则使用饼图
            if selected_pollutants and len(selected_pollutants) > 1:
                logger.info(
                    "smart_chart_obm_multi_pollutant_recommended",
                    reason=f"用户指定了多个污染物对比({len(selected_pollutants)}个)，推荐柱状图",
                    selected_pollutants=selected_pollutants
                )
                return "bar"
            return "bar"  # OBM结果默认使用柱状图
        elif schema_type == "vocs_unified":
            return "timeseries"  # VOCs统一数据适合时序图
        elif schema_type == "vocs":
            return "pie"  # VOCs数据适合饼图
        elif schema_type in ["particulate", "particulate_unified", "carbon_analysis"]:
            # 检测是否为碳组分数据（包含SOC、POC、EC字段）
            if self._check_data_has_fields(data, ["SOC", "POC", "EC"]):
                logger.info(
                    "smart_chart_carbon_stacked_bar_recommended",
                    reason="检测到碳组分字段（SOC, POC, EC），推荐碳组分堆积图",
                    schema_type=schema_type
                )
                return "carbon_stacked_bar"
            # 检测是否有PM2.5字段，有则推荐堆叠时序图（双Y轴：左侧离子堆叠，右侧PM2.5曲线）
            elif self._check_data_has_fields(data, ["PM2_5", "PM2.5"]):
                logger.info(
                    "smart_chart_particulate_stacked_timeseries_recommended",
                    reason="检测到PM2.5字段，推荐堆叠时序图（双Y轴：左侧离子堆叠，右侧PM2.5曲线）",
                    schema_type=schema_type
                )
                return "stacked_timeseries"
            return "stacked_timeseries"  # 默认使用堆叠时序图
        # ========================================
        # 气象数据智能推荐（新增气象专业图表检测）
        # ========================================
        elif schema_type in ["weather", "meteorology", "meteorology_unified", "current_weather", "weather_forecast",
                             "fire_hotspots", "dust_data", "satellite_data",
                             "guangdong_stations", "air_quality_unified",
                             "regional_city_comparison", "regional_station_comparison"]:

            # 【优化1】优先检测气象专业图表类型（基于字段特征）

            # 检测1: 带风向指针的气象时序图 - 需要风速+风向字段
            if self._check_data_has_fields(data, ["wind_speed", "wind_direction",
                                                    "wind_speed_10m", "wind_direction_10m",
                                                    "windSpeed", "windDirection"]):
                logger.info(
                    "smart_chart_weather_timeseries_recommended",
                    reason="检测到风向风速字段，推荐带风向指针的时序图展示风场特征",
                    schema_type=schema_type
                )
                return "weather_timeseries"

            # 检测2: 边界层廓线图 - 需要高度字段
            elif self._check_data_has_fields(data, ["altitude", "height", "boundary_layer_height"]):
                logger.info(
                    "smart_chart_profile_recommended",
                    reason="检测到高度字段，推荐边界层廓线图展示垂直结构",
                    schema_type=schema_type
                )
                return "profile"

            # 检测3: 热力图 - 需要经纬度+数值字段（火点、沙尘等空间密度数据）
            elif (self._check_data_has_fields(data, ["latitude", "longitude", "lat", "lon"]) and
                  (schema_type in ["fire_hotspots", "dust_data", "satellite_data"] or
                   self._check_data_has_fields(data, ["brightness", "aod", "concentration", "value"]))):
                logger.info(
                    "smart_chart_heatmap_recommended",
                    reason="检测到经纬度+数值字段，推荐热力图展示空间强度分布",
                    schema_type=schema_type
                )
                return "heatmap"

            # 检测4: 地图 - 仅需要经纬度字段（站点分布、位置展示）
            # 注意：排除气象数据和空气质量数据类型，这些数据更适合时序图
            elif (self._check_data_has_fields(data, ["latitude", "longitude", "lat", "lon"]) and
                  schema_type not in ["meteorology", "meteorology_unified", "weather", "weather_unified",
                                       "air_quality", "air_quality_unified", "guangdong_stations",
                                       "regional_city_comparison", "regional_station_comparison"]):
                logger.info(
                    "smart_chart_map_recommended",
                    reason="检测到经纬度字段，推荐地图展示空间分布",
                    schema_type=schema_type
                )
                return "map"

            # 【兜底】如果未检测到专业图表特征，使用时间序列分析
            # Step 1: 检查时间维度和污染物数量
            time_count = self._count_time_points(data)
            pollutant_count = self._count_pollutants(data)
            has_time_field = time_count > 0

            logger.info(
                "smart_chart_air_quality_analysis",
                time_count=time_count,
                pollutant_count=pollutant_count,
                selected_pollutants=selected_pollutants,
                schema_type=schema_type
            )

            # Step 2: 多污染物 + 多时间点 → 默认timeseries
            if has_time_field and time_count > 1 and pollutant_count > 1:
                # 默认：多污染物时序图（多条线）
                logger.info(
                    "smart_chart_multi_pollutant_timeseries_recommended",
                    reason=f"多污染物({pollutant_count}个)多时间点({time_count}个)，推荐多条时序线图表（默认显示所有污染物）",
                    selected_pollutants=selected_pollutants
                )
                return "timeseries"

            # Step 3: 单污染物 + 多时间点 → 时序图
            elif has_time_field and time_count > 1:
                logger.info(
                    "smart_chart_single_pollutant_timeseries_recommended",
                    reason=f"数据包含{time_count}个时间点，推荐时序图"
                )
                return "timeseries"

            # Step 4: 单时间点 → 柱状图（对比不同站点/城市）
            elif has_time_field and time_count == 1:
                logger.info(
                    "smart_chart_bar_single_time_recommended",
                    reason="数据只包含1个时间点，推荐柱状图对比不同站点（默认显示所有污染物）",
                    selected_pollutants=selected_pollutants
                )
                return "bar"

            # Step 5: 无时间字段 → 柱状图
            else:
                logger.info(
                    "smart_chart_bar_no_time_recommended",
                    reason="数据不包含时间字段，推荐柱状图对比不同站点（默认显示所有污染物）",
                    selected_pollutants=selected_pollutants
                )
                return "bar"
        else:
            return "auto"  # 通用数据类型，交给转换器处理

    def _check_data_has_time_field(self, data: Any) -> bool:
        """
        检查数据是否包含时间字段

        Args:
            data: 要检查的数据

        Returns:
            如果包含时间字段返回True，否则返回False
        """
        if not data:
            return False

        # 如果是列表，检查第一个元素
        if isinstance(data, list):
            if not data:
                return False
            first_item = data[0]
            if isinstance(first_item, dict):
                # 检查是否包含常见的时间字段名
                time_fields = [
                    "time_point", "timePoint", "timestamp", "time",
                    "DataTime", "dataTime", "date", "Date",
                    "datetime", "DateTime"
                ]
                return any(field in first_item for field in time_fields)
            return False

        # 如果是字典，直接检查
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                # UDF v1.0格式，检查嵌套的data字段
                return self._check_data_has_time_field(data["data"])

            time_fields = [
                "time_point", "timePoint", "timestamp", "time",
                "DataTime", "dataTime", "date", "Date",
                "datetime", "DateTime"
            ]
            return any(field in data for field in time_fields)

        return False

    def _count_time_points(self, data: Any) -> int:
        """
        统计时间点的数量

        Args:
            data: 要统计的数据

        Returns:
            时间点数量（去重后）
        """
        if not data:
            return 0

        time_points = set()

        # 如果是列表，遍历所有元素
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # 检查常见的时间字段名
                    time_fields = [
                        "timestamp", "time", "datetime", "time_point", "timePoint",
                        "DataTime", "dataTime", "date", "Date"
                    ]
                    for field in time_fields:
                        if field in item and item[field]:
                            time_points.add(str(item[field]))
        # 如果是字典，检查字典本身
        elif isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                # UDF v1.0格式，递归检查嵌套的data字段
                return self._count_time_points(data["data"])

            time_fields = [
                "timestamp", "time", "datetime", "time_point", "timePoint",
                "DataTime", "dataTime", "date", "Date"
            ]
            for field in time_fields:
                if field in data and data[field]:
                    time_points.add(str(data[field]))

        return len(time_points)

    def _count_pollutants(self, data: Any) -> int:
        """
        统计污染物的数量

        Args:
            data: 要统计的数据

        Returns:
            污染物数量
        """
        if not data:
            return 0

        pollutants = set()

        # 如果是列表，检查第一个元素的measurements
        if isinstance(data, list):
            if not data:
                return 0
            first_item = data[0]
            if isinstance(first_item, dict):
                # 检查measurements字段
                measurements = first_item.get("measurements", {})
                if measurements:
                    # 使用全局data_standardizer进行字段标准化
                    from app.utils.data_standardizer import get_data_standardizer
                    standardizer = get_data_standardizer()

                    # 统计measurements中的污染物
                    for key in measurements.keys():
                        # 尝试将字段名标准化
                        standard_key = standardizer._get_standard_field_name(key)
                        # 如果找到标准映射，使用标准字段名
                        if standard_key:
                            pollutants.add(standard_key)
                        # 如果未找到标准映射，但字段名可能是污染物，也保留原始字段名
                        else:
                            # 简单判断：如果包含常见污染物关键字，也加入
                            key_upper = key.upper().replace("_", "").replace(".", "")
                            if any(key_upper in p.upper().replace("_", "").replace(".", "") or
                                   p.upper().replace("_", "").replace(".", "") in key_upper
                                   for p in ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "AQI", "O3_8h"]):
                                pollutants.add(key)
                else:
                    # 直接检查污染物字段，使用全局data_standardizer进行标准化
                    from app.utils.data_standardizer import get_data_standardizer
                    standardizer = get_data_standardizer()

                    # 对所有字段进行标准化检查
                    for field in first_item.keys():
                        standard_key = standardizer._get_standard_field_name(field)
                        # 如果是标准污染物字段，加入集合
                        if standard_key and any(std_pollutant in standard_key
                                              for std_pollutant in ["PM2_5", "PM10", "O3", "O3_8h", "NO2", "SO2", "CO", "AQI"]):
                            pollutants.add(standard_key)
                        # 如果不是标准字段，但字段名包含污染物关键字，也加入
                        elif field in ["臭氧", "臭氧(O3)", "臭氧(O₃)", "臭氧8小时", "O3_8h", "细颗粒物", "PM2.5", "PM10", "二氧化硫", "二氧化氮", "一氧化碳", "PM2.5浓度", "PM10浓度"]:
                            pollutants.add(field)

        # 如果是字典，检查嵌套的data字段
        elif isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return self._count_pollutants(data["data"])

        return len(pollutants)

    def _count_stations(self, data: Any) -> int:
        """
        统计站点/城市的数量

        Args:
            data: 要统计的数据

        Returns:
            站点/城市数量
        """
        if not data:
            return 0

        stations = set()

        # 如果是列表，遍历所有元素
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    # 检查常见的站点/城市字段名
                    station_fields = [
                        "station_name", "stationName", "city", "City",
                        "location", "Location", "station", "Station",
                        "site", "Site", "province", "Province"
                    ]
                    for field in station_fields:
                        if field in item and item[field]:
                            stations.add(str(item[field]))
                            break  # 找到一个站点字段就跳出，避免重复计数

        # 如果是字典，检查嵌套的data字段
        elif isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return self._count_stations(data["data"])

        return len(stations)

    def _infer_pollutants_from_metadata(self, metadata: Optional[Dict[str, Any]]) -> Optional[List[str]]:
        """
        根据数据元信息推断目标污染物。

        区域对比查询都会在metadata中写入pollutant/pollutants字段，
        这里读取后统一转换为标准字段名称供chart converter使用。
        """
        if not metadata:
            return None

        candidate_keys = ["pollutant", "pollutants", "target_pollutant", "target_pollutants", "selected_pollutants"]
        raw_values: List[str] = []

        for key in candidate_keys:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                raw_values.append(value)
                break
            if isinstance(value, list) and value:
                raw_values.extend([str(item) for item in value if item])
                break

        normalized = []
        for value in raw_values:
            normalized_value = self._normalize_pollutant_identifier(value)
            if normalized_value:
                normalized.append(normalized_value)

        return normalized or None

    def _normalize_pollutant_identifier(self, pollutant: str) -> Optional[str]:
        """
        将各种命名（中英文、带单位）统一成系统支持的字段名。
        """
        if not pollutant:
            return None

        cleaned = (
            pollutant.strip()
            .replace("（", "(")
            .replace("）", ")")
            .replace("，", ",")
        )
        cleaned_upper = cleaned.upper().replace(" ", "")

        mapping = {
            "PM2.5": "PM2_5",
            "PM2_5": "PM2_5",
            "PM25": "PM2_5",
            "PM10": "PM10",
            "O3": "O3",
            "O₃": "O3",
            "臭氧": "O3",
            "O3_8H": "O3_8h",
            "O3_8h": "O3_8h",
            "O38H": "O3_8h",
            "O38h": "O3_8h",
            "臭氧8小时": "O3_8h",
            "臭氧8小时平均": "O3_8h",
            "NO2": "NO2",
            "二氧化氮": "NO2",
            "SO2": "SO2",
            "二氧化硫": "SO2",
            "CO": "CO",
            "一氧化碳": "CO",
            "AQI": "AQI"
        }

        if cleaned_upper in mapping:
            return mapping[cleaned_upper]

        # fallback：兼容带括号的写法，例如 "O3(8H)"
        if cleaned_upper.startswith("PM2") and "5" in cleaned_upper:
            return "PM2_5"
        if cleaned_upper.startswith("PM10"):
            return "PM10"
        # O3_8h 优先于 O3 匹配
        if "8H" in cleaned_upper or "8H" in cleaned_upper or "_8H" in cleaned_upper or "_8h" in cleaned_upper:
            return "O3_8h"
        if cleaned_upper.startswith("O3"):
            return "O3"
        if cleaned_upper.startswith("NO2"):
            return "NO2"
        if cleaned_upper.startswith("SO2"):
            return "SO2"
        if cleaned_upper.startswith("CO"):
            return "CO"
        if "AQI" in cleaned_upper:
            return "AQI"

        return None

    def _convert_data_for_chart(
        self,
        data: Any,
        schema_type: str,
        chart_type: str,
        options: Dict[str, Any],
        selected_pollutants: Optional[List[str]] = None,
        selected_stations: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        转换数据为图表格式

        Args:
            data: 原始数据
            schema_type: 数据schema类型
            chart_type: 图表类型
            options: 额外选项
            selected_pollutants: 选定的污染物列表（可选）
            selected_stations: 选定的站点/城市列表（可选）

        Returns:
            转换后的图表数据
        """
        # 将schema_type映射为data_type
        data_type = schema_type
        if schema_type == "vocs_unified":
            data_type = "vocs_unified"

        # 清理options，避免参数重复传递
        # 如果selected_pollutants和selected_stations已经显式传递，从options中移除
        cleaned_options = {k: v for k, v in options.items()
                          if k not in ['selected_pollutants', 'selected_stations']}

        # 【修复】只有当参数不为None时才显式传递，否则让convert_chart_data使用默认值
        kwargs_to_pass = cleaned_options.copy()
        # 传递schema_type用于下游细化标题/元数据
        kwargs_to_pass['schema_type'] = schema_type
        if selected_pollutants is not None:
            kwargs_to_pass['selected_pollutants'] = selected_pollutants
        if selected_stations is not None:
            kwargs_to_pass['selected_stations'] = selected_stations

        # 使用统一的转换器
        return convert_chart_data(
            data=data,
            data_type=data_type,
            chart_type=chart_type,
            **kwargs_to_pass
        )

    def _build_chart_config(
        self,
        converted_data: Dict[str, Any],
        title: Optional[str],
        chart_type: str,
        original_data_id: str,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """构建最终的图表配置"""
        # 添加元数据
        if "meta" not in converted_data:
            converted_data["meta"] = {}

        converted_data["meta"].update({
            "data_source": "smart_chart_generator",
            "original_data_id": original_data_id,
            "generated_with_options": options
        })

        # 设置标题（用户传入的title优先级最高）
        if title:
            converted_data["title"] = title
        elif "title" not in converted_data:
            converted_data["title"] = "图表"

        return converted_data

    def _build_summary(
        self,
        final_chart: Dict[str, Any],
        source_data_id: str,
        schema_type: str,
        chart_type: str,
        options: Dict[str, Any]
    ) -> str:
        """构建详细摘要"""
        summary_parts = [
            "✅ 智能图表生成完成\n",
            f"📊 **图表类型**: {chart_type}\n",
            f"📋 **数据来源**: {schema_type}\n",
            f"💾 **原始数据ID**: `{source_data_id}`\n"
        ]

        # 添加图表信息
        if final_chart.get("title"):
            summary_parts.append(f"🎯 **图表标题**: {final_chart['title']}\n")

        # 添加数据信息
        meta = final_chart.get("meta", {})
        if meta.get("unit"):
            summary_parts.append(f"📏 **数据单位**: {meta['unit']}\n")

        if meta.get("record_count"):
            summary_parts.append(f"📈 **数据记录数**: {meta['record_count']}\n")

        # 添加选项信息
        if options:
            summary_parts.append("⚙️ **生成选项**:\n")
            for key, value in options.items():
                summary_parts.append(f"   - {key}: {value}\n")

        return "".join(summary_parts)

    def _normalize_chart_type(self, chart_type: str) -> str:
        """
        标准化图表类型名称，自动纠正常见错误

        Args:
            chart_type: 原始图表类型名称

        Returns:
            标准化后的图表类型名称
        """
        # 首先清理输入（去除空格、换行符，转换为小写）
        chart_type = chart_type.strip().lower()

        # 常见错误映射
        type_mapping = {
            "time_series": "timeseries",
            "time-series": "timeseries",
            "timeseries_chart": "timeseries",
            "line_chart": "line",
            "bar_chart": "bar",
            "pie_chart": "pie"
        }

        normalized = type_mapping.get(chart_type, chart_type)
        if normalized != chart_type:
            logger.info(
                "smart_chart_type_normalized",
                original=chart_type,
                normalized=normalized
            )

        return normalized

    def _validate_chart_type_compatibility(
        self,
        schema_type: str,
        chart_type: str,
        data: Any
    ) -> Dict[str, Any]:
        """
        验证chart_type与schema_type的兼容性，并提供降级建议

        Args:
            schema_type: 数据schema类型
            chart_type: 请求的图表类型
            data: 实际数据（用于检测字段特征）

        Returns:
            包含兼容性结果的字典：
            {
                "compatible": bool,
                "reason": str (如果不兼容),
                "fallback": str (降级建议的图表类型),
                "available_types": List[str] (可用的图表类型列表)
            }
        """
        # 定义各schema_type的兼容图表类型
        compatibility_map = {
            "pmf_result": {
                "compatible": ["pie", "bar", "timeseries", "line"],
                "default_fallback": "pie"
            },
            "obm_ofp_result": {
                "compatible": ["pie", "bar", "radar"],
                "default_fallback": "bar"
            },
            "vocs_unified": {
                "compatible": ["pie", "bar", "timeseries", "line"],
                "default_fallback": "timeseries"
            },
            "vocs": {
                "compatible": ["pie", "bar", "timeseries", "line"],
                "default_fallback": "pie"
            },
            "particulate": {
                "compatible": ["pie", "bar", "timeseries", "line", "carbon_stacked_bar", "stacked_timeseries"],
                "default_fallback": "stacked_timeseries",
                "conditional": {
                    "carbon_stacked_bar": ["SOC", "POC", "EC"],
                    "stacked_timeseries": ["PM2_5", "PM2.5"]
                }
            },
            "particulate_unified": {
                "compatible": ["pie", "bar", "timeseries", "line", "carbon_stacked_bar", "stacked_timeseries"],
                "default_fallback": "stacked_timeseries",
                "conditional": {
                    "carbon_stacked_bar": ["SOC", "POC", "EC"],
                    "stacked_timeseries": ["PM2_5", "PM2.5"]
                }
            },
            # 碳组分分析专用schema（新增）
            "carbon_analysis": {
                "compatible": ["carbon_stacked_bar", "bar", "timeseries"],
                "default_fallback": "carbon_stacked_bar",
                "conditional": {
                    "carbon_stacked_bar": ["SOC", "POC", "EC"]
                }
            },
            "guangdong_stations": {
                "compatible": ["bar", "timeseries", "line", "pie", "facet_timeseries"],
                "default_fallback": "bar"
            },
            "air_quality_unified": {
                "compatible": ["bar", "timeseries", "line", "pie", "facet_timeseries"],
                "default_fallback": "bar"
            },
            "regional_city_comparison": {
                "compatible": ["timeseries", "line", "bar", "facet_timeseries"],
                "default_fallback": "timeseries"
            },
            "regional_station_comparison": {
                "compatible": ["timeseries", "line", "bar", "facet_timeseries"],
                "default_fallback": "timeseries"
            },
            "weather": {
                "compatible": ["weather_timeseries", "wind_rose", "profile", "timeseries", "line", "bar"],
                "default_fallback": "weather_timeseries",
                "conditional": {
                    "weather_timeseries": ["wind_speed", "wind_direction", "windSpeed", "windDirection", "wind_speed_10m", "wind_direction_10m"],
                    "wind_rose": ["wind_speed", "wind_direction", "windSpeed", "windDirection", "wind_speed_10m", "wind_direction_10m"],
                    "profile": ["altitude", "height"]
                }
            },
            "meteorology": {
                "compatible": ["weather_timeseries", "wind_rose", "profile", "timeseries", "line", "bar"],
                "default_fallback": "weather_timeseries",
                "conditional": {
                    "weather_timeseries": ["wind_speed", "wind_direction", "windSpeed", "windDirection", "wind_speed_10m", "wind_direction_10m"],
                    "wind_rose": ["wind_speed", "wind_direction", "windSpeed", "windDirection", "wind_speed_10m", "wind_direction_10m"],
                    "profile": ["altitude", "height"]
                }
            },
            "meteorology_unified": {
                "compatible": ["weather_timeseries", "wind_rose", "profile", "timeseries", "line", "bar"],
                "default_fallback": "weather_timeseries",
                "conditional": {
                    "weather_timeseries": ["wind_speed", "wind_direction", "wind_speed_10m", "wind_direction_10m"],
                    "wind_rose": ["wind_speed", "wind_direction", "wind_speed_10m", "wind_direction_10m"],
                    "profile": ["altitude", "height"]
                }
            }
        }

        # 获取该schema_type的兼容性配置
        schema_config = compatibility_map.get(schema_type)

        # 如果schema_type未定义兼容性规则，允许所有图表类型（宽容模式）
        if not schema_config:
            logger.info(
                "smart_chart_compatibility_check_skipped",
                schema_type=schema_type,
                reason="未定义兼容性规则，允许所有图表类型"
            )
            return {
                "compatible": True,
                "reason": None,
                "fallback": None,
                "available_types": []
            }

        compatible_types = schema_config["compatible"]

        # 检查基础兼容性
        if chart_type not in compatible_types:
            # 不兼容，提供降级建议
            fallback = self._recommend_chart_type(schema_type, data, False)
            return {
                "compatible": False,
                "reason": f"图表类型'{chart_type}'不适用于'{schema_type}'数据类型",
                "fallback": fallback,
                "available_types": compatible_types
            }

        # 检查条件性兼容性（例如wind_rose需要wind_speed+wind_direction字段）
        if "conditional" in schema_config and chart_type in schema_config["conditional"]:
            required_fields = schema_config["conditional"][chart_type]

            # 检查数据是否包含必需字段
            has_required_fields = self._check_data_has_fields(data, required_fields)

            if not has_required_fields:
                # 条件性不兼容，降级
                fallback = schema_config["default_fallback"]
                return {
                    "compatible": False,
                    "reason": f"图表类型'{chart_type}'需要数据包含{required_fields}字段，但当前数据不满足条件",
                    "fallback": fallback,
                    "available_types": compatible_types
                }

        # 兼容
        return {
            "compatible": True,
            "reason": None,
            "fallback": None,
            "available_types": compatible_types
        }

    def _check_data_has_fields(self, data: Any, field_names: List[str]) -> bool:
        """
        检查数据是否包含指定字段（使用data_standardizer进行字段标准化）

        统一使用data_standardizer.py进行字段映射，避免出现字段不匹配的问题

        Args:
            data: 要检查的数据
            field_names: 字段名列表（任一存在即可）

        Returns:
            如果包含任一字段返回True，否则返回False
        """
        if not data or not field_names:
            return False

        # 使用全局data_standardizer进行字段标准化
        from app.utils.data_standardizer import get_data_standardizer
        standardizer = get_data_standardizer()

        # 如果是列表，检查第一个元素
        if isinstance(data, list):
            if not data:
                return False
            first_item = data[0]
            if isinstance(first_item, dict):
                # 检查是否包含任一字段（使用data_standardizer标准化后比较）
                for field in field_names:
                    # 检查原始字段名
                    if field in first_item:
                        return True
                    # 检查data_standardizer映射后的字段
                    for key in first_item.keys():
                        mapped_name = standardizer._get_standard_field_name(key)
                        if mapped_name == field:
                            return True
                return False
            return False

        # 如果是字典，检查字典本身
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                # UDF v1.0格式，检查嵌套的data字段
                return self._check_data_has_fields(data["data"], field_names)

            # 检查顶层字段（使用data_standardizer标准化后比较）
            for field in field_names:
                # 检查原始字段名
                if field in data:
                    return True
                # 检查data_standardizer映射后的字段
                for key in data.keys():
                    mapped_name = standardizer._get_standard_field_name(key)
                    if mapped_name == field:
                        return True

        return False

    def _analyze_chart_data_validity(
        self,
        chart_dict: Dict[str, Any],
        original_data: Any
    ) -> Dict[str, Any]:
        """
        分析图表数据的有效性（用于LLM观测）

        检查图表生成过程中的数据质量，包括：
        - 数据点数量
        - null值比例
        - 数据结构正确性
        - 异常情况识别
        - 改进建议

        Args:
            chart_dict: 生成的图表配置
            original_data: 原始输入数据

        Returns:
            数据有效性分析结果
        """
        analysis_result = {
            "is_valid": True,
            "issue": "none",
            "data_point_count": 0,
            "null_count": 0,
            "null_percentage": 0.0,
            "structure": "unknown",
            "recommendation": ""
        }

        try:
            chart_type = chart_dict.get("type")
            chart_data = chart_dict.get("data")

            # 【修复】支持嵌套数据结构（如 chart.data.data）
            if isinstance(chart_data, dict) and "data" in chart_data:
                actual_chart_data = chart_data["data"]
                analysis_result["data_structure"] = "nested"
            else:
                actual_chart_data = chart_data
                analysis_result["data_structure"] = "direct"

            if not actual_chart_data:
                analysis_result.update({
                    "is_valid": False,
                    "issue": "empty_chart_data",
                    "recommendation": "图表数据为空，请检查输入数据"
                })
                return analysis_result

            # 根据图表类型分析数据
            if chart_type == "timeseries":
                analysis_result["structure"] = "timeseries"
                if isinstance(actual_chart_data, dict):
                    series_data = actual_chart_data.get("series", [])
                    x_data = actual_chart_data.get("x", [])

                    total_points = 0
                    null_points = 0

                    for series in series_data:
                        if isinstance(series, dict) and "data" in series:
                            data_list = series["data"]
                            total_points += len(data_list)
                            null_points += sum(1 for point in data_list if point is None)

                    analysis_result.update({
                        "data_point_count": total_points,
                        "null_count": null_points,
                        "null_percentage": round(null_points / total_points * 100, 2) if total_points > 0 else 0.0,
                        "series_count": len(series_data),
                        "time_points": len(x_data)
                    })

                    # 检查数据质量问题
                    if total_points == 0:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "no_data_points",
                            "recommendation": "时序数据为空，请检查原始数据"
                        })
                    elif null_points / total_points > 0.8 if total_points > 0 else True:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "excessive_null_values",
                            "recommendation": f"超过80%的数据点为null（{analysis_result['null_percentage']:.1f}%），可能数据源问题"
                        })
                    elif null_points / total_points > 0.5 if total_points > 0 else False:
                        analysis_result.update({
                            "is_valid": True,
                            "issue": "high_null_ratio",
                            "recommendation": f"约{analysis_result['null_percentage']:.1f}%的数据点为null，请确认数据完整性"
                        })

            elif chart_type in ["bar", "line"]:
                analysis_result["structure"] = "xy_data"
                if isinstance(actual_chart_data, dict):
                    x_data = actual_chart_data.get("x", [])

                    # 支持两种数据格式（符合 Chart v3.1 规范）：
                    # 1. 单序列格式：{"x": [], "y": []}
                    # 2. 多序列格式：{"x": [], "series": [{"name": "...", "data": [...]}]}
                    if "series" in actual_chart_data:
                        # 多序列格式（时序图常用）
                        series_list = actual_chart_data.get("series", [])
                        total_points = 0
                        null_points = 0

                        for series in series_list:
                            if isinstance(series, dict) and "data" in series:
                                data_list = series["data"]
                                total_points += len(data_list)
                                null_points += sum(1 for point in data_list if point is None)

                        analysis_result.update({
                            "data_point_count": total_points,
                            "null_count": null_points,
                            "null_percentage": round(null_points / total_points * 100, 2) if total_points > 0 else 0.0,
                            "series_count": len(series_list),
                            "time_points": len(x_data)
                        })

                        # 检查数据质量问题
                        if total_points == 0:
                            analysis_result.update({
                                "is_valid": False,
                                "issue": "no_data_points",
                                "recommendation": "时序数据为空，请检查原始数据"
                            })
                        elif null_points / total_points > 0.8 if total_points > 0 else True:
                            analysis_result.update({
                                "is_valid": False,
                                "issue": "excessive_null_values",
                                "recommendation": f"超过80%的数据点为null（{analysis_result['null_percentage']:.1f}%），可能数据源问题"
                            })
                        elif null_points / total_points > 0.5 if total_points > 0 else False:
                            analysis_result.update({
                                "is_valid": True,
                                "issue": "high_null_ratio",
                                "recommendation": f"约{analysis_result['null_percentage']:.1f}%的数据点为null，请确认数据完整性"
                            })
                    else:
                        # 单序列格式
                        y_data = actual_chart_data.get("y", [])
                        null_y = sum(1 for y in y_data if y is None) if y_data else 0

                        analysis_result.update({
                            "data_point_count": len(y_data),
                            "null_count": null_y,
                            "null_percentage": round(null_y / len(y_data) * 100, 2) if y_data else 0.0
                        })

                        if len(y_data) == 0:
                            analysis_result.update({
                                "is_valid": False,
                                "issue": "no_y_data",
                                "recommendation": "Y轴数据为空，请检查输入数据"
                            })
                        elif null_y == len(y_data):
                            analysis_result.update({
                                "is_valid": False,
                                "issue": "all_null_y_values",
                                "recommendation": "所有Y轴值都为null，可能数据源问题"
                            })

            elif chart_type == "pie":
                analysis_result["structure"] = "pie_data"
                if isinstance(actual_chart_data, list):
                    null_values = sum(1 for item in actual_chart_data if not isinstance(item, dict) or item.get("value") is None)
                    analysis_result.update({
                        "data_point_count": len(actual_chart_data),
                        "null_count": null_values,
                        "null_percentage": round(null_values / len(actual_chart_data) * 100, 2) if actual_chart_data else 0.0
                    })

                    if len(actual_chart_data) == 0:
                        analysis_result.update({
                            "is_valid": False,
                            "issue": "empty_pie_data",
                            "recommendation": "饼图数据为空"
                        })

            else:
                # 其他图表类型
                analysis_result["structure"] = f"chart_type_{chart_type}"
                if isinstance(actual_chart_data, (dict, list)):
                    analysis_result["data_point_count"] = len(actual_chart_data) if isinstance(actual_chart_data, list) else 1

            # 原始数据检查
            if isinstance(original_data, list):
                original_count = len(original_data)
                analysis_result["raw_data_size"] = original_count

                if original_count == 0:
                    analysis_result.update({
                        "is_valid": False,
                        "issue": "empty_original_data",
                        "recommendation": "原始数据为空，无法生成有效图表"
                    })

        except Exception as e:
            logger.warning("data_analysis_failed", error=str(e))
            analysis_result.update({
                "is_valid": False,
                "issue": "analysis_error",
                "recommendation": f"数据分析失败: {str(e)}"
            })

        return analysis_result

    def _is_nimfa_only_result(self, raw_data: Any) -> bool:
        """
        检测PMF结果是否为NIMFA模式（无监督因子分解）

        关键逻辑：
        - 双模式结果：同时包含 nnls_result（有标签的源）和 nimfa_result（抽象因子）
          → 应该生成图表（使用NNLS的sources）
        - NIMFA-only结果：只有 nimfa_result，没有 nnls_result
          → 无法生成有意义的污染源图表，应该跳过

        NIMFA模式使用抽象因子名称（如"因子1"、"因子2"），无法生成有意义的污染源图表。
        NNLS模式使用预定义源谱库（有明确标签，如"机动车"、"燃煤"等），可以生成图表。

        Args:
            raw_data: PMF结果数据

        Returns:
            如果是NIMFA-only结果返回True，否则返回False
        """
        if not raw_data:
            return False

        try:
            if not isinstance(raw_data, dict):
                return False

            # 【关键修复】首先检查是否有 nnls_result
            # 如果有 nnls_result，说明是双模式，应该生成图表
            if "nnls_result" in raw_data:
                logger.info(
                    "detected_dual_mode_result",
                    has_nnls_result=True,
                    has_nimfa_result="nimfa_result" in raw_data,
                    reason="双模式结果包含nnls_result，应该生成图表"
                )
                return False  # 有 nnls_result，不跳过

            # 如果没有 nnls_result，但有 nimfa_result，才是 NIMFA-only
            if "nimfa_result" not in raw_data:
                # 既没有 nnls_result 也没有 nimfa_result，不是有效的 PMF 结果
                return False

            # 获取 nimfa_result 的 sources
            nimfa_result = raw_data.get("nimfa_result", {})
            sources = nimfa_result.get("sources", [])

            # 提取源名称
            source_names = []
            if sources:
                if isinstance(sources, list):
                    for source in sources:
                        if isinstance(source, dict):
                            name = source.get("source_name", "")
                        elif hasattr(source, 'source_name'):
                            name = source.source_name
                        else:
                            name = str(source)
                        if name:
                            source_names.append(name)
                elif isinstance(sources, dict):
                    source_names = list(sources.keys())

            # 检测是否为NIMFA模式
            # NIMFA因子命名格式: "因子1", "因子2", ... 或 Pattern: /^因子\d+$/
            import re
            nimfa_pattern = re.compile(r'^因子\d+$')

            # 如果所有源名称都匹配NIMFA模式，则是NIMFA-only结果
            if source_names:
                all_nimfa = all(nimfa_pattern.match(str(name)) for name in source_names)
                if all_nimfa:
                    logger.info(
                        "detected_nimfa_only_result",
                        source_names=source_names,
                        count=len(source_names)
                    )
                    return True

            return False

        except Exception as e:
            logger.warning(
                "nimfa_detection_failed",
                error=str(e),
                raw_data_type=type(raw_data).__name__
            )
            return False

    def _check_existing_visuals(self, raw_data: Any, schema_type: str) -> bool:
        """
        检查上游工具结果是否已包含visuals字段

        某些工具（如meteorological_trajectory_analysis）已内置可视化配置，
        此时应跳过smart_chart_generator，避免重复生成图表

        Args:
            raw_data: 原始数据
            schema_type: 数据schema类型

        Returns:
            如果已包含visuals返回True，否则返回False
        """
        if not raw_data:
            return False

        # 【新增】检测NIMFA模式结果，跳过图表生成
        # NIMFA模式使用抽象因子名称（如"因子1"、"因子2"），无法生成有意义的图表
        if schema_type == "pmf_result":
            if self._is_nimfa_only_result(raw_data):
                logger.info(
                    "skipping_pmf_chart_for_nimfa_result",
                    reason="检测到NIMFA模式结果（抽象因子名称），无法生成有意义的污染源图表，跳过smart_chart_generator",
                    schema_type=schema_type
                )
                return True  # 返回True表示跳过

        # 检查数据类型，根据schema_type决定检查策略
        if schema_type in ["trajectory_result", "trajectory_endpoints", "enterprise_analysis"]:
            # 这些类型的工具通常已内置visuals
            # trajectory_result: 轨迹分析已内置可视化
            # enterprise_analysis: 企业分析已内置可视化
            # pmf_result: calculate_pmf已直接生成PNG图片，无需再次生成ECharts
            logger.info(
                "checking_existing_visuals",
                schema_type=schema_type,
                has_visuals_hint=True
            )
            # 注意：这里返回False，因为需要实际检查数据内容
            # 实际的检查逻辑在下面

        # 直接检查raw_data是否包含visuals字段（通过metadata或其他方式）
        # 注意：raw_data可能是字典格式，需要多层检查

        # 场景1: 如果raw_data是字典且包含"visuals"字段
        if isinstance(raw_data, dict) and "visuals" in raw_data:
            visuals = raw_data["visuals"]
            if isinstance(visuals, list) and len(visuals) > 0:
                logger.info(
                    "detected_existing_visuals",
                    count=len(visuals),
                    visual_types=[v.get("type") for v in visuals if isinstance(v, dict)],
                    schema_type=schema_type
                )
                return True

        # 场景2: 如果raw_data是列表，检查第一个元素是否包含visuals相关信息
        if isinstance(raw_data, list) and len(raw_data) > 0:
            first_item = raw_data[0]
            if isinstance(first_item, dict):
                # 检查是否包含visuals字段
                if "visuals" in first_item:
                    visuals = first_item["visuals"]
                    if isinstance(visuals, list) and len(visuals) > 0:
                        logger.info(
                            "detected_existing_visuals_in_item",
                            count=len(visuals),
                            schema_type=schema_type
                        )
                        return True

                # 检查是否包含图表类型字段（轨迹数据等）
                if "trajectory_id" in first_item or "enterprise_name" in first_item:
                    # 这些是轨迹或企业分析的结果，很可能已包含可视化
                    logger.info(
                        "detected_trajectory_or_enterprise_data",
                        has_trajectory="trajectory_id" in first_item,
                        has_enterprise="enterprise_name" in first_item,
                        schema_type=schema_type
                    )
                    # 注意：对于这些类型，我们需要更深入的检查
                    # 但这里先返回False，让后续逻辑处理

        # 场景3: 检查raw_data是否包含完整的可视化配置（map_layers等）
        if isinstance(raw_data, dict):
            # 检查是否包含地图相关的可视化字段
            if any(key in raw_data for key in ["map_layers", "trajectories", "enterprises"]):
                logger.info(
                    "detected_visualization_related_fields",
                    fields=[k for k in raw_data.keys() if k in ["map_layers", "trajectories", "enterprises"]],
                    schema_type=schema_type
                )
                return True

        # 默认：未检测到visuals
        return False

    def _build_skipped_result(
        self,
        raw_data: Any,
        data_id: str,
        schema_type: str
    ) -> Dict[str, Any]:
        """
        构建跳过smart_chart_generator时的结果

        当上游工具已包含可视化配置时，smart_chart_generator应返回合适的跳过结果

        Args:
            raw_data: 原始数据（可能包含visuals）
            data_id: 数据ID
            schema_type: 数据schema类型

        Returns:
            跳过的结果（符合UDF v2.0格式）
        """
        # 尝试从raw_data中提取已有的visuals
        existing_visuals = []
        if isinstance(raw_data, dict) and "visuals" in raw_data:
            existing_visuals = raw_data["visuals"]
        elif isinstance(raw_data, list) and len(raw_data) > 0:
            first_item = raw_data[0]
            if isinstance(first_item, dict) and "visuals" in first_item:
                existing_visuals = first_item["visuals"]

        # 如果找到了visuals，返回这些visuals
        if existing_visuals:
            logger.info(
                "returning_existing_visuals",
                count=len(existing_visuals),
                data_id=data_id
            )
            return {
                "status": "success",
                "success": True,
                "data": None,  # v2.0格式使用visuals字段
                "visuals": existing_visuals,  # 返回已有的visuals
                "metadata": {
                    "tool_name": "smart_chart_generator",
                    "data_id": data_id,
                    "source_data_id": data_id,
                    "schema_type": schema_type,
                    "schema_version": "v2.0",
                    "record_count": len(existing_visuals),
                    "scenario": "chart_generation",
                    "generator": "smart_chart_generator",
                    "registry_schema": "chart_config",
                    "skipped": True,  # 标记为跳过
                    "skip_reason": "上游工具已包含可视化配置"
                },
                "summary": f"[SKIP] 跳过智能图表生成 - 上游工具已包含{len(existing_visuals)}个可视化配置 (UDF v2.0)"
            }

        # 如果没有找到visuals，返回简单的跳过结果
        logger.info(
            "no_existing_visuals_found",
            data_id=data_id,
            schema_type=schema_type
        )
        return {
            "status": "success",
            "success": True,
            "data": None,
            "visuals": [],  # 返回空列表
            "metadata": {
                "tool_name": "smart_chart_generator",
                "data_id": data_id,
                "source_data_id": data_id,
                "schema_type": schema_type,
                "schema_version": "v2.0",
                "record_count": 0,
                "scenario": "chart_generation",
                "generator": "smart_chart_generator",
                "registry_schema": "chart_config",
                "skipped": True,
                "skip_reason": "检测到数据来自已处理的上游工具"
            },
            "summary": f"[SKIP] 跳过智能图表生成 - 数据来自已处理的上游工具 (UDF v2.0)"
        }

    def _infer_expert_source(self, schema_type: str, data_id: str) -> str:
        """
        根据schema_type和data_id推断数据来源的专家类型

        用于前端大屏分类：
        - "weather": 气象分析专家的数据
        - "component": 组分分析专家的数据

        Args:
            schema_type: 数据schema类型
            data_id: 数据ID

        Returns:
            专家类型字符串 ("weather" 或 "component")
        """
        # 气象相关的schema类型
        weather_schemas = [
            "weather", "meteorology", "meteorology_unified",
            "current_weather", "weather_forecast",
            "fire_hotspots", "dust_data", "satellite_data",
            "trajectory", "upwind_analysis"
        ]

        # 组分/空气质量相关的schema类型
        component_schemas = [
            "air_quality_unified", "guangdong_stations",
            "regional_city_comparison", "regional_station_comparison",
            "vocs_unified", "vocs", "particulate", "particulate_unified",
            "pmf_result", "obm_ofp_result",
            "air_quality", "component_data"
        ]

        # 1. 先根据schema_type判断
        if schema_type in weather_schemas:
            return "weather"
        if schema_type in component_schemas:
            return "component"

        # 2. 从data_id中推断（格式: schema:version:id）
        if data_id:
            data_id_lower = data_id.lower()
            if any(s in data_id_lower for s in ["weather", "meteorology", "trajectory", "fire", "dust"]):
                return "weather"
            if any(s in data_id_lower for s in ["air_quality", "guangdong", "vocs", "pmf", "obm", "component"]):
                return "component"

        # 3. 默认归类为组分专家（因为大部分分析数据是空气质量相关）
        logger.debug(
            "expert_source_default_to_component",
            schema_type=schema_type,
            data_id=data_id,
            reason="无法明确推断，默认归类为component"
        )
        return "component"
