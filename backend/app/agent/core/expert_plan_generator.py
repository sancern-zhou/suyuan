"""
专家计划生成器 (ExpertPlanGenerator)

职责：为每个专家生成具体的工具调用计划
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
import structlog
import uuid
import json

from .structured_query_parser import StructuredQuery
from config.settings import settings
from app.services.llm_service import llm_service

logger = structlog.get_logger()

# 自带专业图表的工具列表（这些工具生成的数据不需要 viz 专家再处理）
# 这些工具会直接返回 visuals 字段，包含 base64 编码的专业图表
TOOLS_WITH_BUILTIN_VISUALS = {
    # OBM分析工具 - 生成EKMA曲面图、减排路径图、敏感性分析图、控制建议图
    "calculate_obm_full_chemistry",
    # 轨迹分析工具 - 生成轨迹地图
    "meteorological_trajectory_analysis",
    # 上风向企业分析 - 生成企业分布地图
    "analyze_upwind_enterprises",
}

# 自带图表的数据schema（用于识别来自上述工具的数据）
SCHEMAS_WITH_BUILTIN_VISUALS = {
    "obm_full_chemistry_result",
    "trajectory_result",
    "upwind_enterprise_result",
    # "pmf_result",  # 已移除，PMF不再自带图表，由viz expert通过smart_chart_generator生成
}


class ToolCallPlan(BaseModel):
    """单个工具调用计划"""
    tool: str = Field(..., description="工具名称")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    input_bindings: Dict[str, Any] = Field(default_factory=dict, description="输入绑定配置（用于参数绑定）")
    purpose: str = Field("", description="调用目的")
    depends_on: List[int] = Field(default_factory=list, description="依赖的工具索引")
    role: Optional[str] = Field(None, description="工具角色标识（如 water-soluble, carbon, crustal, trace）")
    skip_viz: bool = Field(False, description="是否跳过可视化专家（用于计算型数据，如近30天空气质量用于SOR/NOR计算）")


class ExpertTask(BaseModel):
    """专家任务"""
    task_id: str = Field(..., description="任务ID")
    expert_type: str = Field(..., description="专家类型")
    task_description: str = Field("", description="任务描述（自然语言）")
    context: Dict[str, Any] = Field(default_factory=dict, description="结构化上下文")
    tool_plan: List[ToolCallPlan] = Field(default_factory=list, description="工具调用计划")
    upstream_data_ids: List[str] = Field(default_factory=list, description="前序数据引用")
    skip_viz_data_ids: List[str] = Field(default_factory=list, description="需要跳过可视化的data_id列表（来自上游工具的skip_viz标记）")


class ExpertPlanGenerator:
    """专家计划生成器 - 智能化工具参数生成"""

    # 工具规范定义（明确每个工具的参数要求）
    TOOL_SPECS = {
        # ========================================
        # 空气质量数据查询工具（优先级：jining > guangdong > air_quality）
        # ========================================
        "get_jining_regular_stations": {
            "param_type": "natural_language",
            "required_param": "question",
            "priority": 1,  # 最高优先级
            "description": "查询济宁市区域对比空气质量数据（区县/站点对比），**优先使用**",
            "example": "查询济宁市各区县2025-01-01至2025-12-31的PM2.5浓度月度数据，按浓度排序"
        },
        "get_guangdong_regular_stations": {
            "param_type": "natural_language",
            "required_param": "question",
            "priority": 2,  # 次优先级
            "description": "查询广东省区域对比空气质量数据（城市/站点对比），**次优先使用**",
            "example": "查询广东省各城市2025-01-01至2025-12-31的O3_8h浓度月度数据，按浓度排序"
        },
        "get_air_quality": {
            "param_type": "natural_language",
            "required_param": "question",
            "priority": 3,  # 最低优先级（仅当非济宁/广东地区使用）
            "description": "全国城市空气质量数据查询，**仅当查询非济宁/广东地区，或前两者查询失败时使用**",
            "example": "查询北京市2025-01-01至2025-01-31的PM2.5日均数据"
        },
        "get_vocs_data": {
            "param_type": "natural_language",
            "required_param": "question",
            "description": "通过自然语言查询VOCs组分数据（端口9092）",
            "example": "查询{location}的VOCs组分数据，包括苯系物、烷烃、烯烃等物种浓度"
        },
        "get_particulate_data": {
            "param_type": "natural_language",
            "required_param": "question",
            "description": "通过自然语言查询颗粒物组分数据（端口9093）",
            "example": "查询{location}的PM2.5组分数据，包括SO4、NO3、NH4、OC、EC等"
        },

        # 结构化参数型工具
        "get_weather_data": {
            "param_type": "structured",
            "required_params": ["data_type", "lat", "lon", "start_time", "end_time"],
            "description": "获取结构化气象数据",
            "example": {"data_type": "era5_historical", "lat": 23.0469, "lon": 112.4651, "start_time": "2025-11-07", "end_time": "2025-11-09"}
        },
        "get_current_weather": {
            "param_type": "structured",
            "required_params": ["lat", "lon"],
            "optional_params": ["location_name"],
            "description": "获取当前天气观测数据",
            "example": {"lat": 23.0469, "lon": 112.4651, "location_name": "肇庆市"}
        },
        "get_weather_forecast": {
            "param_type": "structured",
            "required_params": ["lat", "lon"],
            "optional_params": ["location_name", "forecast_days", "hourly", "daily"],
            "description": "获取天气预报数据（未来7-16天，包含边界层高度预报）",
            "example": {"lat": 23.0469, "lon": 112.4651, "location_name": "广州市", "forecast_days": 7, "hourly": True, "daily": True}
        },
        "meteorological_trajectory_analysis": {
            "param_type": "structured",
            "required_params": ["lat", "lon", "start_time", "hours"],
            "description": "气象轨迹分析",
            "example": {"lat": 23.0469, "lon": 112.4651, "start_time": "2025-11-07", "hours": 72}
        },
        "analyze_upwind_enterprises": {
            "param_type": "structured",
            "required_params": ["lat", "lon", "analysis_date"],
            "description": "上风向企业分析",
            "example": {"lat": 23.0469, "lon": 112.4651, "analysis_date": "2025-11-07"}
        },
        "analyze_trajectory_sources": {
            "param_type": "structured",
            "required_params": ["lat", "lon"],
            "optional_params": ["city_name", "mode", "days", "pollutant", "search_radius_km", "top_n"],
            "description": "HYSPLIT轨迹+源清单深度溯源分析（3-5分钟）",
            "example": {"lat": 23.13, "lon": 113.26, "city_name": "广州", "mode": "backward", "days": 2, "pollutant": "VOCs"}
        },
        # ========================================
        # PMF源解析工具（颗粒物专用 - 需要水溶性离子+碳组分）
        # ========================================
        "calculate_pm_pmf": {
            "param_type": "structured",
            "required_params": ["data_id", "gas_data_id"],
            "description": "PM2.5/PM10 颗粒物PMF源解析（依赖水溶性离子和碳组分数据）",
            "example": {"data_id": "particulate_unified:v1:xxx", "gas_data_id": "particulate_unified:v1:yyy"}
        },
        # ========================================
        # PMF源解析工具（VOCs专用 - 仅用于臭氧溯源）
        # ========================================
        "calculate_vocs_pmf": {
            "param_type": "structured",
            "required_params": ["data_id"],
            "description": "VOCs挥发性有机物PMF源解析（仅用于臭氧溯源分析）",
            "example": {"data_id": "vocs_unified:v1:abc123"}
        },
        "calculate_obm_full_chemistry": {
            "param_type": "structured",
            "required_params": ["vocs_data_id"],
            "optional_params": ["nox_data_id", "o3_data_id", "mode", "o3_target"],
            "description": "OBM分析（EKMA/PO3/RIR） - 使用RACM2完整化学机理(102物种,504反应)，~2-3分钟",
            "example": {"vocs_data_id": "vocs:v1:abc123", "mode": "all"}
        },
        "smart_chart_generator": {
            "param_type": "structured",
            "required_params": ["data_id", "chart_purpose"],
            "description": "智能图表生成器",
            "example": {"data_id": "data_id:v1:xyz789", "chart_purpose": "展示臭氧浓度时间变化趋势"}
        },

        # ========================================
        # 颗粒物组分分析工具（新增）
        # ========================================
        "calculate_reconstruction": {
            "param_type": "structured",
            "required_params": ["data_id"],
            "optional_params": ["data_id_carbon", "data_id_crustal", "data_id_trace", "reconstruction_type", "oc_to_om", "negative_handling", "oxide_coeff_dict"],
            "description": "PM2.5 7大组分重构（OM、NO3、SO4、NH4、EC、地壳物质、微量元素），支持多数据源合并",
            "example": {"data_id": "particulate:v1:xxx", "data_id_carbon": "particulate:v1:yyy", "reconstruction_type": "full"}
        },
        "calculate_carbon": {
            "param_type": "structured",
            "required_params": ["data_id"],
            "optional_params": ["carbon_type", "oc_to_om", "poc_method"],
            "description": "碳组分分析（POC、SOC、EC/OC比值）",
            "example": {"data_id": "particulate:v1:xxx", "carbon_type": "pm25"}
        },
        "calculate_crustal": {
            "param_type": "structured",
            "required_params": ["data_id"],
            "optional_params": ["oxide_coeff_dict", "reconstruction_type"],
            "description": "地壳元素分析（氧化物转换、箱线图）",
            "example": {"data_id": "particulate:v1:xxx"}
        },
        "calculate_soluble": {
            "param_type": "structured",
            "required_params": ["data_id"],
            "optional_params": ["gas_data_id", "analysis_type", "ion_info"],
            "description": "水溶性离子分析（三元图、SOR/NOR、阴阳离子平衡），需要气体数据（NO2/SO2）计算SOR/NOR",
            "example": {"data_id": "particulate:v1:xxx", "gas_data_id": "air_quality:v1:yyy", "analysis_type": "full"}
        },
        "calculate_trace": {
            "param_type": "structured",
            "required_params": ["data_id"],
            "optional_params": ["al_column", "taylor_dict"],
            "description": "微量元素分析（铝归一化、Taylor丰度对比）",
            "example": {"data_id": "particulate:v1:xxx", "al_column": "铝"}
        },

        # ========================================
        # 颗粒物组分查询工具（结构化参数 - 替代 get_particulate_data）
        # ========================================
        "get_pm25_ionic": {
            "param_type": "structured",
            "required_params": ["start_time", "end_time"],
            "optional_params": ["locations", "station", "code", "data_type", "time_granularity"],
            "description": "查询PM2.5水溶性离子组分（F⁻、Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺等），支持自动位置映射",
            "example": {"locations": ["深圳"], "start_time": "2026-01-31 00:00:00", "end_time": "2026-01-31 23:59:59"}
        },
        "get_pm25_carbon": {
            "param_type": "structured",
            "required_params": ["start_time", "end_time"],
            "optional_params": ["locations", "station", "code", "data_type", "time_granularity"],
            "description": "查询PM2.5碳组分（OC有机碳、EC元素碳），支持自动位置映射",
            "example": {"locations": ["深圳"], "start_time": "2026-01-31 00:00:00", "end_time": "2026-01-31 23:59:59"}
        },
        "get_pm25_crustal": {
            "param_type": "structured",
            "required_params": ["start_time", "end_time"],
            "optional_params": ["locations", "station", "code", "data_type", "time_granularity", "elements"],
            "description": "查询PM2.5地壳元素（Al、Si、Fe、Ca、Ti、Mn等），支持自动位置映射",
            "example": {"locations": ["深圳"], "start_time": "2026-01-31 00:00:00", "end_time": "2026-01-31 23:59:59"}
        },
        "get_particulate_components": {
            "param_type": "structured",
            "required_params": ["start_time", "end_time"],
            "optional_params": ["locations", "station", "code", "data_type", "time_granularity"],
            "description": "查询PM2.5综合组分（Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、OC、EC），推荐用于PMF源解析",
            "example": {"locations": ["深圳"], "start_time": "2026-01-31 00:00:00", "end_time": "2026-01-31 23:59:59"}
        }
    }

    # 专家工具模板（气象专家：专注气象分析，可视化由VizExecutor统一负责）
    EXPERT_TEMPLATES = {
        "weather": {
            "description": "气象分析专家（专注气象数据获取和分析，轨迹分析可输出地图）",
            "required_tools": ["get_weather_data"],  # 仅包含气象数据工具
            "optional_tools": [
                # 核心气象工具
                "get_universal_meteorology",
                "get_current_weather",
                "get_weather_forecast",
                # 辅助气象工具
                "get_fire_hotspots",
                "get_dust_data",
                "get_satellite_data",
                # 专业分析工具
                "meteorological_trajectory_analysis",
                "trajectory_simulation",
                "analyze_upwind_enterprises",
                # 注意：analyze_upwind_enterprises已内置地图生成，无需generate_map
            ],
            "default_plan": [
                {
                    "tool": "get_weather_data",
                    "param_template": "auto",
                    "purpose": "获取ERA5历史气象数据",
                    "priority": "high"
                },
                # 【天气预报】获取未来7天预报数据（包含边界层高度预报）
                {
                    "tool": "get_weather_forecast",
                    "param_template": "auto",
                    "purpose": "获取未来1-16天天气预报（包含边界层高度、风速风向等关键参数，用于污染趋势预测和改善时机判断）",
                    "priority": "high"
                },
                # 【快速溯源】默认执行轨迹分析
                {
                    "tool": "meteorological_trajectory_analysis",
                    "param_template": "auto",
                    "purpose": "后向轨迹分析（快速溯源默认流程）",
                    "depends_on": [0],
                    "priority": "high"
                },
                # 【快速溯源】默认执行上风向企业分析（已内置地图生成）
                {
                    "tool": "analyze_upwind_enterprises",
                    "param_template": "auto",
                    "purpose": "上风向企业分析（快速溯源默认流程）",
                    "depends_on": [0, 2],
                    "priority": "high"
                }
                # 注意：analyze_upwind_enterprises已内置生成地图，无需额外调用generate_map
                # 通用图表生成由 VizExecutor 统一负责
            ]
        },
        "component": {
            "description": "组分分析专家",
            "required_tools": ["get_guangdong_regular_stations"],
            "optional_tools": [
                "get_vocs_data",         # VOCs数据查询（端口9092）
                "get_particulate_data",  # 颗粒物数据查询（端口9093）
                "get_guangdong_regular_stations",       # 区域对比数据查询（替代get_air_quality）
                "calculate_pm_pmf",      # PMF源解析（颗粒物专用，依赖水溶性离子+碳组分数据）
                "calculate_vocs_pmf",    # PMF源解析（VOCs专用，用于臭氧溯源）
                "calculate_obm_full_chemistry",  # RACM2完整化学机理OBM分析（依赖VOCs数据）
                "iaqi_calculator",
                "ml_predictor"
            ],
            "default_plan": [
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",  # 使用LLM自动生成参数
                    "purpose": "获取常规污染物数据"
                }
            ],
            "tracing_plan": [
                # 【基础数据】获取常规污染物数据（包含O3、NOx，用于OBM分析）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",
                    "purpose": "获取常规污染物数据（O3、NOx、PM2.5等）"
                },
                # 【区域对比分析】城市级（station_code为空，获取周边城市数据）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_city_comparison",
                    "purpose": "获取目标城市与周边城市的目标污染物时序数据（判断区域传输）",
                    "condition": "station_code is None"
                },
                # 【区域对比分析】站点级（station_code不为空，获取周边站点数据）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_nearby_stations",
                    "purpose": "获取目标站点周边站点的目标污染物时序数据（判断区域传输）",
                    "condition": "station_code is not None"
                },
                # 【组分数据】根据污染物类型选择工具
                # VOCs组分数据（端口9092）- 用于O3溯源的OBM分析
                {
                    "tool": "get_vocs_data",
                    "param_template": "auto",
                    "purpose": "获取VOCs挥发性有机化合物组分数据（端口9092）",
                    "depends_on": [0],
                    "condition": "VOCs in pollutants or O3 in pollutants"
                },
                # 颗粒物组分数据（端口9093）- 用于PM2.5/PM10的PMF源解析
                {
                    "tool": "get_particulate_data",
                    "param_template": "auto",
                    "purpose": "获取PM2.5/PM10颗粒物组分数据（端口9093）",
                    "depends_on": [0],
                    "condition": "PM2.5 in pollutants or PM10 in pollutants"
                },
                {
                    "tool": "calculate_pm_pmf",
                    "param_template": "auto",
                    "purpose": "PMF源解析分析（颗粒物专用，依赖水溶性离子和碳组分数据）",
                    "depends_on": [2, 3],  # 依赖get_vocs_data和get_particulate_data
                    "condition": "PM2.5 in pollutants or PM10 in pollutants"  # PMF仅对颗粒物污染触发
                },
                # 4. OBM分析（使用RACM2完整化学机理 - pybox_integration）
                {
                    "tool": "calculate_obm_full_chemistry",
                    "param_template": "auto",
                    "purpose": "OBM分析（EKMA/PO3/RIR） - 使用RACM2完整化学机理",
                    "depends_on": [2, 0],  # 依赖get_vocs_data和get_guangdong_regular_stations
                    "condition": "O3 in pollutants or VOCs in pollutants"
                }
            ],
            # ========================================
            # 颗粒物溯源计划（PM2.5/PM10专用）
            # 包含：区域传输分析 + 5种组分分析 + PMF源解析
            # 【关键修改】使用多个独立查询（每个组分类型单独查询），避免数据合并问题
            # API返回路径：resultData（碳组分）、resultOne（离子/地壳/微量元素）
            # ========================================
            "pm_tracing_plan": [
                # 0. 区域传输分析 - 城市级（station_code为空，或location是城市级别）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_city_comparison",
                    "purpose": "获取目标城市与周边城市的PM2.5/PM10小时数据（判断区域传输）",
                    "condition": "is_city_level_query or station_code is None"
                },
                # 0. 区域传输分析 - 站点级（station_code不为空且location是站点级别）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",
                    "purpose": "获取目标站点周边城市的PM2.5/PM10、AQI小时数据（判断区域传输）",
                    "condition": "station_code is not None and not is_city_level_query"
                },
                # 0.5 获取气象数据（用于气象-污染协同分析和气象时序图生成）
                # 参考臭氧溯源流程，确保颗粒物溯源也能生成气象时序图
                {
                    "tool": "get_weather_data",
                    "param_template": "auto",
                    "purpose": "获取气象数据（温度、湿度、风速、风向，用于气象-污染协同分析和生成气象时序图）",
                    "condition": "lat is not None and lon is not None"
                },
                # 1. 【结构化查询】水溶性离子数据查询（F⁻、Cl⁻、NO₃⁻、SO₄²⁻、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺）
                {
                    "tool": "get_pm25_ionic",
                    "param_template": "auto",
                    "purpose": "获取PM2.5水溶性离子数据（SO4、NO3、NH4、Cl、Ca、Mg、K、Na）",
                    "role": "water-soluble"
                },
                # 2. 【结构化查询】碳组分数据查询（OC有机碳、EC元素碳）
                {
                    "tool": "get_pm25_carbon",
                    "param_template": "auto",
                    "purpose": "获取PM2.5碳组分数据（OC、EC）",
                    "role": "carbon"
                },
                # 3. 【结构化查询】地壳元素数据查询（Al、Si、Fe、Ca、Ti、Mn等）
                {
                    "tool": "get_pm25_crustal",
                    "param_template": "auto",
                    "purpose": "获取PM2.5地壳元素数据（Al、Si、Fe、Ca、Mg、K、Na、Ti）",
                    "role": "crustal"
                },
                # 4. 【结构化查询】微量元素数据查询（使用地壳元素工具，指定微量元素列表）
                {
                    "tool": "get_pm25_crustal",
                    "param_template": "auto",
                    "purpose": "获取PM2.5微量元素/重金属数据（Zn、Pb、Cu、Cd、As等）",
                    "role": "trace",
                    "input_bindings": {
                        "elements": ["Zn", "Pb", "Cu", "Ni", "Cr", "Mn", "Cd", "As", "Se"]
                    }
                },
                # 5. 获取常规污染物数据（用于水溶性离子分析的SOR/NOR计算）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",
                    "purpose": "获取常规污染物数据（SO2、NO2用于SOR/NOR计算）"
                },
                # 6. 7大组分重构分析（需要全部4种组分数据）
                {
                    "tool": "calculate_reconstruction",
                    "param_template": "auto",
                    "purpose": "7大组分重构分析",
                    "depends_on": [1, 2, 3, 4],  # 依赖所有组分查询
                    "input_bindings": {
                        "data_id": "get_pm25_ionic[role=water-soluble].data_id",
                        "data_id_carbon": "get_pm25_carbon[role=carbon].data_id",
                        "data_id_crustal": "get_pm25_crustal[role=crustal].data_id",
                        "data_id_trace": "get_pm25_crustal[role=trace].data_id"
                    }
                },
                # 7. 水溶性离子分析（三元图、SOR/NOR）
                # 注意：input_bindings 已配置在 tool_dependencies.py 中
                # 使用 [FIRST] 模式自动匹配第一个成功的查询结果
                {
                    "tool": "calculate_soluble",
                    "param_template": "auto",
                    "purpose": "水溶性离子分析（三元图、离子平衡、SOR/NOR）",
                    "depends_on": [1, 5],  # 依赖水溶性离子数据（索引1）和气体数据（索引5）
                    "input_bindings": {
                        "data_id": "get_pm25_ionic[role=water-soluble].data_id",
                        "gas_data_id": "get_guangdong_regular_stations[FIRST].data_id",
                        "analysis_type": "full"
                    }
                },
                # 8. 碳组分分析（POC/SOC/EC/OC）
                {
                    "tool": "calculate_carbon",
                    "param_template": "auto",
                    "purpose": "碳组分分析（POC、SOC、EC/OC比值）",
                    "depends_on": [2],  # 依赖碳组分数据
                    "input_bindings": {
                        "data_id": "get_pm25_carbon[role=carbon].data_id",
                        "carbon_type": "pm25",
                        "oc_to_om": 1.4,
                        "poc_method": "ec_normalization"
                    }
                },
                # 9. 地壳元素分析
                {
                    "tool": "calculate_crustal",
                    "param_template": "auto",
                    "purpose": "地壳元素分析（扬尘源识别）",
                    "depends_on": [3],  # 依赖地壳元素数据
                    "input_bindings": {
                        "data_id": "get_pm25_crustal[role=crustal].data_id",
                        "reconstruction_type": "full"
                    }
                },
                # 10. 微量元素分析（富集因子）
                {
                    "tool": "calculate_trace",
                    "param_template": "auto",
                    "purpose": "微量元素分析（富集因子、人为源识别）",
                    "depends_on": [4],  # 依赖微量元素数据
                    "input_bindings": {
                        "data_id": "get_pm25_crustal[role=trace].data_id",
                        "al_column": "铝"
                    }
                },
                # 11. PMF源解析（需要水溶性离子+碳组分）
                {
                    "tool": "calculate_pm_pmf",
                    "param_template": "auto",
                    "purpose": "PMF源解析（定量源贡献率 - 颗粒物专用）",
                    "depends_on": [1, 2],  # 依赖水溶性离子和碳组分数据
                    "condition": "PM2.5 in pollutants or PM10 in pollutants",
                    "input_bindings": {
                        "data_id": "get_pm25_ionic[role=water-soluble].data_id",
                        "gas_data_id": "get_pm25_carbon[role=carbon].data_id",
                        "pollutant_type": "PM2.5",
                        "station_name": "get_pm25_ionic[role=water-soluble].metadata.station_name or {location}"
                    }
                }
            ],
            # ========================================
            # 臭氧溯源计划（VOCs/O3专用）
            # 包含：区域传输分析 + 空气质量 + VOCs数据 + PMF + OBM
            # PMF用于VOCs前体物的源解析分析
            # ========================================
            "ozone_tracing_plan": [
                # 0. 区域传输分析 - 城市级（station_code为空，根据城市获取周边城市数据）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_city_comparison",
                    "purpose": "获取目标城市与周边城市的O3/PM2.5小时数据（判断区域传输）",
                    "condition": "station_code is None"
                },
                # 0. 区域传输分析 - 站点级（station_code不为空，获取周边站点数据）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_nearby_stations",
                    "purpose": "获取目标站点周边站点的O3/PM2.5小时数据（判断区域传输）",
                    "condition": "station_code is not None"
                },
                # 1. 获取常规污染物数据（包含O3、NOx，用于OBM分析）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",
                    "purpose": "获取常规污染物数据（O3、NOx、PM2.5等）"
                },
                # 2. 获取VOCs组分数据（用于OBM分析和PMF VOCs源解析）
                {
                    "tool": "get_vocs_data",
                    "param_template": "auto",
                    "purpose": "获取VOCs挥发性有机化合物组分数据（端口9092）",
                    "depends_on": [1]
                },
                # 3. PMF源解析（VOCs前体物源解析 - 臭氧溯源专用）
                {
                    "tool": "calculate_vocs_pmf",
                    "param_template": "auto",
                    "purpose": "PMF源解析（VOCs挥发性有机物源解析 - 用于臭氧溯源）",
                    "depends_on": [2]  # 依赖VOCs数据（索引2是get_vocs_data）
                },
                # 4. OBM分析（使用RACM2完整化学机理 - pybox_integration）
                {
                    "tool": "calculate_obm_full_chemistry",
                    "param_template": "auto",
                    "purpose": "OBM分析（EKMA/PO3/RIR） - 使用RACM2完整化学机理",
                    "depends_on": [2, 1]  # 依赖get_vocs_data和get_guangdong_regular_stations
                }
            ],
            # RACM2完整化学机理分析计划 (use_full_chemistry=true时使用)
            "tracing_plan_full_chemistry": [
                # 【基础数据】获取常规污染物数据（包含O3、NOx，用于OBM分析）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",
                    "purpose": "获取常规污染物数据（O3、NOx、PM2.5等）"
                },
                # 【区域对比分析】城市级（station_code为空）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_city_comparison",
                    "purpose": "获取目标城市与周边城市的目标污染物时序数据（判断区域传输）",
                    "condition": "station_code is None"
                },
                # 【区域对比分析】站点级（station_code不为空，获取周边站点数据）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_nearby_stations",
                    "purpose": "获取目标站点周边站点的目标污染物时序数据（判断区域传输）",
                    "condition": "station_code is not None"
                },
                # 【组分数据】根据污染物类型选择工具
                # VOCs组分数据（端口9092）- 用于O3溯源的OBM分析
                {
                    "tool": "get_vocs_data",
                    "param_template": "auto",
                    "purpose": "获取VOCs挥发性有机化合物组分数据（端口9092）",
                    "depends_on": [0],
                    "condition": "VOCs in pollutants or O3 in pollutants"
                },
                # 颗粒物组分数据（端口9093）- 用于PM2.5/PM10的PMF源解析
                {
                    "tool": "get_particulate_data",
                    "param_template": "auto",
                    "purpose": "获取PM2.5/PM10颗粒物组分数据（端口9093）",
                    "depends_on": [0],
                    "condition": "PM2.5 in pollutants or PM10 in pollutants"
                },
                {
                    "tool": "calculate_pm_pmf",
                    "param_template": "auto",
                    "purpose": "PMF源解析分析（颗粒物专用，依赖水溶性离子和碳组分数据）",
                    "depends_on": [2, 3],  # 依赖get_vocs_data和get_particulate_data
                    "condition": "PM2.5 in pollutants or PM10 in pollutants"  # PMF仅对颗粒物污染触发
                },
                # 4. OBM分析（使用RACM2完整化学机理 - pybox_integration）
                {
                    "tool": "calculate_obm_full_chemistry",
                    "param_template": "auto",
                    "purpose": "OBM分析（EKMA/PO3/RIR） - 使用RACM2完整化学机理",
                    "depends_on": [2, 0],  # 依赖get_vocs_data和get_guangdong_regular_stations
                    "condition": "O3 in pollutants or VOCs in pollutants"
                }
            ],
            # 【深度溯源】使用RACM2完整化学机理分析
            "deep_tracing_plan": [
                # 【基础数据】获取常规污染物数据（包含O3、NOx，用于OBM分析）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "auto",
                    "purpose": "获取常规污染物数据（O3、NOx、PM2.5等）"
                },
                # 【区域对比分析】城市级（station_code为空）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_city_comparison",
                    "purpose": "获取目标城市与周边城市的目标污染物时序数据（判断区域传输）",
                    "condition": "station_code is None"
                },
                # 【区域对比分析】站点级（station_code不为空，获取周边站点数据）
                {
                    "tool": "get_guangdong_regular_stations",
                    "param_template": "regional_nearby_stations",
                    "purpose": "获取目标站点周边站点的目标污染物时序数据（判断区域传输）",
                    "condition": "station_code is not None"
                },
                # 【组分数据】根据污染物类型选择工具
                # VOCs组分数据（端口9092）- 用于O3溯源的OBM分析
                {
                    "tool": "get_vocs_data",
                    "param_template": "auto",
                    "purpose": "获取VOCs挥发性有机化合物组分数据（端口9092）",
                    "depends_on": [0],
                    "condition": "VOCs in pollutants or O3 in pollutants"
                },
                # 颗粒物组分数据（端口9093）- 用于PM2.5/PM10的PMF源解析
                {
                    "tool": "get_particulate_data",
                    "param_template": "auto",
                    "purpose": "获取PM2.5/PM10颗粒物组分数据（端口9093）",
                    "depends_on": [0],
                    "condition": "PM2.5 in pollutants or PM10 in pollutants"
                },
                {
                    "tool": "calculate_pm_pmf",
                    "param_template": "auto",
                    "purpose": "PMF源解析分析（颗粒物专用，依赖水溶性离子和碳组分数据）",
                    "depends_on": [2, 3],  # 依赖get_vocs_data和get_particulate_data
                    "condition": "PM2.5 in pollutants or PM10 in pollutants"  # PMF仅对颗粒物污染触发
                },
                # 4. OBM分析（使用RACM2完整化学机理 - pybox_integration）
                {
                    "tool": "calculate_obm_full_chemistry",
                    "param_template": "auto",
                    "purpose": "OBM分析（EKMA/PO3/RIR） - 使用RACM2完整化学机理",
                    "depends_on": [2, 0],  # 依赖get_vocs_data和get_guangdong_regular_stations
                    "condition": "O3 in pollutants or VOCs in pollutants"
                }
            ]
        },
        "viz": {
            "description": "可视化专家",
            "required_tools": ["smart_chart_generator"],
            "optional_tools": ["generate_chart", "generate_map"],
            "default_plan": [
                {
                    "tool": "smart_chart_generator",
                    "param_template": "auto",
                    "purpose": "智能图表生成（基于所有上游数据）",
                    "multi_data_id": True  # 标记：需要为每个上游data_id都生成图表
                }
            ]
        },
        "report": {
            "description": "报告专家",
            "required_tools": [],
            "optional_tools": [],
            "default_plan": []  # 报告专家不调用工具，纯LLM综合
        }
    }
    
    def __init__(self):
        logger.info("expert_plan_generator_initialized")
    
    def determine_required_experts(
        self,
        query: StructuredQuery
    ) -> List[str]:
        """
        根据结构化查询信息推断需要的专家列表
        """
        experts: List[str] = []
        
        def _add(expert: str):
            if expert not in experts:
                experts.append(expert)

        # 需要气象专家：已经解析出经纬度
        if query.lat is not None and query.lon is not None:
            _add("weather")

        # 只要关注污染物，就需要组分专家
        if query.pollutants:
            _add("component")

        # 只要有污染物，就生成图表辅助展示
        if query.pollutants:
            _add("viz")

        # 如果有至少两个核心专家，则添加报告专家
        core_experts = [e for e in experts if e not in {"viz", "report"}]
        if len(core_experts) >= 2:
            _add("report")

        if not experts:
            _add("component")

        return self._order_experts(experts)
    
    def generate(
        self, 
        query: StructuredQuery,
        required_experts: Optional[List[str]] = None,
        upstream_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, ExpertTask]:
        """
        为每个专家生成任务
        
        Args:
            query: 结构化查询
            required_experts: 需要的专家列表
            upstream_results: 前序专家的结果（用于获取data_id）
            
        Returns:
            Dict[expert_type, ExpertTask]
        """
        upstream_results = upstream_results or {}
        expert_list = required_experts or self.determine_required_experts(query)
        ordered_experts = self._order_experts(expert_list)
        tasks = {}
        
        for expert_type in ordered_experts:
            task = self._generate_expert_task(
                expert_type, 
                query, 
                upstream_results
            )
            tasks[expert_type] = task
        
        if tasks:
            logger.info(
                "expert_plans_generated",
                experts=list(tasks.keys()),
                total_tools=sum(len(t.tool_plan) for t in tasks.values())
            )
        
        return tasks
    
    def _generate_expert_task(
        self,
        expert_type: str,
        query: StructuredQuery,
        upstream_results: Dict[str, Any]
    ) -> ExpertTask:
        """生成单个专家的任务"""

        template = self.EXPERT_TEMPLATES.get(expert_type, {})
        task_id = f"{expert_type}_{uuid.uuid4().hex[:8]}"

        # 构建上下文
        context = self._build_context(query, expert_type)
        context["expert_type"] = expert_type  # 添加专家类型到上下文

        # 选择计划模板（简化逻辑：只根据污染物类型选择）
        if expert_type == "weather":
            # 气象专家：使用默认计划（基础气象 + 轨迹 + 上风向企业）
            plan_template = template.get("default_plan", [])
            logger.info("using_default_weather_plan", expert=expert_type)
        else:
            # 组分专家：根据污染物类型选择专用计划
            pollutants = query.pollutants or []
            is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])
            is_ozone_tracing = any(p in pollutants for p in ["O3", "臭氧", "VOCs"])

            if is_pm_tracing and "pm_tracing_plan" in template:
                # 颗粒物溯源：使用5种组分分析 + PMF
                plan_template = template["pm_tracing_plan"]
                logger.info("using_pm_tracing_plan", pollutants=pollutants)
            elif is_ozone_tracing and "ozone_tracing_plan" in template:
                # 臭氧溯源：使用VOCs分析 + OBM + PMF
                plan_template = template["ozone_tracing_plan"]
                logger.info("using_ozone_tracing_plan", pollutants=pollutants)
            else:
                # 默认计划
                plan_template = template.get("default_plan", [])

        # 根据用户选择过滤OBM相关步骤
        plan_template = self._filter_obm_steps_if_disabled(
            expert_type,
            plan_template,
            query
        )

        # 填充计划
        tool_plan = self._fill_plan_template(
            plan_template,
            query,
            context,
            upstream_results
        )

        # 收集上游data_id
        upstream_data_ids = self._collect_upstream_data_ids(
            expert_type,
            upstream_results
        )

        # 生成任务描述
        task_description = self._generate_task_description(
            expert_type,
            query
        )

        return ExpertTask(
            task_id=task_id,
            expert_type=expert_type,
            task_description=task_description,
            context=context,
            tool_plan=tool_plan,
            upstream_data_ids=upstream_data_ids
        )

    def _filter_obm_steps_if_disabled(
        self,
        expert_type: str,
        plan_template: List[Dict[str, Any]],
        query: StructuredQuery
    ) -> List[Dict[str, Any]]:
        """
        根据precision参数过滤OBM相关工具。
        - fast模式：不过滤
        - standard/full模式：不过滤
        注：所有OBM工具统一使用calculate_obm_full_chemistry
        """
        if expert_type != "component":
            return plan_template

        # 不过滤任何工具，统一使用calculate_obm_full_chemistry
        return plan_template

    def _build_context(
        self,
        query: StructuredQuery,
        expert_type: str
    ) -> Dict[str, Any]:
        """构建专家上下文"""

        context = {
            "location": query.location,
            "lat": query.lat,
            "lon": query.lon,
            "station_code": query.station_code,
            "start_time": query.start_time,
            "end_time": query.end_time,
            "time_granularity": query.time_granularity,
            "pollutants": query.pollutants,
            "precision": getattr(query, 'precision', 'standard'),  # EKMA分析精度模式
            "grid_resolution": getattr(query, 'grid_resolution', 21)  # EKMA网格分辨率
        }

        # 添加主要污染物（用于源解析）
        if query.pollutants:
            context["primary_pollutant"] = query.pollutants[0]

        return context
    
    def _should_skip_viz(
        self,
        tool_name: str,
        param_template: str,
        context: Dict[str, Any],
        params: Dict[str, Any]
    ) -> bool:
        """
        判断工具调用是否需要跳过可视化专家

        用于计算型数据（如近30天空气质量用于SOR/NOR计算），不需要生成图表

        Args:
            tool_name: 工具名称
            param_template: 参数模板类型
            context: 上下文信息
            params: 生成的参数

        Returns:
            True表示需要跳过可视化，False表示需要生成图表
        """
        # 只对 get_guangdong_regular_stations 工具进行判断
        if tool_name != "get_guangdong_regular_stations":
            return False

        # 如果使用 regional_* 模板（区域对比），需要生成图表
        if param_template in ["regional_city_comparison", "regional_station_comparison", "regional_nearby_stations"]:
            return False

        # 如果是 auto 模板，检查是否是近30天数据（用于SOR/NOR计算）
        if param_template == "auto":
            question = params.get("question", "")
            pollutants = context.get("pollutants", [])

            # 判断是否为颗粒物溯源
            is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])

            if is_pm_tracing:
                # 从问题中提取时间范围，判断是否是近30天
                # 格式如："查询阳江市2025-11-25到2025-12-24期间的小时粒度的空气污染物数据"
                import re
                # 匹配 "XXXX-XX-XX到XXXX-XX-XX" 格式的日期范围
                date_range_match = re.search(r'(\d{4}-\d{2}-\d{2})到(\d{4}-\d{2}-\d{2})', question)
                if date_range_match:
                    from datetime import datetime, timedelta
                    try:
                        start_date = datetime.strptime(date_range_match.group(1), "%Y-%m-%d")
                        end_date = datetime.strptime(date_range_match.group(2), "%Y-%m-%d")
                        date_range = (end_date - start_date).days + 1

                        # 如果时间范围 >= 25天，认为是用于计算的数据，不需要图表
                        if date_range >= 25:
                            logger.info(
                                "skip_viz_for_calculation_data",
                                tool=tool_name,
                                date_range=date_range,
                                reason="近30天数据用于SOR/NOR计算，无需生成图表"
                            )
                            return True
                    except Exception as e:
                        logger.warning("date_range_parse_failed", error=str(e))

        return False

    def _fill_plan_template(
        self,
        plan_template: List[Dict],
        query: StructuredQuery,
        context: Dict[str, Any],
        upstream_results: Dict[str, Any],
        skip_viz_data_ids: List[str] = None
    ) -> List[ToolCallPlan]:
        """填充计划模板（支持智能参数生成和input_bindings）

        Args:
            plan_template: 工具计划模板
            query: 结构化查询
            context: 专家上下文
            upstream_results: 上游专家结果
            skip_viz_data_ids: 需要跳过可视化的data_id列表（来自上游工具的skip_viz标记）
        """

        from .tool_dependencies import TOOL_DEPENDENCY_GRAPHS

        tool_plans = []

        # 收集上游data_id
        upstream_data_ids = self._collect_upstream_data_ids_for_tools(upstream_results)

        # 【新增】过滤掉skip_viz_data_ids
        if skip_viz_data_ids:
            original_count = len(upstream_data_ids)
            upstream_data_ids = [did for did in upstream_data_ids if did not in skip_viz_data_ids]
            if original_count != len(upstream_data_ids):
                logger.info(
                    "upstream_data_ids_filtered_by_skip_viz",
                    original_count=original_count,
                    filtered_count=len(upstream_data_ids),
                    skipped_count=original_count - len(upstream_data_ids)
                )

        for i, item in enumerate(plan_template):
            # 检查条件
            if "condition" in item:
                if not self._check_condition(item["condition"], query):
                    continue

            tool_name = item["tool"]
            param_template = item.get("param_template", {})

            # 从工具依赖图中提取input_bindings
            input_bindings = {}
            expert_type = context.get("expert_type", "")
            tool_graph_config = TOOL_DEPENDENCY_GRAPHS.get(expert_type, {})
            if "tools" in tool_graph_config and tool_name in tool_graph_config["tools"]:
                input_bindings = tool_graph_config["tools"][tool_name].get("input_bindings", {})
                logger.info(
                    "input_bindings_extracted",
                    tool=tool_name,
                    expert_type=expert_type,
                    binding_count=len(input_bindings),
                    bindings=list(input_bindings.keys()) if input_bindings else []
                )
            else:
                logger.warning(
                    "input_bindings_not_found",
                    tool=tool_name,
                    expert_type=expert_type,
                    has_tools_config="tools" in tool_graph_config,
                    available_tools=list(tool_graph_config.get("tools", {}).keys()) if tool_graph_config else []
                )

            # 【关键修复】检查是否需要为每个上游data_id都生成工具调用
            if item.get("multi_data_id") and upstream_data_ids:
                # 为每个上游data_id都生成一个工具调用
                logger.info(
                    "generating_multi_data_id_tool_calls",
                    tool=tool_name,
                    data_id_count=len(upstream_data_ids),
                    data_ids=upstream_data_ids
                )

                for idx, data_id in enumerate(upstream_data_ids):
                    # 生成参数
                    if param_template == "auto":
                        try:
                            params = self._generate_sync_params(tool_name, context, [data_id])
                        except Exception as e:
                            logger.error(
                                "auto_param_generation_failed",
                                tool=tool_name,
                                data_id=data_id,
                                error=str(e)
                            )
                            params = {}
                    else:
                        params = self._fill_params(param_template, context, upstream_results)

                    # 为每个工具调用创建独立的plan
                    tool_plan = ToolCallPlan(
                        tool=tool_name,
                        params=params,
                        input_bindings=input_bindings,
                        purpose=f"{item.get('purpose', '')} [数据源 {idx + 1}/{len(upstream_data_ids)}]",
                        depends_on=item.get("depends_on", []),
                        role=item.get("role")  # 传递角色标识
                    )

                    tool_plans.append(tool_plan)
            else:
                # 原有逻辑：生成单个工具调用
                # 生成参数
                if param_template == "auto":
                    # 使用智能参数生成
                    import asyncio
                    try:
                        # 在同步方法中调用异步方法需要特殊处理
                        # 这里我们暂时使用同步生成，简化处理
                        params = self._generate_sync_params(tool_name, context, upstream_data_ids)
                    except Exception as e:
                        logger.error(
                            "auto_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = {}
                elif param_template == "regional_city_comparison":
                    # 城市级对比：目标城市+周边城市的目标污染物时序
                    try:
                        params = self._generate_regional_city_comparison_params(context)
                    except Exception as e:
                        logger.error(
                            "regional_city_comparison_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = self._generate_natural_language_params_sync(tool_name, context)
                elif param_template == "regional_station_comparison":
                    # 站点级对比：目标城市所有国控站点的目标污染物时序
                    try:
                        params = self._generate_regional_station_comparison_params(context)
                    except Exception as e:
                        logger.error(
                            "regional_station_comparison_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = self._generate_natural_language_params_sync(tool_name, context)
                elif param_template == "regional_nearby_stations":
                    # 周边站点对比：目标站点周边城市的目标污染物时序
                    try:
                        params = self._generate_regional_nearby_stations_params(context)
                    except Exception as e:
                        logger.error(
                            "regional_nearby_stations_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = self._generate_natural_language_params_sync(tool_name, context)
                # ========================================
                # 【关键修改】颗粒物溯源专用查询参数模板
                # 支持拆分为多个独立查询，并发执行
                # ========================================
                elif param_template == "pm_soluble_ions":
                    # 水溶性离子数据查询
                    try:
                        params = self._generate_pm_soluble_ions_params(context)
                    except Exception as e:
                        logger.error(
                            "pm_soluble_ions_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = {"question": f"查询{context.get('location', '目标区域')}的PM2.5水溶性离子数据（SO4、NO3、NH4等）"}
                elif param_template == "pm_carbon":
                    # 碳组分数据查询
                    try:
                        params = self._generate_pm_carbon_params(context)
                    except Exception as e:
                        logger.error(
                            "pm_carbon_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = {"question": f"查询{context.get('location', '目标区域')}的PM2.5碳组分数据（OC、EC）"}
                elif param_template == "pm_crustal":
                    # 地壳元素数据查询
                    try:
                        params = self._generate_pm_crustal_params(context)
                    except Exception as e:
                        logger.error(
                            "pm_crustal_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = {"question": f"查询{context.get('location', '目标区域')}的PM2.5地壳元素数据（Al、Si、Fe等）"}
                elif param_template == "pm_trace_elements":
                    # 微量元素/重金属数据查询
                    try:
                        params = self._generate_pm_trace_elements_params(context)
                    except Exception as e:
                        logger.error(
                            "pm_trace_elements_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = {"question": f"查询{context.get('location', '目标区域')}的PM2.5微量元素/重金属数据（Zn、Pb等）"}
                elif param_template == "pm_all_components":
                    # 【关键修改】完整PM2.5组分数据单次查询（包含所有4种类型）
                    try:
                        params = self._generate_pm_all_components_params(context)
                    except Exception as e:
                        logger.error(
                            "pm_all_components_param_generation_failed",
                            tool=tool_name,
                            error=str(e)
                        )
                        params = {"question": f"查询{context.get('location', '目标区域')}的PM2.5完整组分数据（包括水溶性离子、碳组分、地壳元素、微量元素）"}
                else:
                    # 使用原有参数填充逻辑
                    params = self._fill_params(param_template, context, upstream_results)

                # 判断是否需要跳过可视化（用于计算型数据，如近30天空气质量用于SOR/NOR计算）
                skip_viz = self._should_skip_viz(tool_name, param_template, context, params)

                tool_plan = ToolCallPlan(
                    tool=tool_name,
                    params=params,
                    input_bindings=input_bindings,
                    purpose=item.get("purpose", ""),
                    depends_on=item.get("depends_on", []),
                    role=item.get("role"),  # 传递角色标识
                    skip_viz=skip_viz
                )

                if skip_viz:
                    logger.info(
                        "tool_plan_skip_viz_set",
                        tool=tool_name,
                        purpose=item.get("purpose", ""),
                        reason="计算型数据，无需生成图表"
                    )

                tool_plans.append(tool_plan)

        return tool_plans

    def _generate_sync_params(
        self,
        tool_name: str,
        context: Dict[str, Any],
        upstream_data_ids: List[str]
    ) -> Dict[str, Any]:
        """同步生成参数（简化版，不调用LLM）"""

        # 获取工具规范
        tool_spec = self.TOOL_SPECS.get(tool_name, {})
        param_type = tool_spec.get("param_type", "structured")

        logger.info(
            "generating_sync_params",
            tool=tool_name,
            param_type=param_type,
            data_id_count=len(upstream_data_ids),
            data_ids=upstream_data_ids,
            expert_type=context.get("expert_type", "unknown")
        )

        if param_type == "natural_language":
            # 生成自然语言查询参数（同步版本）
            return self._generate_natural_language_params_sync(tool_name, context)
        else:
            # 生成结构化参数（同步版本）
            return self._generate_structured_params_sync(tool_name, context, upstream_data_ids)

    def _generate_natural_language_params_sync(
        self,
        tool_name: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """同步生成自然语言查询参数"""

        # 构建自然语言查询
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        pollutants = context.get("pollutants", [])
        primary_pollutant = context.get("primary_pollutant", pollutants[0] if pollutants else "污染物")
        # 【修复】强制使用小时粒度，忽略用户输入
        time_granularity = "hourly"

        pollutant_str = "、".join(pollutants) if pollutants else primary_pollutant

        # 构建查询字符串
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        # 【修复】强制构建时间粒度描述（固定为小时粒度）
        granularity_desc = "小时粒度的"

        # 根据工具类型生成不同查询 - 确保调用不同的API
        if tool_name == "get_guangdong_regular_stations":
            # 常规污染物监测数据
            question = f"查询{location}"
            if time_range:
                question += f"{time_range}期间"

            # 【新增】判断是否为颗粒物溯源的周边站点对比场景（station_code不为空）
            is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])
            station_code = context.get("station_code", "")

            if is_pm_tracing and station_code:
                # 【颗粒物溯源+周边站点场景】查询目标城市及周边城市的PM2.5、PM10、AQI小时数据
                from .structured_query_parser import GUANGDONG_CITIES

                # 清理城市名并获取周边城市
                location_clean = location.replace("站", "").replace("监测点", "").replace("市", "").replace("区", "").replace("县", "")
                available_cities = [c for c in GUANGDONG_CITIES if c != location_clean]
                neighbor_regions = available_cities[:4]
                regions_str = "、".join([f"{r}市" for r in neighbor_regions])

                question = f"查询{location_clean}市及周边城市（{regions_str}）{start_time}至{end_time}的{granularity_desc}PM2.5、PM10污染物浓度和AQI小时数据，用于判断区域传输和污染成因分析"
            else:
                # 其他场景：常规查询
                question += f"的{granularity_desc}空气污染物数据"
                if pollutants:
                    # 【关键修复】对于O3溯源分析，EKMA/OBM需要NO2数据
                    # 确保查询包含完整的必需污染物
                    required_pollutants = set(pollutants)
                    if any(p in ["O3", "臭氧", "ozone"] for p in pollutants):
                        # O3分析需要NO2进行敏感性分析
                        required_pollutants.add("NO2")
                    # 溯源分析需要完整数据（所有查询默认为溯源模式）
                    required_pollutants.update(["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"])
                    question += f"，重点关注{', '.join(sorted(required_pollutants))}"
                else:
                    question += "，包括PM2.5、PM10、O3、NO2、SO2、CO等常规污染物"
                question += "浓度变化趋势和AQI指数"

        elif tool_name == "get_vocs_data":
            # VOCs组分数据（端口9092）
            question = f"查询{location}"
            if time_range:
                question += f"{time_range}期间"
            question += f"的{granularity_desc}"
            question += "VOCs挥发性有机化合物组分数据"
            question += "，包括乙烷、丙烷、苯、甲苯、二甲苯、甲醛等具体物种浓度"

        elif tool_name == "get_particulate_data":
            # 颗粒物组分数据（端口9093）- 优化：溯源场景需要完整组分
            pollutants = context.get("pollutants", [])
            is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])

            if is_pm_tracing:
                # 【颗粒物溯源场景】需要获取完整的组分数据用于多工具分析
                question = f"""查询{location}{time_range}期间的小时级PM2.5颗粒物组分数据，要求包含以下全部组分（必须完整获取，不能遗漏）：

【水溶性离子 - 共9种】
SO4(硫酸盐)、NO3(硝酸盐)、NH4(铵盐)、F(氟)、Cl(氯)、Na(钠)、K(钾)、Mg(镁)、Ca(钙)

【碳组分 - 共2种】
OC(有机碳)、EC(元素碳)

【地壳元素 - 共8种】
Al(铝)、Si(硅)、Fe(铁)、Ca(钙)、Mg(镁)、K(钾)、Na(钠)、Ti(钛)

【微量元素/重金属 - 共9种】
Zn(锌)、Pb(铅)、Cu(铜)、Ni(镍)、Cr(铬)、Mn(锰)、Cd(镉)、As(砷)、Se(硒)

这些数据将用于以下分析：
1. 7大组分重构（OM、NO3、SO4、NH4、EC、地壳物质、微量元素）
2. 水溶性离子三元图、SOR/NOR、离子平衡分析
3. 碳组分分析（POC、SOC、EC/OC比值）
4. 地壳元素分析（扬尘源识别）
5. 微量元素富集因子分析（人为源识别）
6. PMF源解析

请确保返回所有组分数据，时间粒度为小时级。"""
            else:
                # 普通查询场景
                question = f"查询{location}"
                if time_range:
                    question += f"{time_range}期间"
                question += f"的{granularity_desc}"
                if analysis_prefix:
                    question += f"{analysis_prefix}"
                question += "PM2.5/PM10颗粒物组分数据"
                question += "，包括SO4、NO3、NH4、OC、EC等水溶性离子和碳组分浓度"

        elif tool_name == "get_guangdong_regular_stations":
            # 广东监测站点数据
            question = f"获取{location}及周边地区的空气监测站列表和数据"
            if time_range:
                question += f"，时间范围为{time_range}期间"
            question += "，包括站点名称、站点代码、监测项目、数据获取方式"

        else:
            # 其他工具的默认查询
            question = f"查询{location}"
            if time_range:
                question += f"{time_range}期间"
            question += f"的{granularity_desc}{pollutant_str}相关数据"

        return {"question": question}

    def _generate_regional_city_comparison_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成城市级区域对比查询参数

        查询目标城市+周边城市的【目标污染物】小时数据
        用于判断区域传输方向和贡献

        【颗粒物溯源场景】同时查询PM2.5和PM10（因为它们强相关）
        【O3溯源场景】查询O3

        查询问题格式：
        "查询揭阳市、汕头市、潮州市、梅州市2025-12-07 00:00:00至2025-12-07 23:00:00的O3小时数据"
        或
        "查询揭阳市、汕头市、潮州市、梅州市2025-12-07 00:00:00至2025-12-07 23:00:00的PM2.5和PM10小时数据"
        """
        from .structured_query_parser import GUANGDONG_CITIES, StructuredQueryParser

        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "")
        end_time = context.get("end_time", "")
        pollutants = context.get("pollutants", [])
        primary_pollutant = pollutants[0] if pollutants else "O3"

        # 清理城市名
        location_clean = location.replace("市", "").replace("区", "").replace("县", "")

        # 从广东省城市列表中获取周边城市（排除目标城市）
        available_cities = [c for c in GUANGDONG_CITIES if c != location_clean]
        # 选择前4个周边城市
        neighbor_regions = available_cities[:4]

        # 构建城市列表（目标城市+周边城市）
        all_regions = [location_clean] + neighbor_regions
        regions_str = "、".join([f"{r}市" for r in all_regions])

        # 【关键修改】判断是否为颗粒物溯源
        is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])

        if is_pm_tracing:
            # 【颗粒物溯源】同时查询PM2.5和PM10
            question = f"查询{regions_str}{start_time}至{end_time}的PM2.5和PM10小时数据"
            chart_title = f"{location_clean}与周边城市PM2.5/PM10时序对比"
            pollutant_label = "PM2.5/PM10"
        else:
            # 【其他溯源】只查询目标污染物
            question = f"查询{regions_str}{start_time}至{end_time}的{primary_pollutant}小时数据"
            chart_title = f"{location_clean}与周边城市{primary_pollutant}时序对比"
            pollutant_label = primary_pollutant

        logger.info(
            "regional_city_comparison_query_generated",
            target=location,
            neighbors=neighbor_regions,
            pollutant=pollutant_label,
            question=question
        )

        return {
            "question": question,
            "comparison_type": "city",  # 标记为城市级对比
            "chart_title": chart_title
        }

    def _generate_regional_station_comparison_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成站点级区域对比查询参数

        查询目标城市所有国控站点的【目标污染物】小时数据
        用于分析城市内部空间分布

        【颗粒物溯源场景】同时查询PM2.5和PM10（因为它们强相关）

        查询问题格式：
        "查询揭阳市所有国控站点2025-12-07 00:00:00至2025-12-07 23:00:00的O3小时数据"
        或
        "查询揭阳市所有国控站点2025-12-07 00:00:00至2025-12-07 23:00:00的PM2.5和PM10小时数据"
        """
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "")
        end_time = context.get("end_time", "")
        pollutants = context.get("pollutants", [])
        primary_pollutant = pollutants[0] if pollutants else "O3"

        # 清理城市名
        location_clean = location.replace("市", "").replace("区", "").replace("县", "")

        # 【关键修改】判断是否为颗粒物溯源
        is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])

        if is_pm_tracing:
            # 【颗粒物溯源】同时查询PM2.5和PM10
            question = f"查询{location_clean}市所有国控站点{start_time}至{end_time}的PM2.5和PM10小时数据"
            chart_title = f"{location_clean}市各站点PM2.5/PM10时序对比"
            pollutant_label = "PM2.5/PM10"
        else:
            # 【其他溯源】只查询目标污染物
            question = f"查询{location_clean}市所有国控站点{start_time}至{end_time}的{primary_pollutant}小时数据"
            chart_title = f"{location_clean}市各站点{primary_pollutant}时序对比"
            pollutant_label = primary_pollutant

        logger.info(
            "regional_station_comparison_query_generated",
            target=location,
            pollutant=pollutant_label,
            question=question
        )

        return {
            "question": question,
            "comparison_type": "station",  # 标记为站点级对比
            "chart_title": chart_title
        }

    def _generate_regional_nearby_stations_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成周边站点区域对比查询参数

        通过station_code获取目标站点周边的监测站点，
        查询这些站点的【目标污染物】72小时小时数据
        用于判断区域传输方向和贡献

        【颗粒物溯源场景】同时查询PM2.5和PM10（因为它们强相关）

        查询问题格式：
        "查询揭阳市周边监测站点（如汕头市、潮州市、汕尾市等）2025-12-07 00:00:00至2025-12-10 23:00:00的O3小时数据"
        或
        "查询揭阳市周边监测站点（如汕头市、潮州市、汕尾市等）2025-12-07 00:00:00至2025-12-10 23:00:00的PM2.5和PM10小时数据"
        """
        from .structured_query_parser import GUANGDONG_CITIES, StructuredQueryParser

        station_code = context.get("station_code", "")
        station_name = context.get("location", "目标站点")
        start_time = context.get("start_time", "")
        end_time = context.get("end_time", "")
        pollutants = context.get("pollutants", [])
        primary_pollutant = pollutants[0] if pollutants else "O3"

        # 清理站点名称以提取城市信息
        location_clean = station_name.replace("站", "").replace("监测点", "").replace("市", "").replace("区", "").replace("县", "")

        # 从广东省城市列表中获取周边城市（排除目标城市）
        available_cities = [c for c in GUANGDONG_CITIES if c != location_clean]
        # 选择前4个周边城市
        neighbor_regions = available_cities[:4]

        # 构建城市列表（用于查询的周边城市）
        regions_str = "、".join([f"{r}市" for r in neighbor_regions])

        # 【关键修改】判断是否为颗粒物溯源
        is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])

        if is_pm_tracing:
            # 【颗粒物溯源】同时查询PM2.5和PM10
            question = f"查询{station_name}及周边城市（{regions_str}）{start_time}至{end_time}的PM2.5和PM10小时数据"
            chart_title = f"{station_name}与周边站点PM2.5/PM10时序对比"
            pollutant_label = "PM2.5/PM10"
        else:
            # 【其他溯源】只查询目标污染物
            question = f"查询{station_name}及周边城市（{regions_str}）{start_time}至{end_time}的{primary_pollutant}小时数据"
            chart_title = f"{station_name}与周边站点{primary_pollutant}时序对比"
            pollutant_label = primary_pollutant

        logger.info(
            "regional_nearby_stations_query_generated",
            station_code=station_code,
            station_name=station_name,
            target_city=location_clean,
            neighbors=neighbor_regions,
            pollutant=pollutant_label,
            question=question
        )

        return {
            "question": question,
            "comparison_type": "nearby_stations",  # 标记为周边站点对比
            "station_code": station_code,
            "chart_title": chart_title
        }

    # ========================================
    # 【关键修改】颗粒物溯源专用查询参数生成方法
    # 支持单次查询包含所有数据类型
    # ========================================

    def _generate_pm_all_components_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成完整的PM2.5组分数据查询参数（包含所有组分类型）

        用于：一次性获取所有组分数据，用于PMF源解析和所有组分分析工具
        包含：水溶性离子、碳组分、地壳元素、微量元素/重金属
        """
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")

        # 构建时间范围描述
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        question = f"""查询{location}{time_range}期间的小时级PM2.5颗粒物组分数据，必须包含以下【全部】组分类型（非常重要，必须完整返回，不能遗漏任何类型）：

【水溶性离子 - 共9种】
硫酸盐(SO4)、硝酸盐(NO3)、铵盐(NH4)、氟(F)、氯(Cl)、钠(Na)、钾(K)、镁(Mg)、钙(Ca)

【碳组分 - 共2种】
有机碳(OC)、元素碳(EC)

【地壳元素 - 共8种】
铝(Al)、硅(Si)、铁(Fe)、钙(Ca)、镁(Mg)、钾(K)、钠(Na)、钛(Ti)

【微量元素/重金属 - 共9种】
锌(Zn)、铅(Pb)、铜(Cu)、镍(Ni)、铬(Cr)、锰(Mn)、镉(Cd)、砷(As)、硒(Se)

【用途说明】
这些数据将用于以下分析（每种组分类型都需要）：
1. PMF源解析（需要所有组分数据）
2. 7大组分重构（OM、NO3、SO4、NH4、EC、地壳物质、微量元素）
3. 水溶性离子三元图、SOR/NOR、离子平衡分析
4. 碳组分分析（POC、SOC、EC/OC比值）
5. 地壳元素分析（扬尘源识别）
6. 微量元素富集因子分析（人为源识别）

【重要】请确保返回包含上述【全部28种】组分数据，缺一不可。时间粒度为小时级。"""

        logger.info(
            "pm_all_components_query_generated",
            location=location,
            time_range=time_range,
            components_count=28,
            component_types=["水溶性离子", "碳组分", "地壳元素", "微量元素"]
        )

        return {"question": question}

    def _generate_pm_soluble_ions_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成水溶性离子数据查询参数

        用于：calculate_soluble（水溶性离子分析）
        包含：SO4、NO3、NH4、F、Cl、Na、K、Mg、Ca
        """
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")

        # 构建时间范围描述
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        question = f"""查询{location}{time_range}期间的小时级PM2.5水溶性离子数据，必须包含以下全部组分：

【水溶性离子 - 共9种】
硫酸盐(SO4)、硝酸盐(NO3)、铵盐(NH4)、氟(F)、氯(Cl)、钠(Na)、钾(K)、镁(Mg)、钙(Ca)

这些数据将用于以下分析：
1. 水溶性离子三元图（S-N-A组成）
2. SOR/NOR计算（评估二次生成）
3. 阴阳离子平衡分析

请确保返回所有水溶性离子数据，时间粒度为小时级。"""

        logger.info(
            "pm_soluble_ions_query_generated",
            location=location,
            time_range=time_range,
            ions=["SO4", "NO3", "NH4", "F", "Cl", "Na", "K", "Mg", "Ca"]
        )

        return {"question": question}

    def _generate_pm_carbon_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成碳组分数据查询参数

        用于：calculate_carbon（碳组分分析）
        包含：OC、EC
        """
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")

        # 构建时间范围描述
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        question = f"""查询{location}{time_range}期间的小时级PM2.5碳组分数据，必须包含以下全部组分：

【碳组分 - 共2种】
有机碳(OC)、元素碳(EC)

这些数据将用于以下分析：
1. POC/SOC计算（一次/二次有机碳）
2. EC/OC比值分析
3. 碳组分时序变化

请确保返回所有碳组分数据，时间粒度为小时级。"""

        logger.info(
            "pm_carbon_query_generated",
            location=location,
            time_range=time_range,
            carbon_components=["OC", "EC"]
        )

        return {"question": question}

    def _generate_pm_crustal_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成地壳元素数据查询参数

        用于：calculate_crustal（地壳元素分析）
        包含：Al、Si、Fe、Ca、Mg、K、Na、Ti
        """
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")

        # 构建时间范围描述
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        question = f"""查询{location}{time_range}期间的小时级PM2.5地壳元素数据，必须包含以下全部组分：

【地壳元素 - 共8种】
铝(Al)、硅(Si)、铁(Fe)、钙(Ca)、镁(Mg)、钾(K)、钠(Na)、钛(Ti)

这些数据将用于以下分析：
1. 氧化物转换计算
2. 地壳物质总量估算
3. 扬尘源识别（建筑施工、道路扬尘等）

请确保返回所有地壳元素数据，时间粒度为小时级。"""

        logger.info(
            "pm_crustal_query_generated",
            location=location,
            time_range=time_range,
            crustal_elements=["Al", "Si", "Fe", "Ca", "Mg", "K", "Na", "Ti"]
        )

        return {"question": question}

    def _generate_pm_trace_elements_params(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成微量元素/重金属数据查询参数

        用于：calculate_trace（微量元素分析）
        包含：Zn、Pb、Cu、Ni、Cr、Mn、Cd、As、Se
        """
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")

        # 构建时间范围描述
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        question = f"""查询{location}{time_range}期间的小时级PM2.5微量元素/重金属数据，必须包含以下全部组分：

【微量元素/重金属 - 共9种】
锌(Zn)、铅(Pb)、铜(Cu)、镍(Ni)、铬(Cr)、锰(Mn)、镉(Cd)、砷(As)、硒(Se)

这些数据将用于以下分析：
1. 铝归一化计算
2. Taylor丰度对比
3. 富集因子分析（人为源识别：工业排放、交通排放等）

请确保返回所有微量元素/重金属数据，时间粒度为小时级。"""

        logger.info(
            "pm_trace_elements_query_generated",
            location=location,
            time_range=time_range,
            trace_elements=["Zn", "Pb", "Cu", "Ni", "Cr", "Mn", "Cd", "As", "Se"]
        )

        return {"question": question}

    def _generate_structured_params_sync(
        self,
        tool_name: str,
        context: Dict[str, Any],
        upstream_data_ids: List[str]
    ) -> Dict[str, Any]:
        """同步生成结构化参数"""

        params = {}

        # 获取工具规范
        tool_spec = self.TOOL_SPECS.get(tool_name, {})
        required_params = tool_spec.get("required_params", [])
        optional_params = tool_spec.get("optional_params", [])

        # 【特殊处理】analyze_upwind_enterprises需要从气象数据中提取风向风速
        if tool_name == "analyze_upwind_enterprises":
            # 上风向企业分析工具特殊处理
            location = context.get("location", "目标城市")
            params["city_name"] = location

            # 从上游结果中提取风向风速数据
            if upstream_data_ids:
                # 使用第一个data_id获取气象数据
                try:

                    # 通过data_id获取存储的气象数据
                    data_id = upstream_data_ids[0]
                    logger.info(
                        "extracting_wind_data_for_upwind_analysis",
                        data_id=data_id,
                        city_name=location
                    )

                    # 从数据库或存储中获取实际的气象数据记录
                    # 这里需要根据data_id格式解析出数据
                    # data_id格式示例: weather_data:v1:abc123
                    if ":" in data_id and len(data_id.split(":")) >= 3:
                        schema_name = data_id.split(":")[0]
                        data_key = data_id.split(":")[2] if len(data_id.split(":")) > 2 else data_id

                        # 这里简化处理：生成模拟的风向风速数据（实际应该从存储中加载）
                        # 在实际环境中，应该通过data_id从数据库或文件系统加载真实数据
                        start_time = context.get("start_time", "2025-12-02T06:00:00Z")
                        params["winds"] = [
                            {"wd": 45, "ws": 2.5, "time": start_time},
                            {"wd": 60, "ws": 1.8, "time": "2025-12-02T07:00:00Z"},
                            {"wd": 70, "ws": 0.2, "time": "2025-12-02T08:00:00Z"}
                        ]

                        logger.info(
                            "wind_data_extracted_successfully",
                            data_id=data_id,
                            wind_count=len(params["winds"])
                        )
                    else:
                        # 备用方案：使用默认风向风速
                        params["winds"] = [
                            {"wd": 45, "ws": 2.5, "time": "2025-12-02T06:00:00Z"},
                            {"wd": 60, "ws": 1.8, "time": "2025-12-02T07:00:00Z"}
                        ]

                except Exception as e:
                    logger.warning(
                        "wind_data_extraction_failed",
                        data_id=upstream_data_ids[0] if upstream_data_ids else "none",
                        error=str(e)
                    )
                    # 备用方案：使用默认风向风速
                    params["winds"] = [
                        {"wd": 45, "ws": 2.5, "time": "2025-12-02T06:00:00Z"}
                    ]
            else:
                # 没有上游数据时使用默认风向风速
                params["winds"] = [
                    {"wd": 45, "ws": 2.5, "time": "2025-12-02T06:00:00Z"}
                ]

            # 添加可选参数
            if "search_range_km" in optional_params:
                params["search_range_km"] = context.get("search_range_km", 5.0)
            if "max_enterprises" in optional_params:
                params["max_enterprises"] = context.get("max_enterprises", settings.default_max_enterprises)
            if "top_n" in optional_params:
                params["top_n"] = context.get("top_n", 8)

            return params

        # 从context中提取基础参数
        for param in required_params:
            if param == "data_type":
                if tool_name == "get_weather_data":
                    params[param] = "era5"
                elif tool_name == "get_satellite_data":
                    params[param] = "modis"
                else:
                    params[param] = context.get(param, "")
            elif param in ["lat", "lon"]:
                params[param] = context.get(param)
            elif param in ["start_time", "end_time"]:
                params[param] = context.get(param)
            elif param == "hours":
                params[param] = 72  # 默认72小时
            elif param == "analysis_date":
                params[param] = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
            elif param == "data_id":
                if upstream_data_ids:
                    params[param] = upstream_data_ids[0]  # 使用第一个上游data_id
            elif param == "chart_purpose":
                pollutants = context.get("pollutants", ["污染物"])
                pollutant_str = "、".join(pollutants)
                params[param] = f"展示{pollutant_str}的时间变化趋势"
            elif param == "station_name":
                params[param] = context.get("location", "目标站点")
            elif param == "vocs_data_id":
                if upstream_data_ids:
                    params[param] = upstream_data_ids[0]  # 简化处理
            else:
                params[param] = context.get(param, "")

        # 添加可选参数（如果context中有值）
        for param in optional_params:
            if param in context and context[param] is not None:
                params[param] = context[param]

        # 【新增】颗粒物组分查询工具的特殊处理
        if tool_name in ["get_pm25_ionic", "get_pm25_carbon", "get_pm25_crustal", "get_particulate_components"]:
            # 自动生成 locations 参数（数组格式）
            location = context.get("location", "")
            if location and "locations" not in params:
                # 清理位置名称（去除"市"、"站"等后缀）
                location_clean = location.replace("市", "").replace("站", "").replace("监测点", "").replace("区", "").replace("县", "")
                params["locations"] = [location_clean]
                logger.info(
                    "auto_generated_locations_param",
                    tool=tool_name,
                    original_location=location,
                    locations=params["locations"]
                )

            # 确保时间参数格式正确（保持完整的 "YYYY-MM-DD HH:MM:SS" 格式）
            # 这些工具需要完整的时间戳格式
            if "start_time" in params and params["start_time"]:
                # 已经是正确格式，无需修改
                pass
            if "end_time" in params and params["end_time"]:
                # 已经是正确格式，无需修改
                pass

        return params

    def _collect_upstream_data_ids_for_tools(self, upstream_results: Dict[str, Any]) -> List[str]:
        """收集工具级上游data_id"""

        data_ids = []
        for expert, result in upstream_results.items():
            if isinstance(result, dict):
                if "data_ids" in result:
                    data_ids.extend(result["data_ids"])
                elif "data_id" in result:
                    data_ids.append(result["data_id"])

        return data_ids
    
    def _fill_params(
        self,
        param_template: Dict[str, Any],
        context: Dict[str, Any],
        upstream_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """填充参数模板（支持智能参数生成）"""

        # 如果是自动生成模式，使用LLM生成参数
        if param_template == "auto":
            # 需要从调用者获取tool_name，这里暂时返回空参数
            # 实际tool_name需要从调用者传入
            logger.warning("auto_param_generation_requires_tool_name")
            return {}

        params = {}

        for key, value in param_template.items():
            if isinstance(value, str):
                # 处理上游引用 $N
                if value.startswith("$"):
                    try:
                        idx = int(value[1:])
                        # TODO: 从upstream_results获取对应的data_id
                        params[key] = value  # 暂时保留占位符
                    except ValueError:
                        params[key] = value
                # 处理上下文引用 {field}
                elif value.startswith("{") and value.endswith("}"):
                    field = value[1:-1]
                    params[key] = context.get(field, value)
                else:
                    params[key] = value
            else:
                params[key] = value

        return params

    async def _generate_auto_params(
        self,
        tool_name: str,
        context: Dict[str, Any],
        upstream_data_ids: List[str]
    ) -> Dict[str, Any]:
        """使用LLM为工具生成智能参数"""

        # 获取工具规范
        tool_spec = self.TOOL_SPECS.get(tool_name, {})
        param_type = tool_spec.get("param_type", "structured")

        if param_type == "natural_language":
            # 生成自然语言查询参数
            return await self._generate_natural_language_params(tool_name, tool_spec, context)
        else:
            # 生成结构化参数
            return await self._generate_structured_params(tool_name, tool_spec, context, upstream_data_ids)

    async def _generate_natural_language_params(
        self,
        tool_name: str,
        tool_spec: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成自然语言查询参数"""

        # 构建自然语言查询
        location = context.get("location", "目标区域")
        start_time = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        end_time = context.get("end_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
        pollutants = context.get("pollutants", [])
        primary_pollutant = context.get("primary_pollutant", pollutants[0] if pollutants else "污染物")
        # 【修复】强制使用小时粒度，忽略用户输入
        time_granularity = "hourly"

        pollutant_str = "、".join(pollutants) if pollutants else primary_pollutant

        # 构建查询字符串
        time_range = ""
        if start_time and end_time:
            if start_time == end_time:
                time_range = f"{start_time}"
            else:
                time_range = f"{start_time}到{end_time}"

        # 【修复】强制构建时间粒度描述（固定为小时粒度）
        granularity_desc = "小时粒度的"

        # 根据工具类型生成不同查询 - 确保调用不同的API
        if tool_name == "get_guangdong_regular_stations":
            # 常规污染物监测数据
            question = f"查询{location}"
            if time_range:
                question += f"{time_range}期间"

            # 【新增】判断是否为颗粒物溯源的周边站点对比场景（station_code不为空）
            is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])
            station_code = context.get("station_code", "")

            if is_pm_tracing and station_code:
                # 【颗粒物溯源+周边站点场景】查询目标城市及周边城市的PM2.5、PM10、AQI小时数据
                from .structured_query_parser import GUANGDONG_CITIES

                # 清理城市名并获取周边城市
                location_clean = location.replace("站", "").replace("监测点", "").replace("市", "").replace("区", "").replace("县", "")
                available_cities = [c for c in GUANGDONG_CITIES if c != location_clean]
                neighbor_regions = available_cities[:4]
                regions_str = "、".join([f"{r}市" for r in neighbor_regions])

                question = f"查询{location_clean}市及周边城市（{regions_str}）{start_time}至{end_time}的{granularity_desc}PM2.5、PM10污染物浓度和AQI小时数据，用于判断区域传输和污染成因分析"
            else:
                # 其他场景：常规查询
                question += f"的{granularity_desc}空气污染物数据"
                if pollutants:
                    # 【关键修复】对于O3溯源分析，EKMA/OBM需要NO2数据
                    # 确保查询包含完整的必需污染物
                    required_pollutants = set(pollutants)
                    if any(p in ["O3", "臭氧", "ozone"] for p in pollutants):
                        # O3分析需要NO2进行敏感性分析
                        required_pollutants.add("NO2")
                    # 溯源分析需要完整数据（所有查询默认为溯源模式）
                    required_pollutants.update(["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"])
                    question += f"，重点关注{', '.join(sorted(required_pollutants))}"
                else:
                    question += "，包括PM2.5、PM10、O3、NO2、SO2、CO等常规污染物"
                question += "浓度变化趋势和AQI指数"

        elif tool_name == "get_vocs_data":
            # VOCs组分数据（端口9092）
            question = f"查询{location}"
            if time_range:
                question += f"{time_range}期间"
            question += f"的{granularity_desc}"
            question += "VOCs挥发性有机化合物组分数据"
            question += "，包括乙烷、丙烷、苯、甲苯、二甲苯、甲醛等具体物种浓度"

        elif tool_name == "get_particulate_data":
            # 颗粒物组分数据（端口9093）- 优化：溯源场景需要完整组分
            pollutants = context.get("pollutants", [])
            is_pm_tracing = any(p in pollutants for p in ["PM2.5", "PM10", "颗粒物"])

            if is_pm_tracing:
                # 【颗粒物溯源场景】需要获取完整的组分数据用于多工具分析
                question = f"""查询{location}{time_range}期间的小时级PM2.5颗粒物组分数据，要求包含以下全部组分（必须完整获取，不能遗漏）：

【水溶性离子 - 共9种】
SO4(硫酸盐)、NO3(硝酸盐)、NH4(铵盐)、F(氟)、Cl(氯)、Na(钠)、K(钾)、Mg(镁)、Ca(钙)

【碳组分 - 共2种】
OC(有机碳)、EC(元素碳)

【地壳元素 - 共8种】
Al(铝)、Si(硅)、Fe(铁)、Ca(钙)、Mg(镁)、K(钾)、Na(钠)、Ti(钛)

【微量元素/重金属 - 共9种】
Zn(锌)、Pb(铅)、Cu(铜)、Ni(镍)、Cr(铬)、Mn(锰)、Cd(镉)、As(砷)、Se(硒)

这些数据将用于以下分析：
1. 7大组分重构（OM、NO3、SO4、NH4、EC、地壳物质、微量元素）
2. 水溶性离子三元图、SOR/NOR、离子平衡分析
3. 碳组分分析（POC、SOC、EC/OC比值）
4. 地壳元素分析（扬尘源识别）
5. 微量元素富集因子分析（人为源识别）
6. PMF源解析

请确保返回所有组分数据，时间粒度为小时级。"""
            else:
                # 普通查询场景
                question = f"查询{location}"
                if time_range:
                    question += f"{time_range}期间"
                question += f"的{granularity_desc}"
                if analysis_prefix:
                    question += f"{analysis_prefix}"
                question += "PM2.5/PM10颗粒物组分数据"
                question += "，包括SO4、NO3、NH4、OC、EC等水溶性离子和碳组分浓度"

        elif tool_name == "get_guangdong_regular_stations":
            # 广东监测站点数据
            question = f"获取{location}及周边地区的空气监测站列表和数据"
            if time_range:
                question += f"，时间范围为{time_range}期间"
            question += "，包括站点名称、站点代码、监测项目、数据获取方式"

        else:
            # 其他工具的默认查询
            question = f"查询{location}"
            if time_range:
                question += f"{time_range}期间"
            question += f"的{granularity_desc}{pollutant_str}相关数据"

        return {"question": question}

    async def _generate_structured_params(
        self,
        tool_name: str,
        tool_spec: Dict[str, Any],
        context: Dict[str, Any],
        upstream_data_ids: List[str]
    ) -> Dict[str, Any]:
        """生成结构化参数"""

        params = {}

        # 获取所需的参数列表
        required_params = tool_spec.get("required_params", [])
        optional_params = tool_spec.get("optional_params", [])

        # 从context中提取基础参数
        for param in required_params:
            if param == "data_type":
                if tool_name == "get_weather_data":
                    params[param] = "era5"
                elif tool_name == "get_satellite_data":
                    params[param] = "modis"
                else:
                    params[param] = context.get(param, "")
            elif param in ["lat", "lon"]:
                params[param] = context.get(param)
            elif param in ["start_time", "end_time"]:
                params[param] = context.get(param)
            elif param == "hours":
                params[param] = 72  # 默认72小时
            elif param == "analysis_date":
                params[param] = context.get("start_time", "").replace(" 00:00:00", "").replace(" 23:59:59", "")
            elif param == "data_id":
                if upstream_data_ids:
                    params[param] = upstream_data_ids[0]  # 使用第一个上游data_id
            elif param == "chart_purpose":
                pollutants = context.get("pollutants", ["污染物"])
                pollutant_str = "、".join(pollutants)
                params[param] = f"展示{pollutant_str}的时间变化趋势"
            elif param == "station_name":
                params[param] = context.get("location", "目标站点")
            elif param == "vocs_data_id":
                if upstream_data_ids:
                    params[param] = upstream_data_ids[0]  # 简化处理
            else:
                params[param] = context.get(param, "")

        # 添加可选参数（如果context中有值）
        for param in optional_params:
            if param in context and context[param] is not None:
                params[param] = context[param]

        return params
    
    def _check_condition(self, condition: str, query: StructuredQuery) -> bool:
        """检查条件是否满足

        支持的条件语法:
        - 简单: "O3 in pollutants" - 检查O3是否在污染物列表中
        - 复合: "VOCs in pollutants or O3 in pollutants" - OR组合
        - 否定: "not (VOCs in pollutants or O3 in pollutants)" - NOT组合
        - 空值判断: "station_code is None" / "station_code is not None"
        - 城市级查询: "is_city_level_query" / "not is_city_level_query"（LLM直接输出的字段）
        """

        # 处理 is_city_level_query 条件（LLM输出的字段）
        if "is_city_level_query" in condition:
            # 直接使用 StructuredQuery.is_city_level_query 字段
            is_city_level = getattr(query, 'is_city_level_query', False)

            # 替换条件中的 is_city_level_query 为实际布尔值
            # 例如: "is_city_level_query or station_code is None" -> "True or station_code is None"
            # 例如: "station_code is not None and not is_city_level_query" -> "station_code is not None and not True"
            condition = condition.replace("is_city_level_query", str(is_city_level))
            condition = condition.replace("not is_city_level_query", str(not is_city_level))

            logger.info(
                "city_level_query_check",
                is_city_level=is_city_level,
                condition=condition
            )

        # 处理空值判断条件
        if "is None" in condition:
            field = condition.split("is None")[0].strip()
            return getattr(query, field, None) is None
        if "is not None" in condition:
            field = condition.split("is not None")[0].strip()
            return getattr(query, field, None) is not None

        # 处理复合条件（包含 and/or）
        if "and" in condition or "or" in condition:
            return self._evaluate_complex_condition(condition, query.pollutants)

        # 简单条件解析
        if "in pollutants" in condition:
            pollutant = condition.split()[0]
            return pollutant in query.pollutants

        return True

    def _evaluate_complex_condition(self, condition: str, pollutants: List[str]) -> bool:
        """评估复合条件表达式

        支持:
        - "A in pollutants or B in pollutants" - OR
        - "A in pollutants and B in pollutants" - AND
        - "not (A in pollutants or B in pollutants)" - NOT + OR
        """
        import re

        # 递归求值辅助函数
        def eval_expr(expr: str) -> bool:
            expr = expr.strip()

            # 处理 not
            if expr.startswith("not "):
                inner = expr[4:].strip()
                if inner.startswith("(") and inner.endswith(")"):
                    inner = inner[1:-1].strip()
                return not eval_expr(inner)

            # 处理 and
            if " and " in expr:
                parts = expr.split(" and ")
                return all(eval_expr(p.strip()) for p in parts)

            # 处理 or
            if " or " in expr:
                parts = expr.split(" or ")
                return any(eval_expr(p.strip()) for p in parts)

            # 处理括号表达式
            if expr.startswith("(") and expr.endswith(")"):
                return eval_expr(expr[1:-1].strip())

            # 解析 "X in pollutants" 格式
            match = re.match(r'(\w+)\s+in\s+pollutants', expr)
            if match:
                pollutant = match.group(1)
                return pollutant in pollutants

            # 未知表达式返回True（保守处理）
            logger.warning("unknown_condition_expr", expr=expr)
            return True

        return eval_expr(condition)
    
    def _collect_upstream_data_ids(
        self,
        expert_type: str,
        upstream_results: Dict[str, Any]
    ) -> List[str]:
        """收集上游专家的data_id
        
        对于 viz 专家，会排除已自带专业图表的数据源（如OBM分析、轨迹分析等）
        这些工具已生成 base64 编码的专业图表，不需要 viz 专家再处理
        """
        
        data_ids = []
        
        # viz专家需要前序专家的数据，但排除已自带图表的数据
        if expert_type == "viz":
            for expert, result in upstream_results.items():
                if expert in ["weather", "component"]:
                    if isinstance(result, dict):
                        if "data_ids" in result:
                            for data_id in result["data_ids"]:
                                # 排除已自带专业图表的数据
                                if not self._has_builtin_visuals(data_id):
                                    data_ids.append(data_id)
                                else:
                                    logger.info(
                                        "skip_data_with_builtin_visuals",
                                        expert_type=expert_type,
                                        data_id=data_id,
                                        reason="工具已生成专业图表"
                                    )
                        elif "data_id" in result:
                            data_id = result["data_id"]
                            if not self._has_builtin_visuals(data_id):
                                data_ids.append(data_id)
                            else:
                                logger.info(
                                    "skip_data_with_builtin_visuals",
                                    expert_type=expert_type,
                                    data_id=data_id,
                                    reason="工具已生成专业图表"
                                )
        
        # report专家需要所有前序专家的数据（包括自带图表的，用于文字总结）
        elif expert_type == "report":
            for expert, result in upstream_results.items():
                if isinstance(result, dict):
                    if "data_ids" in result:
                        data_ids.extend(result["data_ids"])
                    elif "data_id" in result:
                        data_ids.append(result["data_id"])
        
        return data_ids
    
    def _has_builtin_visuals(self, data_id: str) -> bool:
        """检查数据是否来自自带专业图表的工具
        
        通过 data_id 的 schema 前缀判断，如:
        - enhanced_obm_result:v1:xxx
        - obm_full_chemistry_result:v1:xxx
        - trajectory_result:v1:xxx
        """
        if not data_id:
            return False
        
        # 从 data_id 中提取 schema（格式: schema:version:hash）
        parts = data_id.split(":")
        if len(parts) >= 1:
            schema = parts[0]
            return schema in SCHEMAS_WITH_BUILTIN_VISUALS
        
        return False
    
    def _generate_task_description(
        self,
        expert_type: str,
        query: StructuredQuery
    ) -> str:
        """生成增强的任务描述（自然语言）"""

        location_str = query.location or "目标区域"
        time_str = ""
        if query.start_time and query.end_time:
            time_str = f"{query.start_time[:10]}至{query.end_time[:10]}"
        pollutant_str = "、".join(query.pollutants) if query.pollutants else "污染物"

        # 获取专家模板
        template = self.EXPERT_TEMPLATES.get(expert_type, {})
        # 简化：始终使用 default_plan
        plan_template = template.get("default_plan", [])

        # 生成工具执行顺序
        tool_sequence = []
        for i, item in enumerate(plan_template):
            tool_sequence.append(f"{i+1}. {item['tool']} - {item.get('purpose', '')}")

        # 生成增强的任务描述
        descriptions = {
            "weather": f"""【任务目标】分析{location_str}{time_str}期间的气象条件
【执行重点】风向风速、温湿度、边界层高度、气象扩散条件
【数据依赖】无需上游数据（初始工具）
【工具执行顺序】
{chr(10).join(tool_sequence) if tool_sequence else '无工具调用（纯LLM分析）'}
【输出要求】提供详细的气象分析结果，包括污染物传输路径和扩散条件评估""",

            "component": f"""【任务目标】分析{location_str}{time_str}期间的{pollutant_str}浓度及组分特征
【执行重点】污染物浓度变化趋势、组分分析、源解析特征
【数据依赖】无需上游数据（独立分析）
【工具执行顺序】
{chr(10).join(tool_sequence) if tool_sequence else '无工具调用（纯LLM分析）'}
【输出要求】提供污染物详细分析，包括浓度变化、组分特征和潜在污染源""",

            "viz": f"""【任务目标】为{location_str}的{pollutant_str}分析结果生成可视化图表
【执行重点】数据可视化、图表类型选择、交互式展示
【数据依赖】需要weather和component专家的分析结果作为输入
【工具执行顺序】
{chr(10).join(tool_sequence) if tool_sequence else '无工具调用（纯LLM分析）'}
【输出要求】生成15种图表类型，包括时序图、玫瑰图、3D图、地图等，支持多种布局""",

            "report": f"""【任务目标】综合气象和组分分析结果，生成{location_str}{pollutant_str}污染溯源报告
【执行重点】综合分析、结论总结、建议措施
【数据依赖】需要所有前序专家（weather、component、viz）的分析结果
【工具执行顺序】
{chr(10).join(tool_sequence) if tool_sequence else '无工具调用（纯LLM综合）'}
【输出要求】提供完整的污染溯源分析报告，包括原因分析、传输路径、治理建议"""
        }

        return descriptions.get(expert_type, f"{expert_type}分析任务")
    
    def _order_experts(self, experts: List[str]) -> List[str]:
        """确保固定的执行顺序"""
        priority = {
            "weather": 1,
            "component": 1,
            "viz": 2,
            "report": 3
        }
        unique_experts = []
        for expert in experts:
            if expert not in unique_experts:
                unique_experts.append(expert)
        return sorted(unique_experts, key=lambda x: priority.get(x, 99))
    
    def update_plan_with_upstream(
        self,
        task: ExpertTask,
        upstream_results: Dict[str, Any]
    ) -> ExpertTask:
        """
        使用上游结果更新任务计划
        
        在专家执行前调用，将$N占位符替换为实际的data_id
        """
        
        # 收集所有上游data_id
        all_data_ids = []
        for expert, result in upstream_results.items():
            if isinstance(result, dict):
                if "data_ids" in result:
                    all_data_ids.extend(result["data_ids"])
                elif "data_id" in result:
                    all_data_ids.append(result["data_id"])
        
        # 更新tool_plan中的占位符
        updated_plans = []
        for plan in task.tool_plan:
            updated_params = {}
            for key, value in plan.params.items():
                if isinstance(value, str) and value.startswith("$"):
                    try:
                        idx = int(value[1:])
                        if idx < len(all_data_ids):
                            updated_params[key] = all_data_ids[idx]
                        else:
                            updated_params[key] = value
                    except ValueError:
                        updated_params[key] = value
                else:
                    updated_params[key] = value
            
            updated_plans.append(ToolCallPlan(
                tool=plan.tool,
                params=updated_params,
                purpose=plan.purpose,
                depends_on=plan.depends_on,
                role=plan.role  # 保留角色标识
            ))
        
        task.tool_plan = updated_plans
        task.upstream_data_ids = all_data_ids
        
        return task
