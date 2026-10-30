"""
VOCs组分查询工具（直接调用广东超站API）
查询VOCs类别和物种数据：烷烃、烯烃、炔烃、芳香烃、OVOCs等

替换原自然语言API工具，使用结构化参数直接调用广东超站接口

站点映射说明：
- VOCs站点与PM2.5组分站点共享同一套编码系统（geo_mappings.json）
- 站点名称→编码解析统一走 component_station_resolver
- 站点编码格式：1025b（带b后缀）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.vocs_api_client import get_voc_api_client

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetVOCsDataTool(LLMTool):
    """VOCs数据查询工具（烷烃、烯烃、炔烃、芳香烃、OVOCs等）- 结构化查询版本"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_vocs_data",
            "description": (
                "查询广东省超级站组分站点的 VOCs 组分数据（VOCs 类别：烷烃、烯烃、炔烃、"
                "芳香烃、OVOCs、卤代烃等及其占比），用于 VOCs 组成特征、"
                "臭氧生成潜势（OFP）核算和来源指向分析。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用。"
                "返回类别级时序/均值/占比结构；物种级明细按 station 清单结合类别结果另行研判。"
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
                    "time_granularity": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "统计粒度：1小时（默认），2日，3月，5年",
                        "default": 1
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1, 4, 5],
                        "description": "数据审核类型：0原始（默认），1终审，4初审，5复审"
                    }
                },
                "required": ["start_time", "end_time"],
            }
        }

        super().__init__(
            name="get_vocs_data",
            description="Query VOCs component data (alkanes, alkenes, aromatics, OVOCs, etc.) - Structured API",
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
        time_granularity: Union[int, str, None] = None,
        table_type: Union[int, str, None] = None,
        data_type: int = 0,
        **_: Any
    ) -> Dict[str, Any]:
        """执行VOCs类别查询"""

        station, code, error = resolve_component_station(locations=locations, station=station, code=code, require_domain="vocs")
        if error:
            return error

        # 兼容旧参数名 table_type；粒度参数统一走 time_granularity
        granularity_raw = time_granularity if time_granularity is not None else table_type
        if granularity_raw is None:
            granularity_raw = 1
        table_type_value = int(granularity_raw)

        logger.info(
            "voc_categories_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_granularity=table_type_value,
            data_type=data_type
        )

        # 获取API客户端
        client = get_voc_api_client()

        # 调用VOCs类别查询接口
        api_result = client.get_voc_categories(
            station_code=code,
            start_time=start_time,
            end_time=end_time,
            table_type=table_type_value,
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
        logger.info("voc_categories_api_response", response=str(api_response))

        try:
            # 提取数据
            result = api_response.get("result", {})
            records = result.get("dataList", [])
            avg_data = result.get("resultAvg", [])
            prop_data = result.get("resultDataProp", [])
            avg_prop = result.get("resultAvgProp", [])

            if not records:
                return {
                    "success": False,
                    "error": "No VOCs category records found",
                    "station": station,
                    "code": code
                }

            # 标准化数据格式
            standardized_records = self._standardize_voc_data(records)

            # 数据外部化：下游PMF依赖file_path，即使只有24小时数据也需要保存引用。
            file_path = None
            file_path = None
            sample_data = standardized_records

            try:
                file_path = context.save_data(
                    data=standardized_records,
                    schema="vocs_unified",
                    metadata={
                        "component_type": "categories",
                        "station": station,
                        "station_name": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(standardized_records),
                        "table_type": table_type,
                        "data_type": data_type
                    }
                )

                if len(standardized_records) > 24:
                    # 智能采样：前12条 + 后12条
                    head_size = 12
                    tail_size = 12
                    sample_data = standardized_records[:head_size] + standardized_records[-tail_size:]

                logger.info(
                    "voc_categories_data_externalized",
                    total_count=len(standardized_records),
                    sample_count=len(sample_data),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("voc_categories_save_failed", error=str(save_error))
                file_path = None

            # 构建返回消息
            if file_path:
                summary_msg = f"成功获取{len(standardized_records)}条VOCs类别数据（已保存数据引用，返回样本{len(sample_data)}条）"
            else:
                summary_msg = f"成功获取{len(standardized_records)}条VOCs类别数据"

            return {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "file_path": file_path,
                "count": len(standardized_records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "table_type": table_type,
                "data_type": data_type,
                "avg_data": avg_data,
                "prop_data": prop_data,
                "avg_prop": avg_prop,
                "summary": summary_msg,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_vocs_data",
                    "file_path": file_path,
                    "station_name": station,
                    "station": station,
                    "code": code,
                    "total_count": len(standardized_records),
                    "externalized": file_path is not None
                }
            }

        except Exception as e:
            logger.error("voc_categories_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _standardize_voc_data(self, records: List[Dict]) -> List[Dict]:
        """标准化VOCs数据格式"""
        standardized = []

        for record in records:
            std_record = {
                "timestamp": record.get("TimePoint"),
                "station_code": record.get("Code"),
                "station_name": record.get("StationName"),
                "data_type": record.get("DataType"),
                "time_type": record.get("TimeType"),
                "measurements": {
                    "tvoc": self._safe_float(record.get("TVOC")),
                    "alkanes": self._safe_float(record.get("烷烃")),
                    "alkenes": self._safe_float(record.get("烯烃")),
                    "alkynes": self._safe_float(record.get("炔烃")),
                    "aromatics": self._safe_float(record.get("芳香烃")),
                    "ovocs": self._safe_float(record.get("OVOCs")),
                    "halogenated": self._safe_float(record.get("卤代烃")),
                    "organic_sulfur": self._safe_float(record.get("有机硫"))
                }
            }
            standardized.append(std_record)

        return standardized

    def _safe_float(self, value: Any) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == "" or value == "—":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def __init__() -> GetVOCsDataTool:
    return GetVOCsDataTool()
