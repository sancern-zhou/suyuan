"""
PM2.5地壳元素查询工具
查询铝(Al)、硅(Si)、钙(Ca)、铁(Fe)、钛(Ti)、钾(K)等地壳元素
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
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


class GetPM25CrustalTool(LLMTool):
    """PM2.5地壳元素查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_pm25_crustal",
            "description": (
                "查询PM2.5地壳元素数据（Al/Si/Fe/Ca/Ti/K等），用于扬尘源解析和地壳元素分析。"
                "需要地壳元素/重金属数据时优先使用；locations可自动映射站点。"
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
                        "description": "数据质量：0原始，1审核；地壳元素数值需用1，默认1",
                        "default": 1
                    },
                    "time_granularity": {
                        "type": "integer",
                        "enum": [0],
                        "description": "时间粒度固定0；其他粒度会返回占位符",
                        "default": 0
                    },
                    "elements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "元素列表，如['Al','Si','Fe','Ca','Ti','Mn']",
                        "default": ["Al", "Si", "Fe", "Ca", "Ti", "Mn"]
                    }
                },
                "required": ["start_time", "end_time"],
            },
        }

        super().__init__(
            name="get_pm25_crustal",
            description="Query PM2.5 crustal elements for dust source analysis.",
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
        data_type: int = 1,  # 默认使用审核数据（地壳元素数值仅在审核数据中）
        time_granularity: Union[int, str] = 0,  # 默认使用0（小时，返回数值）
        elements: List[str] = None,
        **_: Any
    ) -> Dict[str, Any]:
        """执行地壳元素查询"""

        if elements is None:
            elements = ["Al", "Si", "Fe", "Ca", "Ti", "Mn"]

        # 时间粒度映射：字符串 -> 数字
        # 注意：地壳元素数据只在 dataType=0 时返回数值，其他粒度返回占位符
        time_granularity_map = {
            "hour": 0,
            "hourly": 0,
            "day": 0,    # 强制使用0（返回数值），而不是2（返回占位符）
            "daily": 0,
            "month": 0,
            "monthly": 0,
            "year": 0,
            "yearly": 0
        }

        # 如果是字符串，转换为数字
        if isinstance(time_granularity, str):
            original_value = time_granularity
            time_granularity = time_granularity_map.get(time_granularity.lower(), 1)
            logger.info(
                "time_granularity_converted",
                input=original_value,
                output=time_granularity
            )

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
            "pm25_crustal_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            elements=elements,
            time_granularity=time_granularity
        )

        client = get_particulate_api_client()

        # 地壳元素因子编码映射 (元素名 -> 因子编码)
        element_code_map = {
            "Al": "a20002",
            "Si": "a20119",
            "Ca": "a20029",
            "Fe": "a20111",
            "Ti": "a20095",
            "K": "a20068",
            "Mn": None,  # 锰可能需要其他编码
        }

        # 将请求的元素转换为因子编码
        detection_codes = []
        for elem in elements:
            element_code = element_code_map.get(elem)
            if element_code:
                detection_codes.append(element_code)

        # 如果没有匹配的编码，使用默认列表
        if not detection_codes:
            detection_codes = None  # 使用 API 默认值

        try:
            # 使用 particulate_api_client 的重金属分析方法
            api_result = client.get_heavy_metal_analysis(
                station=station,
                code=code,
                start_time=start_time,
                end_time=end_time,
                date_type=data_type,       # 数据质量：0=原始，1=审核（地壳元素数值需要1）
                data_type=time_granularity, # 时间粒度：0=小时(数值), 2=日(字符串占位符)
                detection_item_codes=detection_codes
            )

            if not api_result.get("success"):
                error_msg = api_result.get("error", "Unknown error")
                logger.error("crustal_api_call_failed", error=error_msg)
                return {
                    "success": False,
                    "error": f"API调用失败: {error_msg}",
                    "station": station,
                    "code": code
                }

            # 提取API响应
            api_response = api_result.get("api_response", {})
            if not api_response:
                return {
                    "success": False,
                    "error": "API返回空响应",
                    "station": station,
                    "code": code
                }

            # 提取记录
            records = []
            result = api_response.get("result", {})
            records = result.get("resultOne", [])

            if not records:
                return {
                    "success": False,
                    "error": "No crustal element records found",
                    "station": station,
                    "code": code,
                    "api_structure": list(api_response.get("result", {}).keys()) if isinstance(api_response, dict) else []
                }

            # 过滤掉所有 _Mark 字段
            records = _filter_mark_fields(records)
            logger.info("crustal_filtered", original_count=len(records), filtered_count=len(records))

            # 保存数据
            data_id = None
            file_path = None
            try:
                data_id = context.save_data(
                    data=records,
                    schema="particulate_unified",
                    metadata={
                        "component_type": "crustal",
                        "station": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "elements": elements
                    }
                )
            except Exception as save_error:
                logger.warning("pm25_crustal_save_failed", error=str(save_error))

            # 分析数据质量
            quality_report = self._analyze_quality(records, elements)

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
                "elements": elements,
                "quality_report": quality_report,
                "summary": f"[OK] 成功获取{len(records)}条PM2.5地壳元素数据，已保存为 {data_id}（路径: {file_path}）。",
                "metadata": {
                    "sample_record": sample_record
                }
            }

        except Exception as e:
            logger.error("pm25_crustal_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _analyze_quality(self, records: List[Dict[str, Any]], elements: List[str]) -> Dict[str, Any]:
        """分析数据质量"""
        if not records:
            return {}

        first = records[0]
        available_elements = [k for k in first.keys() if k not in ["Code", "StationName", "TimePoint", "DataType"]]

        result = {
            "total_records": len(records),
            "requested_elements": len(elements),
            "available_elements": len(available_elements),
            "element_fields": available_elements[:10]
        }

        # 统计每个元素的数据完整性
        for elem in elements:
            matching_fields = [f for f in available_elements if elem in f]
            if matching_fields:
                field = matching_fields[0]
                valid_count = sum(1 for r in records if r.get(field) not in ["—", "", None])
                result[elem] = {
                    "field": field,
                    "valid_count": valid_count,
                    "total": len(records),
                    "completeness": valid_count / len(records)
                }

        return result


def __init__() -> None:
    return GetPM25CrustalTool()
