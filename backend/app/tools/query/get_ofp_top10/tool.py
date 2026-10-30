"""VOCs 物种 OFP Top10 查询工具（广东超站 GetStationDataSecondOFPAOrdersync）。

返回物种 OFP 前10、浓度前10 双榜与 OFP 累计贡献（ofpresults，contribution
为累计百分比）；接口仅支持单站点，固定参数单一来源 component_semantics。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.vocs_api_client import get_voc_api_client

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetOFPTop10Tool(LLMTool):
    """VOCs 物种 OFP Top10 与累计贡献查询工具"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_ofp_top10",
            "description": (
                "查询广东省超级站组分站点的 VOCs 物种 OFP Top10、浓度 Top10 与 OFP 累计贡献。"
                "OFP 由平台按官方 MIR 系数（版本1）计算：OFP 前10（datalistOrderByOFP）、"
                "浓度前10（datalistOrderByval）、OFP 降序累计贡献百分比（ofpresults），"
                "用于识别臭氧生成关键活性物种与贡献截断点（如累计到 80% 的物种数）。"
                "仅支持单站点，多站点在同一轮并行多次调用；"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）。"
                "类别级 OFP 时序用 get_vocs_ofp。"
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
            name="get_ofp_top10",
            description="Query VOCs species OFP/concentration Top10 and cumulative OFP contribution.",
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
        """执行 OFP Top10 查询"""

        station, code, error = resolve_component_station(locations=locations, station=station, code=code, require_domain="vocs")
        if error:
            return error

        granularity_raw = time_granularity if time_granularity is not None else table_type
        if granularity_raw is None:
            granularity_raw = 1
        table_type_value = int(granularity_raw)

        logger.info(
            "ofp_top10_tool_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_granularity=table_type_value,
            data_type=data_type
        )

        client = get_voc_api_client()
        api_result = client.get_ofp_top10(
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
            result = api_result.get("api_response", {}).get("result", {})
            ofp_top10 = result.get("datalistOrderByOFP", [])
            val_top10 = result.get("datalistOrderByval", [])
            ofp_results = result.get("ofpresults", [])
            ofp_total = result.get("ofp总数")
            val_total = result.get("浓度总数")

            if not ofp_top10 and not ofp_results:
                return {
                    "success": False,
                    "error": "No OFP Top10 records found",
                    "station": station,
                    "code": code
                }

            # 累计贡献达到 80% 所需的物种数（接口已给累计百分比，这里只读截断点）
            species_to_80 = None
            for idx, item in enumerate(ofp_results, start=1):
                contribution = item.get("contribution")
                if isinstance(contribution, (int, float)) and contribution >= 80:
                    species_to_80 = idx
                    break

            payload = {
                "ofp_top10": ofp_top10,
                "concentration_top10": val_top10,
                "cumulative_contribution": ofp_results,
                "species_count_to_80pct": species_to_80,
                "ofp_total": ofp_total,
                "concentration_total": val_total,
            }

            file_path = None
            try:
                file_path = context.save_data(
                    data=payload,
                    schema="vocs_ofp_top10",
                    metadata={
                        "component_type": "vocs_ofp_top10",
                        "station": station,
                        "station_name": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "table_type": table_type_value,
                        "data_type": data_type,
                        "mir_version": 1,
                    }
                )
            except Exception as save_error:
                logger.warning("ofp_top10_save_failed", error=str(save_error))
                file_path = None

            return {
                "success": True,
                **payload,
                "file_path": file_path,
                "station": station,
                "code": code,
                "table_type": table_type_value,
                "data_type": data_type,
                "mir_version": 1,
                "summary": (
                    f"OFP Top10 首要物种为 {ofp_top10[0].get('DisplayName') if ofp_top10 else '—'}"
                    f"（OFP={ofp_top10[0].get('ofp') if ofp_top10 else '—'}），"
                    f"累计贡献达 80% 需前 {species_to_80 if species_to_80 else '—'} 个物种"
                    if ofp_top10 else "OFP Top10 数据为空"
                ),
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_ofp_top10",
                    "station_name": station,
                    "code": code,
                    "externalized": file_path is not None,
                }
            }

        except Exception as e:
            logger.error("ofp_top10_tool_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }


def __init__() -> GetOFPTop10Tool:
    return GetOFPTop10Tool()
