"""
图表数据目录 - 记录每类数据的标准字段和推荐模板

这是策略选择器的核心参考资料，定义了：
1. 每种数据类型的必需字段和可选字段
2. 推荐的图表模板和使用场景
3. 图表编码的标准配置

参考业界最佳实践，支持环境监测、气象、溯源分析等多种场景
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class ChartTemplate(BaseModel):
    """图表模板定义"""
    chart_type: str = ""  # 图表类型
    scenario: str = ""  # 使用场景描述
    priority: int = 1  # 优先级（1最高）
    special: bool = False  # 是否需要专门组件
    requires_map: bool = False  # 是否需要地图
    condition: Optional[str] = None  # 使用条件
    encoding_template: Dict[str, Any] = {}  # 编码模板


class DataCatalogEntry(BaseModel):
    """数据目录条目"""
    schema: str  # 数据类型
    description: str  # 描述
    required_fields: List[str]  # 必需字段
    optional_fields: List[str]  # 可选字段
    time_granularity: List[str]  # 时间粒度
    recommended_templates: List[ChartTemplate]  # 推荐模板
    sample_config: Dict[str, Any]  # 示例配置


# ============================================
# 图表数据目录（核心配置）
# ============================================

CHART_DATA_CATALOG: Dict[str, DataCatalogEntry] = {

    # ========== 环境监测数据 ==========

    "vocs": DataCatalogEntry(
        schema="vocs",
        description="VOCs组分数据",
        required_fields=["species_name", "concentration", "timestamp"],
        optional_fields=["station_name", "category", "unit"],
        time_granularity=["hourly", "daily"],
        recommended_templates=[
            ChartTemplate(
                chart_type="pie",
                scenario="组分占比",
                priority=1,
                encoding_template={
                    "theta": {"field": "concentration", "type": "quantitative"},
                    "color": {"field": "species_name", "type": "nominal"}
                }
            ),
            ChartTemplate(
                chart_type="timeseries",
                scenario="浓度趋势",
                priority=2,
                encoding_template={
                    "x": {"field": "timestamp", "type": "temporal"},
                    "y": {"field": "concentration", "type": "quantitative"},
                    "color": {"field": "species_name", "type": "nominal"}
                }
            ),
            ChartTemplate(
                chart_type="bar",
                scenario="物种对比",
                priority=3,
                encoding_template={
                    "x": {"field": "species_name", "type": "nominal"},
                    "y": {"field": "concentration", "type": "quantitative", "aggregate": "mean"}
                }
            )
        ],
        sample_config={
            "top_n": 10,
            "sort_by": "concentration",
            "sort_order": "descending"
        }
    ),

    "air_quality": DataCatalogEntry(
        schema="air_quality",
        description="环境空气质量监测数据",
        required_fields=["timePoint", "AQI"],
        optional_fields=["PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "station_name"],
        time_granularity=["hourly", "daily"],
        recommended_templates=[
            ChartTemplate(
                chart_type="timeseries",
                scenario="污染物时序",
                priority=1,
                encoding_template={
                    "x": {"field": "timePoint", "type": "temporal"},
                    "y": {"field": "PM2.5", "type": "quantitative"},
                    "color": {"field": "station_name", "type": "nominal"}
                }
            ),
            ChartTemplate(
                chart_type="bar",
                scenario="污染物对比",
                priority=2,
                encoding_template={
                    "x": {"field": "station_name", "type": "nominal"},
                    "y": {"field": "AQI", "type": "quantitative", "aggregate": "mean"}
                }
            ),
            ChartTemplate(
                chart_type="heatmap",
                scenario="时空分布",
                priority=3,
                special=True,
                encoding_template={
                    "x": {"field": "timePoint", "type": "temporal"},
                    "y": {"field": "station_name", "type": "nominal"},
                    "color": {"field": "PM2.5", "type": "quantitative"}
                }
            )
        ],
        sample_config={}
    ),

    "guangdong_stations": DataCatalogEntry(
        schema="guangdong_stations",
        description="广东省环境监测站点数据",
        required_fields=["station_name", "time_point"],
        optional_fields=["PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "AQI"],
        time_granularity=["hourly"],
        recommended_templates=[
            ChartTemplate(
                chart_type="timeseries",
                scenario="多站点时序",
                priority=1,
                encoding_template={
                    "x": {"field": "time_point", "type": "temporal"},
                    "y": {"field": "PM2.5", "type": "quantitative"},
                    "color": {"field": "station_name", "type": "nominal"}
                }
            ),
            ChartTemplate(
                chart_type="bar",
                scenario="站点对比",
                priority=2,
                encoding_template={
                    "x": {"field": "station_name", "type": "nominal"},
                    "y": {"field": "PM2.5", "type": "quantitative", "aggregate": "mean"}
                }
            ),
            ChartTemplate(
                chart_type="pie",
                scenario="站点浓度占比",
                priority=3,
                encoding_template={
                    "theta": {"field": "PM2.5", "type": "quantitative", "aggregate": "mean"},
                    "color": {"field": "station_name", "type": "nominal"}
                }
            ),
            ChartTemplate(
                chart_type="heatmap",
                scenario="时空热力图",
                priority=4,
                special=True,
                encoding_template={
                    "x": {"field": "time_point", "type": "temporal"},
                    "y": {"field": "station_name", "type": "nominal"},
                    "color": {"field": "PM2.5", "type": "quantitative"}
                }
            )
        ],
        sample_config={
            "max_stations": 15,
            "pollutant": "PM2.5"
        }
    ),

    # ========== 气象数据 ==========

    "meteorology": DataCatalogEntry(
        schema="meteorology",
        description="气象观测数据",
        required_fields=["timePoint", "windSpeed", "windDirection"],
        optional_fields=["temperature", "humidity", "pressure", "pbl", "station_name"],
        time_granularity=["hourly", "daily"],
        recommended_templates=[
            ChartTemplate(
                chart_type="wind_rose",
                scenario="风向玫瑰",
                priority=1,
                special=True,
                encoding_template={
                    "theta": {"field": "windDirection", "type": "quantitative"},
                    "radius": {"field": "windSpeed", "type": "quantitative"}
                }
            ),
            ChartTemplate(
                chart_type="timeseries",
                scenario="气象要素时序",
                priority=2,
                encoding_template={
                    "x": {"field": "timePoint", "type": "temporal"},
                    "y": {"field": "temperature", "type": "quantitative"}
                }
            ),
            ChartTemplate(
                chart_type="profile",
                scenario="边界层廓线",
                priority=3,
                special=True,
                condition="has_pbl_data",
                encoding_template={
                    "x": {"field": "pbl_value", "type": "quantitative"},
                    "y": {"field": "altitude", "type": "quantitative"}
                }
            )
        ],
        sample_config={}
    ),

    # ========== 溯源分析结果 ==========

    "pmf_result": DataCatalogEntry(
        schema="pmf_result",
        description="PMF源解析结果",
        required_fields=["source_name", "contribution_pct"],
        optional_fields=["timeseries", "concentration"],
        time_granularity=["daily", "monthly"],
        recommended_templates=[
            ChartTemplate(
                chart_type="pie",
                scenario="源贡献占比",
                priority=1,
                encoding_template={
                    "theta": {"field": "contribution_pct", "type": "quantitative"},
                    "color": {"field": "source_name", "type": "nominal"}
                }
            ),
            ChartTemplate(
                chart_type="bar",
                scenario="源贡献对比",
                priority=2,
                encoding_template={
                    "x": {"field": "source_name", "type": "nominal"},
                    "y": {"field": "contribution_pct", "type": "quantitative"}
                }
            ),
            ChartTemplate(
                chart_type="timeseries",
                scenario="源贡献时序",
                priority=3,
                condition="has_timeseries",
                encoding_template={
                    "x": {"field": "time", "type": "temporal"},
                    "y": {"field": "contribution", "type": "quantitative"},
                    "color": {"field": "source_name", "type": "nominal"}
                }
            )
        ],
        sample_config={}
    ),

    "obm_ofp_result": DataCatalogEntry(
        schema="obm_ofp_result",
        description="OBM/OFP分析结果",
        required_fields=["species_name", "ofp"],
        optional_fields=["category", "concentration"],
        time_granularity=["hourly", "daily"],
        recommended_templates=[
            ChartTemplate(
                chart_type="bar",
                scenario="物种OFP排名",
                priority=1,
                encoding_template={
                    "x": {"field": "species_name", "type": "nominal"},
                    "y": {"field": "ofp", "type": "quantitative"}
                }
            ),
            ChartTemplate(
                chart_type="pie",
                scenario="类别OFP占比",
                priority=2,
                encoding_template={
                    "theta": {"field": "ofp", "type": "quantitative", "aggregate": "sum"},
                    "color": {"field": "category", "type": "nominal"}
                }
            )
        ],
        sample_config={
            "top_n": 10,
            "sort_by": "ofp"
        }
    ),

    # ========== 溯源外部数据 ==========

    "dust_trajectory": DataCatalogEntry(
        schema="dust_trajectory",
        description="沙尘输送轨迹数据",
        required_fields=["latitude", "longitude", "altitude", "timePoint"],
        optional_fields=["trajectory_id", "pressure"],
        time_granularity=["hourly"],
        recommended_templates=[
            ChartTemplate(
                chart_type="map_trajectory",
                scenario="沙尘轨迹",
                priority=1,
                special=True,
                requires_map=True,
                encoding_template={
                    "longitude": {"field": "longitude", "type": "quantitative"},
                    "latitude": {"field": "latitude", "type": "quantitative"},
                    "color": {"field": "altitude", "type": "quantitative"}
                }
            )
        ],
        sample_config={}
    ),

    "fire_hotspots": DataCatalogEntry(
        schema="fire_hotspots",
        description="NASA FIRMS火点数据",
        required_fields=["latitude", "longitude", "brightness", "scan_time"],
        optional_fields=["confidence", "frp"],
        time_granularity=["daily"],
        recommended_templates=[
            ChartTemplate(
                chart_type="map_scatter",
                scenario="火点分布",
                priority=1,
                special=True,
                requires_map=True,
                encoding_template={
                    "longitude": {"field": "longitude", "type": "quantitative"},
                    "latitude": {"field": "latitude", "type": "quantitative"},
                    "size": {"field": "brightness", "type": "quantitative"},
                    "color": {"field": "confidence", "type": "quantitative"}
                }
            )
        ],
        sample_config={}
    )
}


# ============================================
# 辅助函数
# ============================================

def get_catalog_entry(schema: str) -> Optional[DataCatalogEntry]:
    """获取数据目录条目"""
    return CHART_DATA_CATALOG.get(schema)


def get_recommended_templates(schema: str, scenario: Optional[str] = None) -> List[ChartTemplate]:
    """
    获取推荐的图表模板

    Args:
        schema: 数据类型
        scenario: 使用场景（可选，用于过滤）

    Returns:
        按优先级排序的模板列表
    """
    entry = get_catalog_entry(schema)
    if not entry:
        return []

    templates = entry.recommended_templates

    # 如果指定场景，过滤匹配的模板
    if scenario:
        templates = [t for t in templates if scenario in t.scenario]

    # 按优先级排序
    templates.sort(key=lambda t: t.priority)

    return templates


def validate_data_fields(schema: str, data_fields: List[str]) -> Dict[str, Any]:
    """
    验证数据字段是否满足要求

    Args:
        schema: 数据类型
        data_fields: 实际数据字段列表

    Returns:
        {
            "valid": True/False,
            "missing_fields": [...],
            "available_templates": [...]
        }
    """
    entry = get_catalog_entry(schema)
    if not entry:
        return {
            "valid": False,
            "error": f"未知的数据类型: {schema}"
        }

    # 检查必需字段
    missing_fields = [f for f in entry.required_fields if f not in data_fields]

    if missing_fields:
        return {
            "valid": False,
            "missing_fields": missing_fields,
            "message": f"缺少必需字段: {', '.join(missing_fields)}"
        }

    # 检查可用的模板（考虑条件）
    available_templates = []
    for template in entry.recommended_templates:
        # 检查条件
        if template.condition:
            # 简单的条件检查
            if template.condition == "has_timeseries" and "timeseries" not in data_fields:
                continue
            if template.condition == "has_pbl_data" and "pbl" not in data_fields:
                continue

        available_templates.append(template)

    return {
        "valid": True,
        "missing_fields": [],
        "available_templates": available_templates
    }


def get_all_schemas() -> List[str]:
    """获取所有支持的数据类型"""
    return list(CHART_DATA_CATALOG.keys())


def get_catalog_summary() -> Dict[str, Any]:
    """获取数据目录摘要"""
    return {
        "total_schemas": len(CHART_DATA_CATALOG),
        "schemas": {
            schema: {
                "description": entry.description,
                "template_count": len(entry.recommended_templates),
                "required_fields_count": len(entry.required_fields)
            }
            for schema, entry in CHART_DATA_CATALOG.items()
        }
    }


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    # 示例1：查询VOCs数据的推荐模板
    print("=== VOCs推荐模板 ===")
    vocs_templates = get_recommended_templates("vocs")
    for template in vocs_templates:
        print(f"{template.priority}. {template.scenario} ({template.chart_type})")

    # 示例2：验证数据字段
    print("\n=== 数据字段验证 ===")
    result = validate_data_fields(
        "vocs",
        ["species_name", "concentration", "timestamp", "station_name"]
    )
    print(f"有效: {result['valid']}")
    print(f"可用模板数: {len(result.get('available_templates', []))}")

    # 示例3：获取目录摘要
    print("\n=== 目录摘要 ===")
    summary = get_catalog_summary()
    print(f"支持的数据类型数: {summary['total_schemas']}")
    for schema, info in summary['schemas'].items():
        print(f"  {schema}: {info['description']} ({info['template_count']}个模板)")
