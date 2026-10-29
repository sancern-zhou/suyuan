"""PM2.5 组分质量重构查询工具（广东超站 GetComponentPm25RecoveryAnalysis）。

平台官方重构口径：九组分（有机物/硫酸盐/硝酸盐/铵盐/元素碳/氯盐/
地壳元素/微量元素/其他）+ 重构质量浓度与 PM2.5 比值 + 高位线/低位线 +
K/B/R² 拟合；重构契约单一来源 component_semantics。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.component_semantics import (
    RECONSTRUCTION_COMPONENTS,
    RECONSTRUCTION_RATIO_BAND,
    filter_mark_fields,
)
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.particulate_api_client import get_particulate_api_client

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetPM25RecoveryTool(LLMTool):
    """PM2.5 组分质量重构查询工具（平台官方口径）"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_pm25_recovery",
            "description": (
                "查询广东省超级站组分站点的 PM2.5 组分质量重构（平台官方口径）。"
                "返回九组分（有机物/硫酸盐/硝酸盐/铵盐/元素碳/氯盐/地壳元素/微量元素/其他）"
                "重构质量时序与平均占比，以及重构质量浓度与 PM2.5 实测的比值、"
                "高位线 1.20 / 低位线 0.70 控制线和 K/B/R² 线性拟合，"
                "用于质量闭合检验、二次组分占比与来源类型识别。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用；"
                "数值口径以小时粒度为主，其他粒度返回占位符时按该口径无数据交付。"
                "离线自算重构用 calculate_reconstruction（输入查询工具落盘数据）；"
                "优先使用本工具的官方口径。"
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
                        "description": "统计粒度：1小时（默认，数值口径），2日，3月，5年",
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
            name="get_pm25_recovery",
            description="Query official PM2.5 mass reconstruction (9 components, closure ratio, K/B/R2).",
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
        """执行 PM2.5 组分重构查询"""

        station, code, error = resolve_component_station(locations=locations, station=station, code=code)
        if error:
            return error

        granularity_raw = time_granularity if time_granularity is not None else table_type
        if granularity_raw is None:
            granularity_raw = 1
        table_type_value = int(granularity_raw)

        logger.info(
            "pm25_recovery_tool_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_granularity=table_type_value,
            data_type=data_type
        )

        client = get_particulate_api_client()
        api_result = client.get_pm25_recovery(
            station=station or "",
            code=code,
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
            result = api_result.get("api_response", {}).get("result", {})
            records = result.get("resultData", [])
            avg_data = result.get("resultAvg", [])
            avg_prop = result.get("resultAvgProp", [])
            prop_data = result.get("resultDataProp", [])

            if not records:
                return {
                    "success": False,
                    "error": "No PM2.5 recovery records found",
                    "station": station,
                    "code": code
                }

            records = filter_mark_fields(records)

            file_path = None
            sample_data = records
            try:
                file_path = context.save_data(
                    data=records,
                    schema="particulate_unified",
                    metadata={
                        "component_type": "pm25_recovery",
                        "station": station,
                        "station_name": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(records),
                        "table_type": table_type_value,
                        "data_type": data_type,
                    }
                )
                if len(records) > 24:
                    sample_data = records[:12] + records[-12:]
                logger.info(
                    "pm25_recovery_data_externalized",
                    total_count=len(records),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("pm25_recovery_save_failed", error=str(save_error))
                file_path = None

            quality_report = self._analyze_quality(records)

            sample_record = records[0] if records else None
            if file_path:
                summary_msg = (
                    f"成功获取{len(records)}条PM2.5组分重构数据"
                    f"（已保存数据引用，返回样本{len(sample_data)}条）"
                )
            else:
                summary_msg = f"成功获取{len(records)}条PM2.5组分重构数据"

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
                "avg_data": avg_data,
                "avg_prop": avg_prop,
                "prop_data": prop_data,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_pm25_recovery",
                    "station_name": station,
                    "code": code,
                    "total_count": len(records),
                    "externalized": file_path is not None,
                    "components": RECONSTRUCTION_COMPONENTS,
                    "sample_record": sample_record,
                }
            }

        except Exception as e:
            logger.error("pm25_recovery_tool_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _analyze_quality(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """重构质量：九组分有效率 + 质量闭合比值落在控制线内的比例。"""
        if not records:
            return {}

        report: Dict[str, Any] = {"total_records": len(records)}

        for component in RECONSTRUCTION_COMPONENTS:
            valid = sum(
                1 for r in records
                if r.get(component) is not None and r.get(component) != "—"
            )
            report[component] = {
                "valid_count": valid,
                "total": len(records),
                "completeness": round(valid / len(records), 3),
            }

        in_band = 0
        ratio_total = 0
        for record in records:
            ratio = record.get("重构后的质量浓度比值")
            if isinstance(ratio, (int, float)):
                ratio_total += 1
                if RECONSTRUCTION_RATIO_BAND["low"] <= ratio <= RECONSTRUCTION_RATIO_BAND["high"]:
                    in_band += 1
        if ratio_total:
            report["closure_ratio_in_band"] = {
                "count": in_band,
                "total": ratio_total,
                "band": RECONSTRUCTION_RATIO_BAND,
            }
        return report


def __init__() -> GetPM25RecoveryTool:
    return GetPM25RecoveryTool()
