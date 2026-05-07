"""
VOCs组分查询工具（直接调用广东超站API）
查询VOCs类别和物种数据：烷烃、烯烃、炔烃、芳香烃、OVOCs等

替换原自然语言API工具，使用结构化参数直接调用广东超站接口

站点映射说明：
- VOCs站点与PM2.5组分站点共享同一套编码系统（geo_mappings.json）
- 使用 ParticulateGeoMatcher 进行站点名称到编码的映射
- 站点编码格式：1025b（带b后缀）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.vocs_api_client import get_voc_api_client
from app.utils.particulate_geo_matcher import get_particulate_geo_matcher
from app.utils.particulate_city_mapper import get_particulate_city_mapper

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetVOCsDataTool(LLMTool):
    """VOCs数据查询工具（烷烃、烯烃、炔烃、芳香烃、OVOCs等）- 结构化查询版本"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_vocs_data",
            "description": (
                "查询VOCs组分数据，包括烷烃、烯烃、炔烃、芳香烃、OVOCs、卤代烃、有机硫等。"
                "直接调用广东超站API获取结构化数据，支持站点自动映射。"
                "用于VOCs组分分析和臭氧生成潜势(OFP)分析。"
                "locations参数可自动映射站点编码。"
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
                    "table_type": {
                        "type": "integer",
                        "enum": [1, 2, 3, 5],
                        "description": "统计类型：1小时（默认），2日，3月，5年"
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1, 4, 5],
                        "description": "数据类型：0原始（默认），1终审，4初审，5复审"
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
        table_type: int = 1,
        data_type: int = 0,
        **_: Any
    ) -> Dict[str, Any]:
        """执行VOCs类别查询"""

        # 参数处理：支持 locations 自动映射
        if locations:
            # 第一步：城市名 → 站点名（使用城市映射器）
            city_mapper = get_particulate_city_mapper()
            station_names = []
            for loc in locations:
                # 尝试作为城市名映射
                station_name = city_mapper.city_to_station_name(loc)
                if station_name:
                    station_names.append(station_name)
                    logger.info("city_to_station_mapped", city=loc, station=station_name)
                else:
                    # 可能已经是站点名，直接使用
                    station_names.append(loc)

            # 第二步：站点名 → 站点编码（使用组分站点映射器）
            component_matcher = get_particulate_geo_matcher()
            try:
                station_codes = component_matcher.stations_to_codes(station_names)
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
                    "error": f"无法将站点名称映射到组分站点编码: {station_names}",
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
            "voc_categories_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            table_type=table_type,
            data_type=data_type
        )

        # 获取API客户端
        client = get_voc_api_client()

        # 调用VOCs类别查询接口
        api_result = client.get_voc_categories(
            station_code=code,
            start_time=start_time,
            end_time=end_time,
            table_type=table_type,
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

            # 数据外部化：保存完整数据到文件系统
            data_id = None
            file_path = None
            sample_data = standardized_records

            if len(standardized_records) > 24:
                # 超过24条，进行采样并外部化
                try:
                    data_id = context.save_data(
                        data=standardized_records,
                        schema="vocs_unified",
                        metadata={
                            "component_type": "categories",
                            "station": station,
                            "code": code,
                            "start_time": start_time,
                            "end_time": end_time,
                            "record_count": len(standardized_records),
                            "table_type": table_type,
                            "data_type": data_type
                        }
                    )

                    # 智能采样：前12条 + 后12条
                    head_size = 12
                    tail_size = 12
                    sample_data = standardized_records[:head_size] + standardized_records[-tail_size:]

                    logger.info(
                        "voc_categories_data_externalized",
                        total_count=len(standardized_records),
                        sample_count=len(sample_data),
                        data_id=data_id
                    )
                except Exception as save_error:
                    logger.warning("voc_categories_save_failed", error=str(save_error))
                    data_id = None

            # 构建返回消息
            if data_id:
                summary_msg = f"成功获取{len(standardized_records)}条VOCs类别数据（已外部化，返回样本{len(sample_data)}条）"
            else:
                summary_msg = f"成功获取{len(standardized_records)}条VOCs类别数据"

            return {
                "success": True,
                "data": sample_data,
                "data_id": data_id,
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
                    "total_count": len(standardized_records),
                    "externalized": data_id is not None
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
