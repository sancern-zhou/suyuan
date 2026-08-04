"""
PM2.5碳组分查询工具（OC/EC）
查询有机碳(OC)和元素碳(EC)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.particulate_api_client import get_particulate_api_client
from app.utils.particulate_geo_matcher import get_particulate_geo_matcher

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


def _resolve_station_and_code(
    *,
    locations: Union[List[str], None],
    station: Union[str, None],
    code: Union[str, None],
) -> tuple[str | None, str | None, Dict[str, Any] | None]:
    if locations:
        station_names = [str(location).strip() for location in locations if str(location).strip()]
    elif station:
        station_names = [station.strip()]
    else:
        station_names = []

    if station_names:
        matcher = get_particulate_geo_matcher()
        try:
            station_codes = matcher.stations_to_codes(station_names)
        except ValueError as e:
            return None, None, {
                "success": False,
                "error": (
                    f"{e} 请先调用 resolve_station_geo 获取城市下辖组分站点，"
                    "再传入具体站点名称查询。"
                ),
                "locations": locations,
                "station_names": station_names,
            }
        if not station_codes:
            return None, None, {
                "success": False,
                "error": f"无法将站点名称映射到组分站点编码: {station_names}",
                "locations": locations,
                "station_names": station_names,
            }
        return station_names[0], code or station_codes[0], None

    if station and code:
        return station, code, None

    return None, None, {
        "success": False,
        "error": "必须提供具体组分站点名称 station，或同时提供 station 和 code；城市请先用 resolve_station_geo 展开。"
    }


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
                "查询PM2.5碳组分数据（OC/EC），用于PMF源解析和二次有机气溶胶分析。"
                "需要OC/EC或碳组分数据时优先使用；城市下辖组分站点需先用 resolve_station_geo 获取，本工具只查询指定站点。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "组分站点名称列表，不接受城市名；城市需先用 resolve_station_geo 展开"
                    },
                    "station": {
                        "type": "string",
                        "description": "中文组分站点名，可自动映射站点编码"
                    },
                    "code": {
                        "type": "string",
                        "description": "站点编码；传入 station 时可省略"
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
                        "description": "数据类型：0原始，1审核，默认0"
                    },
                    "time_granularity": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "时间粒度：1小时，2日，3月，5年；数值数据仅小时粒度，默认1",
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

        station, code, error = _resolve_station_and_code(locations=locations, station=station, code=code)
        if error:
            return error

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

            # 数据外部化：无条件保存完整数据到文件系统
            file_path = None
            file_path = None
            sample_data = records

            # 无条件外部化数据（确保下游分析工具能通过file_path获取数据）
            try:
                file_path = context.save_data(
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

                # 智能采样：超过24条时进行Head-Tail采样
                if len(records) <= 24:
                    sample_data = records
                else:
                    sample_count = 24
                    head_size = sample_count // 2
                    tail_size = sample_count - head_size
                    head = records[:head_size]
                    tail = records[-tail_size:]
                    sample_data = head + tail

                logger.info(
                    "pm25_carbon_data_externalized",
                    total_count=len(records),
                    sample_count=len(sample_data),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("pm25_carbon_save_failed", error=str(save_error))
                file_path = None

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

            # 构建返回消息
            if file_path:
                summary_msg = f"成功获取{len(records)}条PM2.5碳组分数据（已外部化，返回样本{len(sample_data)}条）"
            else:
                summary_msg = f"成功获取{len(records)}条PM2.5碳组分数据（OC/EC）"

            return {
                "success": True,
                "data": sample_data,  # 只返回样本数据
                "file_path": file_path,
                "file_path": file_path,
                "count": len(records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "data_type": data_type,
                "time_granularity": time_granularity,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "sample_record": sample_record,
                    "total_count": len(records),
                    "externalized": file_path is not None
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
