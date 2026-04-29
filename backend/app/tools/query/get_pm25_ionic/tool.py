"""
PM2.5水溶性离子组分查询工具
查询F⁻、Cl⁻、NO₂⁻、NO₃⁻、SO₄²⁻、PO₄³⁻、Li⁺、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、Al³⁺等
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.particulate_api_client import get_particulate_api_client
from app.utils.particulate_geo_matcher import get_particulate_geo_matcher
from app.utils.particulate_city_mapper import get_particulate_city_mapper

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


def _filter_mark_fields(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """过滤掉所有 _Mark 字段

    Args:
        records: 原始记录列表

    Returns:
        过滤后的记录列表（不包含 _Mark 字段）
    """
    filtered_records = []
    for record in records:
        if isinstance(record, dict):
            # 创建新记录，排除所有 _Mark 字段
            filtered_record = {
                k: v for k, v in record.items()
                if not k.endswith('_Mark')
            }
            filtered_records.append(filtered_record)
        else:
            filtered_records.append(record)
    return filtered_records


class GetPM25IonicTool(LLMTool):
    """PM2.5水溶性离子组分查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_pm25_ionic",
            "description": (
                "查询PM2.5水溶性离子组分（SO4/NO3/NH4/F/Cl/Na/K/Mg/Ca等），用于PMF和二次气溶胶分析。"
                "需要离子组分数据时优先使用；locations可自动映射站点。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市或站点名称列表，可自动映射站点编码"
                    },
                    "station": {
                        "type": "string",
                        "description": "中文站点名；优先用locations"
                    },
                    "code": {
                        "type": "string",
                        "description": "站点编码；locations存在时可省略"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式YYYY-MM-DD HH:MM:SS"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式YYYY-MM-DD HH:MM:SS"
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "数据质量：0原始，1审核，默认0"
                    },
                    "time_type": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "时间粒度必须为整数：1小时，2日，3月，5年",
                        "examples": [2]  # 明确示例使用数字
                    }
                },
                "required": ["start_time", "end_time"],
            }
        }

        super().__init__(
            name="get_pm25_ionic",
            description="Query PM2.5 water-soluble ionic components for PMF analysis.",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            requires_context=True,
        )

    async def execute(
        self,
        context: "ExecutionContext",
        start_time: str,
        end_time: str,
        locations: Union[List[str], None] = None,
        station: Union[str, None] = None,
        code: Union[str, None] = None,
        data_type: int = 0,
        time_type: int = 1,
        **_: Any
    ) -> Dict[str, Any]:
        """执行水溶性离子查询"""

        # 参数处理：支持 locations 自动映射
        if locations:
            # 步骤1：城市名→站点名映射（如果是城市名）
            city_mapper = get_particulate_city_mapper()
            station_names = []

            for location in locations:
                # 尝试作为城市名映射到站点名
                station_name = city_mapper.city_to_station_name(location)
                if station_name:
                    # 成功映射：城市→站点
                    station_names.append(station_name)
                    logger.info(
                        "city_mapped_to_station",
                        city=location,
                        station=station_name
                    )
                else:
                    # 映射失败，假设本身就是站点名
                    station_names.append(location)
                    logger.info(
                        "location_assumed_as_station",
                        location=location
                    )

            # 步骤2：站点名→站点编码映射（使用组分站点映射器）
            particulate_geo_matcher = get_particulate_geo_matcher()
            try:
                station_codes = particulate_geo_matcher.stations_to_codes(station_names)
            except ValueError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "locations": locations,
                    "station_names": station_names
                }

            if not station_codes:
                return {
                    "success": False,
                    "error": f"无法将站点名称映射到组分站点编码: {station_names}（原始输入: {locations}）",
                    "locations": locations,
                    "station_names": station_names
                }

            # 使用第一个映射的编码和站点名
            code = station_codes[0]
            station = station_names[0]
        elif not (station and code):
            return {
                "success": False,
                "error": "必须提供 locations 参数，或者同时提供 station 和 code 参数"
            }

        logger.info(
            "pm25_ionic_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            time_type=time_type
        )

        client = get_particulate_api_client()

        # 调用API客户端的 get_ionic_analysis 方法
        # 该方法会自动处理Token验证和完整URL构建
        # time_type: 1=hour, 2=day, 3=month, 5=year (直接传递整数)
        api_result = client.get_ionic_analysis(
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_type=time_type,
            data_type=data_type
        )

        # 检查API调用结果
        if not api_result.get("success"):
            return {
                "success": False,
                "error": api_result.get("error", "Unknown API error"),
                "station": station,
                "code": code
            }

        api_response = api_result.get("api_response")

        # 添加调试日志
        logger.info("pm25_ionic_api_response", response=str(api_response))

        try:

            # 提取记录
            # API 响应格式: {"success": true, "result": {"resultOne": [], "resultTwo": {}, "resultThree": []}}
            records = []
            if isinstance(api_response, dict):
                # 直接从 result 字段获取
                result = api_response.get("result", {})
                if isinstance(result, dict):
                    records = result.get("resultOne", [])

                logger.info("pm25_ionic_records_extracted", count=len(records))

            if not records:
                return {
                    "success": False,
                    "error": "No ionic component records found",
                    "station": station,
                    "code": code
                }

            # 过滤掉所有 _Mark 字段
            records = _filter_mark_fields(records)
            logger.info("pm25_ionic_filtered", original_count=len(records), filtered_count=len(records))

            # 保存数据到上下文
            data_id = None
            file_path = None
            try:
                data_id = context.save_data(
                    data=records,
                    schema="particulate_unified",
                    metadata={
                        "component_type": "ionic",
                        "station": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "data_type": data_type,
                        "time_type": time_type
                    }
                )
            except Exception as save_error:
                logger.warning("pm25_ionic_save_failed", error=str(save_error))

            # 分析数据质量
            quality_report = self._analyze_quality(records)

            # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
            sample_record = None
            if records:
                first = records[0]
                sample_record = {
                    "timestamp": first.get("timestamp"),
                    "station_name": first.get("station_name"),
                    "measurements": first.get("measurements", {}),
                    "components": first.get("components")
                }

            return {
                "success": True,
                "data": records,
                "data_id": data_id,
                "file_path": file_path,
                "count": len(records),
                "station": station,
                "code": code,
                "data_type": data_type,
                "time_type": time_type,
                "quality_report": quality_report,
                "summary": f"[OK] 成功获取{len(records)}条PM2.5水溶性离子数据，已保存为 {data_id}（路径: {file_path}）。",
                "metadata": {
                    "sample_record": sample_record
                }
            }

        except Exception as e:
            logger.error("pm25_ionic_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _analyze_quality(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析数据质量"""
        if not records:
            return {}

        first = records[0]
        ionic_fields = [
            k for k in first.keys()
            if k not in ["Code", "StationName", "TimePoint", "TimeType", "DataType", "PM2_5", "PM₂.₅", "AQI"]
        ]

        # PMF核心组分
        pmf_components = {"SO4²⁻": "SO4", "NO₃⁻": "NO3", "NH₄⁺": "NH4"}
        found = {}
        for field, name in pmf_components.items():
            if field in first:
                valid_count = sum(1 for r in records if r.get(field) not in ["—", "", None])
                found[name] = {
                    "field": field,
                    "valid_count": valid_count,
                    "total": len(records),
                    "completeness": valid_count / len(records) if records else 0
                }

        return {
            "total_records": len(records),
            "ionic_fields": len(ionic_fields),
            "field_names": list(ionic_fields)[:15],
            "pmf_components": found
        }


def __init__() -> None:
    return GetPM25IonicTool()
