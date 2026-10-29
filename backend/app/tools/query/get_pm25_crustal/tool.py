"""
PM2.5地壳元素查询工具
查询铝(Al)、硅(Si)、钙(Ca)、铁(Fe)、钛(Ti)、钾(K)等地壳元素
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.particulate_api_client import get_particulate_api_client

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
                "查询广东省超级站组分站点的 PM2.5 地壳元素/无机元素数据"
                "（Al、Si、Ca、Fe、Ti、K、Mn 等），用于扬尘/建筑尘/道路尘指向、"
                "地壳贡献核算和富集因子分析。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用。"
                "注意：数值数据仅审核数据（data_type=1）且小时粒度返回，"
                "其他口径返回占位符。不要用于常规六参数/城市浓度查询（那是监测数据工具）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "station": {
                        "type": "string",
                        "description": "组分站点名称（如 新兴、鹤山花果山），自动映射站点编码；不接受城市名"
                    },
                    "locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "兼容参数：单个组分站点名的列表形式；多站点请并行调用"
                    },
                    "code": {
                        "type": "string",
                        "description": "组分站点编码（如 1042b）；传入 station 时可省略，只传 code 也可查询"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，格式 YYYY-MM-DD HH:MM:SS"
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，格式 YYYY-MM-DD HH:MM:SS"
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "数据质量：0原始，1审核（默认且唯一有数值的口径）",
                        "default": 1
                    },
                    "time_granularity": {
                        "type": "integer",
                        "description": "固定为 0（小时数值口径）；其他值返回占位符，保持默认即可",
                        "default": 0
                    },
                    "elements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "元素列表，如['Al','Si','Fe','Ca','Ti','Mn']；留空查默认六元素",
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

        station, code, error = resolve_component_station(locations=locations, station=station, code=code)
        if error:
            return error

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
                        "component_type": "crustal",
                        "station": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "elements": elements
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
                    "pm25_crustal_data_externalized",
                    total_count=len(records),
                    sample_count=len(sample_data),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("pm25_crustal_save_failed", error=str(save_error))
                file_path = None

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

            # 构建返回消息
            if file_path:
                summary_msg = f"成功获取{len(records)}条PM2.5地壳元素数据（已外部化，返回样本{len(sample_data)}条）"
            else:
                summary_msg = f"成功获取{len(records)}条PM2.5地壳元素数据"

            return {
                "success": True,
                "data": sample_data,  # 只返回样本数据
                "file_path": file_path,
                "file_path": file_path,
                "count": len(records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "elements": elements,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "sample_record": sample_record,
                    "total_count": len(records),
                    "externalized": file_path is not None
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
