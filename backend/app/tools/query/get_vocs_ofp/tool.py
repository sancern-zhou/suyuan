"""VOCs 类别 OFP（臭氧生成潜势）时序查询工具（广东超站 GetStationOfpDataAsync）。

OFP 由平台按固定 MIR 系数版本（mirVerEmun=1）官方计算，返回
7 大类 + TVOC 的 OFP 时序与浓度百分比；固定参数单一来源 component_semantics。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.component_semantics import OFP_CATEGORY_ORDER
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.vocs_api_client import get_voc_api_client

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetVOCsOFPTool(LLMTool):
    """VOCs 类别 OFP 时序查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_vocs_ofp",
            "description": (
                "查询广东省超级站组分站点的 VOCs 类别臭氧生成潜势（OFP）时序与占比。"
                "OFP 由平台按官方 MIR 系数（版本1）计算，返回烷烃/烯烃/炔烃/芳香烃/"
                "OVOCs/卤代烃/有机硫各类别与 TVOC 的 OFP 时序及浓度百分比，"
                "用于臭氧生成主导类别识别与 VOCs 活性分析。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用；"
                "小时粒度单次查询窗口不超过 24 小时。"
                "物种级 OFP Top10 与累计贡献用 get_ofp_top10。"
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
                        "description": "统计粒度：1小时（默认），2日，3月，5年；小时窗口不超过24小时",
                        "default": 1
                    },
                    "data_type": {
                        "type": "integer",
                        "enum": [0, 1, 4, 5],
                        "description": "数据审核类型：0原始（默认，终审审核滞后常有空窗），1终审，4初审，5复审",
                        "default": 0
                    }
                },
                "required": ["start_time", "end_time"],
            }
        }

        super().__init__(
            name="get_vocs_ofp",
            description="Query category-level VOCs OFP timeseries (platform MIR-based) from Guangdong super station.",
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
        """执行类别 OFP 时序查询"""

        station, code, error = resolve_component_station(locations=locations, station=station, code=code, require_domain="vocs")
        if error:
            return error

        granularity_raw = time_granularity if time_granularity is not None else table_type
        if granularity_raw is None:
            granularity_raw = 1
        table_type_value = int(granularity_raw)

        logger.info(
            "voc_ofp_tool_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_granularity=table_type_value,
            data_type=data_type
        )

        client = get_voc_api_client()
        api_result = client.get_ofp_timeseries(
            station_code=code,
            start_time=start_time,
            end_time=end_time,
            table_type=table_type_value,
            data_type=data_type
        )

        if not api_result.get("success"):
            return {
                "success": False,
                "error": api_result.get("error", "Unknown API error"),
                "station": station,
                "code": code
            }

        try:
            result = api_result.get("api_response", {}).get("result", [])
            # 接口返回二元数组：[0] 各类别 OFP 时序，[1] 各类别浓度百分比
            if not isinstance(result, list) or len(result) < 2:
                return {
                    "success": False,
                    "error": "OFP 时序接口返回结构异常（预期二元数组）",
                    "station": station,
                    "code": code,
                    "api_structure": type(result).__name__,
                }

            timeseries, share = result[0], result[1]
            records = self._standardize_ofp_records(timeseries, share)

            if not records:
                return {
                    "success": False,
                    "error": "No OFP records found",
                    "station": station,
                    "code": code
                }

            file_path = None
            sample_data = records
            try:
                file_path = context.save_data(
                    data=records,
                    schema="vocs_ofp_unified",
                    metadata={
                        "component_type": "vocs_ofp_category",
                        "station": station,
                        "station_name": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "table_type": table_type_value,
                        "data_type": data_type,
                        "mir_version": 1,
                    }
                )
                if len(records) > 24:
                    sample_data = records[:12] + records[-12:]
                logger.info(
                    "voc_ofp_data_externalized",
                    total_count=len(records),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("voc_ofp_save_failed", error=str(save_error))
                file_path = None

            quality_report = self._analyze_quality(records)

            if file_path:
                summary_msg = (
                    f"成功获取{len(records)}条VOCs类别OFP时序数据"
                    f"（已保存数据引用，返回样本{len(sample_data)}条）"
                )
            else:
                summary_msg = f"成功获取{len(records)}条VOCs类别OFP时序数据"

            return {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": len(records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "table_type": table_type_value,
                "data_type": data_type,
                "mir_version": 1,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_vocs_ofp",
                    "station_name": station,
                    "code": code,
                    "total_count": len(records),
                    "externalized": file_path is not None,
                    "category_order": OFP_CATEGORY_ORDER,
                }
            }

        except Exception as e:
            logger.error("voc_ofp_tool_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _standardize_ofp_records(self, timeseries: Dict, share: Dict) -> List[Dict[str, Any]]:
        """把接口的平行数组（TimePoint 列 + 类别值列）组装为逐时记录。"""
        time_points = timeseries.get("TimePoint", [])
        records: List[Dict[str, Any]] = []
        for idx, time_point in enumerate(time_points):
            ofp_values: Dict[str, Any] = {}
            share_values: Dict[str, Any] = {}
            for category, series in timeseries.items():
                if category == "TimePoint" or not isinstance(series, list):
                    continue
                ofp_values[category] = self._safe_float(
                    series[idx] if idx < len(series) else None
                )
            for category, series in (share or {}).items():
                if not isinstance(series, list):
                    continue
                share_values[category] = self._safe_float(
                    series[idx] if idx < len(series) else None
                )
            records.append({
                "timestamp": time_point,
                "ofp": ofp_values,
                "concentration_share_percent": share_values,
            })
        return records

    def _analyze_quality(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """OFP 完整性：各类别有效率。"""
        if not records:
            return {}
        categories = list(records[0].get("ofp", {}).keys())
        report: Dict[str, Any] = {"total_records": len(records), "categories": categories}
        for category in categories:
            valid = sum(
                1 for r in records if r.get("ofp", {}).get(category) is not None
            )
            report[category] = {
                "valid_count": valid,
                "total": len(records),
                "completeness": round(valid / len(records), 3),
            }
        return report

    def _safe_float(self, value: Any) -> Any:
        if value is None or value == "" or value == "—":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return value


def __init__() -> GetVOCsOFPTool:
    return GetVOCsOFPTool()
