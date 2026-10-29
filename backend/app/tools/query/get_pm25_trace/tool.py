"""PM2.5 微量元素/重金属查询工具（广东超站 GetChartAnalysis，元素分析页）。

与地壳元素同一接口与口径（审核数据 + 小时粒度才有数值），默认查询
13 项微量元素/重金属（Mn/Zn/Pb/V/As/Cr/Cu/Se/Ni/Cd/Sb/Co/Hg），
编码字典单一来源 component_semantics.METAL_ELEMENT_CODES（42 项可选）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.component_semantics import (
    TRACE_ELEMENTS,
    filter_mark_fields,
    metal_element_catalog_text,
    resolve_element_codes,
)
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.particulate_api_client import get_particulate_api_client

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetPM25TraceTool(LLMTool):
    """PM2.5 微量元素/重金属查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_pm25_trace",
            "description": (
                "查询广东省超级站组分站点的 PM2.5 微量元素/重金属数据"
                "（默认 Mn/Zn/Pb/V/As/Cr/Cu/Se/Ni/Cd/Sb/Co/Hg 十三项，"
                "可选元素见元素字典：Al/Si/Ca/Fe/Ti/K/Mn/Zn/Pb/V/As/Cr/Cu/Se/Ni/Cd/Sb/Co/Hg/"
                "Tl/Sc/P/Sn/Te/Au/Cs/Br/Ge/Ba/Bi/In/S/Rb/Sr/Cl/Pt/Nb/Ag/Mo/Y/Pd/Ga），"
                "用于工业/燃煤/交通源指向、富集因子分析（输入 calculate_trace）与"
                "组分重构微量元素项。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用。"
                "注意：数值数据仅审核数据（data_type=1）且小时粒度返回，"
                "其他口径返回占位符；元素可得性取决于站点仪器配置，"
                "返回占位符按该站无此元素数据交付。"
                "地壳六元素（Al/Si/Ca/Fe/Ti/K）扬尘指向用 get_pm25_crustal。"
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
                        "description": (
                            "元素符号或中文名列表（如 ['Pb','Zn','As'] 或 ['铅','锌','砷']），"
                            "留空查默认十三项微量元素"
                        ),
                    }
                },
                "required": ["start_time", "end_time"],
            }
        }

        super().__init__(
            name="get_pm25_trace",
            description="Query PM2.5 trace elements/heavy metals (Mn Zn Pb V As Cr Cu Se Ni Cd Sb Co Hg).",
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
        data_type: int = 1,
        time_granularity: Union[int, str] = 0,
        elements: Union[List[str], None] = None,
        **_: Any
    ) -> Dict[str, Any]:
        """执行微量元素查询"""

        requested_elements = list(elements) if elements else list(TRACE_ELEMENTS)
        detection_codes, unresolved = resolve_element_codes(requested_elements)
        if not detection_codes:
            return {
                "success": False,
                "error": (
                    f"元素无法识别：{('、'.join(unresolved))[:80]}。"
                    f"可用元素目录：{metal_element_catalog_text()}"
                ),
                "station": station,
                "code": code,
            }

        # 数值口径：审核数据（dateType=1）+ 小时粒度（dataType=0）
        station, code, error = resolve_component_station(locations=locations, station=station, code=code)
        if error:
            return error

        logger.info(
            "pm25_trace_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            elements=requested_elements,
            data_type=data_type
        )

        client = get_particulate_api_client()
        api_result = client.get_heavy_metal_analysis(
            station=station or "",
            code=code,
            start_time=start_time,
            end_time=end_time,
            date_type=data_type,   # 数据质量：1=审核（微量元素数值仅审核口径）
            data_type=0,           # 时间粒度：0=小时（返回数值）
            detection_item_codes=detection_codes
        )

        if not api_result.get("success"):
            error_msg = api_result.get("error", "Unknown error")
            logger.error("trace_api_call_failed", error=error_msg)
            return {
                "success": False,
                "error": f"API调用失败: {error_msg}",
                "station": station,
                "code": code
            }

        try:
            api_response = api_result.get("api_response", {})
            if not api_response:
                return {
                    "success": False,
                    "error": "API返回空响应",
                    "station": station,
                    "code": code
                }

            records = api_response.get("result", {}).get("resultOne", [])
            if not records:
                return {
                    "success": False,
                    "error": "No trace element records found",
                    "station": station,
                    "code": code,
                    "api_structure": list(api_response.get("result", {}).keys()) if isinstance(api_response, dict) else []
                }

            records = filter_mark_fields(records)

            file_path = None
            sample_data = records
            try:
                file_path = context.save_data(
                    data=records,
                    schema="particulate_unified",
                    metadata={
                        "component_type": "trace_elements",
                        "station": station,
                        "station_name": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "elements": requested_elements,
                        "detection_codes": detection_codes,
                    }
                )
                if len(records) > 24:
                    sample_data = records[:12] + records[-12:]
                logger.info(
                    "pm25_trace_data_externalized",
                    total_count=len(records),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("pm25_trace_save_failed", error=str(save_error))
                file_path = None

            quality_report = self._analyze_quality(records, requested_elements)
            quality_report["unresolved_elements"] = unresolved

            if file_path:
                summary_msg = (
                    f"成功获取{len(records)}条PM2.5微量元素数据"
                    f"（已保存数据引用，返回样本{len(sample_data)}条）"
                )
            else:
                summary_msg = f"成功获取{len(records)}条PM2.5微量元素数据"

            return {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": len(records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "elements": requested_elements,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "sample_record": records[0] if records else None,
                    "total_count": len(records),
                    "externalized": file_path is not None,
                }
            }

        except Exception as e:
            logger.error("pm25_trace_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _analyze_quality(self, records: List[Dict[str, Any]], elements: List[str]) -> Dict[str, Any]:
        """逐元素数据完整性统计。"""
        if not records:
            return {}

        available_fields = [
            k for k in records[0].keys()
            if k not in ("Code", "StationName", "TimePoint", "DataType")
        ]
        result: Dict[str, Any] = {
            "total_records": len(records),
            "available_element_fields": available_fields[:20],
        }
        for element in elements:
            matching = [f for f in available_fields if str(element) in f]
            if matching:
                field = matching[0]
                valid = sum(1 for r in records if r.get(field) not in ["—", "", None])
                result[str(element)] = {
                    "field": field,
                    "valid_count": valid,
                    "total": len(records),
                    "completeness": round(valid / len(records), 3),
                }
        return result


def __init__() -> GetPM25TraceTool:
    return GetPM25TraceTool()
