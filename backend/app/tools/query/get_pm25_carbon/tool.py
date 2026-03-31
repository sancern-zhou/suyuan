"""
PM2.5碳组分查询工具（OC/EC）
查询有机碳(OC)和元素碳(EC)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.particulate_api_client import get_particulate_api_client
from app.utils.geo_matcher import get_geo_matcher
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


class GetPM25CarbonTool(LLMTool):
    """PM2.5碳组分（OC/EC）查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_pm25_carbon",
            "description": (
                "【结构化查询工具-优先使用】查询PM2.5碳组分数据 - 有机碳(OC)和元素碳(EC)。"
                ""
                "**优势：**"
                "- 参数精确，支持直接指定站点、时间范围、时间粒度"
                "- 数据格式标准化，自动保存为particulate_unified格式"
                "- 适用于PMF源解析和二次有机气溶胶分析"
                "- 支持城市名称自动映射到站点编码"
                ""
                "**关键词：** 碳组分、OC、EC、有机碳、元素碳"
                ""
                "**何时使用：** 用户需要OC/EC碳组分数据时，优先使用此工具而非自然语言查询工具"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Location names (city/station), e.g., ['东莞'], ['广州', '新兴']. Will be auto-mapped to StationCodes."
                    },
                    "station": {
                        "type": "string",
                        "description": "Station name in Chinese, e.g., '东莞', '揭阳', '新兴'. Use 'locations' for automatic mapping instead."
                    },
                    "code": {
                        "type": "string",
                        "description": "Station code, e.g., '1037b', '1042b'. Automatically mapped if 'locations' provided."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in format 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in format 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "Data type: 0=original, 1=audited (default: 0)"
                    },
                    "time_granularity": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "Time granularity (integer only): 1=hour, 2=day, 3=month, 5=year. IMPORTANT: Carbon component NUMERIC data is only available in hourly granularity (time_granularity=1 or 'hourly'). Daily/monthly/yearly data returns string placeholders. Default: 1",
                        "default": 1,
                        "examples": [1]  # 明确示例使用数字1
                    }
                },
                "required": ["start_time", "end_time"],
            },
        }

        super().__init__(
            name="get_pm25_carbon",
            description="Query PM2.5 carbon components (OC/EC) for PMF analysis.",
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
        time_granularity: Union[int, str] = 1,  # 支持字符串和数字
        **_: Any
    ) -> Dict[str, Any]:
        """执行碳组分查询"""

        # 时间粒度映射：字符串 -> 数字
        # 注意：碳组分数据只在 time_granularity=1 (小时) 时返回数值，其他粒度返回占位符
        time_granularity_map = {
            "hour": 1,
            "hourly": 1,
            "day": 1,    # 强制使用1（返回数值），而不是2（返回占位符）
            "daily": 1,
            "month": 1,
            "monthly": 1,
            "year": 1,
            "yearly": 1
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

            # 步骤2：站点名→站点编码映射
            geo_matcher = get_geo_matcher()
            station_codes = geo_matcher.stations_to_codes(station_names)
            if not station_codes:
                return {
                    "success": False,
                    "error": f"无法将站点名称映射到站点编码: {station_names}（原始输入: {locations}）",
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
            "pm25_carbon_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            time_granularity=time_granularity,
            locations=locations
        )

        client = get_particulate_api_client()

        try:
            # 使用 particulate_api_client 的正确方法
            api_result = client.get_carbon_components(
                station=station,
                code=code,
                start_time=start_time,
                end_time=end_time,
                table_type=time_granularity  # 直接传递时间粒度 (1=小时, 2=日, 3=月, 5=年)
            )

            if not api_result.get("success"):
                error_msg = api_result.get("error", "Unknown error")
                logger.error("carbon_api_call_failed", error=error_msg)
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

            # 提取记录 - 碳组分API返回特殊结构
            # 优先使用 resultData（原始数据），其次使用 resultAvg（平均值），最后兼容 resultOne
            records = []
            result = api_response.get("result", {})

            if "resultData" in result and result["resultData"]:
                records = result["resultData"]
                logger.info("carbon_using_resultData", record_count=len(records))
            elif "resultAvg" in result and result["resultAvg"]:
                # resultAvg 是单条记录，转换为列表
                avg_record = result["resultAvg"]
                if isinstance(avg_record, dict):
                    records = [avg_record]
                    logger.info("carbon_using_resultAvg", record_count=1)
            elif "resultOne" in result:
                # 兼容旧格式
                records = result.get("resultOne", [])
                logger.info("carbon_using_resultOne", record_count=len(records))
            else:
                logger.warning(
                    "carbon_unexpected_structure",
                    available_keys=list(result.keys())
                )

            if not records:
                return {
                    "success": False,
                    "error": "No carbon component records found",
                    "station": station,
                    "code": code,
                    "api_structure": list(api_response.get("result", {}).keys()) if isinstance(api_response, dict) else []
                }

            # 过滤掉所有 _Mark 字段
            records = _filter_mark_fields(records)
            logger.info("carbon_filtered", original_count=len(records), filtered_count=len(records))

            # 保存数据
            data_id = None
            file_path = None
            try:
                data_id = context.save_data(
                    data=records,
                    schema="particulate_unified",
                    metadata={
                        "component_type": "carbon",
                        "station": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "data_type": data_type,
                        "time_granularity": time_granularity
                    }
                )
            except Exception as save_error:
                logger.warning("pm25_carbon_save_failed", error=str(save_error))

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
                "time_granularity": time_granularity,
                "quality_report": quality_report,
                "summary": f"[OK] 成功获取{len(records)}条PM2.5碳组分数据（OC/EC），已保存为 {data_id}（路径: {file_path}）。",
                "metadata": {
                    "sample_record": sample_record
                }
            }

        except Exception as e:
            logger.error("pm25_carbon_query_failed", error=str(e))
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
        carbon_fields = [
            k for k in first.keys()
            if "OC" in k or "EC" in k or "碳" in k
        ]

        # 检查OC/EC字段
        oc_field = next((k for k in carbon_fields if "OC" in k), None)
        ec_field = next((k for k in carbon_fields if "EC" in k), None)

        result = {
            "total_records": len(records),
            "carbon_fields": len(carbon_fields),
            "field_names": list(carbon_fields)
        }

        if oc_field:
            valid_oc = sum(1 for r in records if r.get(oc_field) not in ["—", "", None])
            result["OC"] = {
                "field": oc_field,
                "valid_count": valid_oc,
                "total": len(records),
                "completeness": valid_oc / len(records)
            }

        if ec_field:
            valid_ec = sum(1 for r in records if r.get(ec_field) not in ["—", "", None])
            result["EC"] = {
                "field": ec_field,
                "valid_count": valid_ec,
                "total": len(records),
                "completeness": valid_ec / len(records)
            }

        return result


def __init__() -> None:
    return GetPM25CarbonTool()
