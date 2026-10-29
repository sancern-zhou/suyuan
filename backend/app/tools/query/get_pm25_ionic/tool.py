"""
PM2.5水溶性离子组分查询工具
查询F⁻、Cl⁻、NO₂⁻、NO₃⁻、SO₄²⁻、PO₄³⁻、Li⁺、Na⁺、K⁺、NH₄⁺、Mg²⁺、Ca²⁺、Al³⁺等
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
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


class GetPM25IonicTool(LLMTool):
    """PM2.5水溶性离子组分查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_pm25_ionic",
            "description": (
                "查询广东省超级站组分站点的 PM2.5 水溶性离子数据"
                "（SO4²⁻、NO3⁻、NH4⁺、F⁻、Cl⁻、Na⁺、K⁺、Mg²⁺、Ca²⁺ 等），"
                "用于二次无机盐生成、PMF 源解析输入和组分重构分析。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用。"
                "不要用于常规六参数/城市浓度查询（那是监测数据工具）。"
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
                        "description": "兼容参数：单个组分站点名的列表形式；传入多个时仅支持一个，多站点请并行调用"
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
                    "time_granularity": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "时间粒度：1小时（默认，数值完整），2日，3月，5年",
                        "default": 1
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1],
                        "description": "数据质量：0原始（默认），1审核"
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
        time_granularity: Union[int, str, None] = None,
        time_type: Union[int, str, None] = None,
        **_: Any
    ) -> Dict[str, Any]:
        """执行水溶性离子查询"""

        station, code, error = resolve_component_station(locations=locations, station=station, code=code)
        if error:
            return error

        # 兼容旧参数名 time_type；粒度参数统一走 time_granularity
        granularity_raw = time_granularity if time_granularity is not None else time_type
        if granularity_raw is None:
            granularity_raw = 1
        if isinstance(granularity_raw, str):
            text = granularity_raw.strip().lower()
            granularity_raw = {"hour": 1, "hourly": 1, "day": 2, "daily": 2,
                               "month": 3, "monthly": 3, "year": 5, "yearly": 5}.get(text, 1)
        time_type_value = int(granularity_raw)

        logger.info(
            "pm25_ionic_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            data_type=data_type,
            time_granularity=time_type_value
        )

        client = get_particulate_api_client()

        # 调用API客户端的 get_ionic_analysis 方法
        # 该方法会自动处理Token验证和完整URL构建
        # time_granularity: 1=hour, 2=day, 3=month, 5=year (直接传递整数)
        api_result = client.get_ionic_analysis(
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_type=time_type_value,
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

            # 数据外部化：保存完整数据到文件系统
            file_path = None
            file_path = None
            sample_data = records

            # 无条件外部化数据（确保下游分析工具能通过file_path获取数据）
            try:
                file_path = context.save_data(
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
                    "pm25_ionic_data_externalized",
                    total_count=len(records),
                    sample_count=len(sample_data),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("pm25_ionic_save_failed", error=str(save_error))
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
                summary_msg = f"成功获取{len(records)}条PM2.5水溶性离子数据（已外部化，返回样本{len(sample_data)}条）"
            else:
                summary_msg = f"成功获取{len(records)}条PM2.5水溶性离子数据"

            return {
                "success": True,
                "data": sample_data,  # 只返回样本数据
                "file_path": file_path,    # 完整数据文件路径
                "file_path": file_path,
                "count": len(records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "data_type": data_type,
                "time_type": time_type,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "sample_record": sample_record,
                    "total_count": len(records),
                    "externalized": file_path is not None
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
