"""VOCs 物种级查询工具（广东超站 GetSpeciesVOCAnalysis）。

117 种单体物种（烷烃/烯烃/炔烃/芳香烃/卤代烃/OVOCs/有机硫）的时序浓度、
数值化占比与物种浓度 Top10（topTenResultAvg）；物种字典单一来源
component_semantics.VOC_SPECIES_GROUPS。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Union
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.component_semantics import (
    VOC_ALL_SPECIES,
    VOC_SPECIES_SET,
    filter_mark_fields,
    voc_species_catalog_text,
    voc_species_group,
)
from app.tools.query.component_station_resolver import resolve_component_station
from app.utils.vocs_api_client import get_voc_api_client

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

# 返回给模型的样本里逐物种字段过多，默认只带 Top 物种列，全量在落盘文件
_SAMPLE_SPECIES = [
    "乙烷", "乙烯", "乙炔", "丙烷", "丙烯", "异丁烷", "正丁烷", "异戊烷", "正戊烷",
    "正己烷", "苯", "甲苯", "乙苯", "间/对-二甲苯", "邻-二甲苯", "苯乙烯",
    "异戊二烯", "甲醛", "乙醛", "丙酮",
]


class GetVOCsSpeciesTool(LLMTool):
    """VOCs 物种级数据查询工具（117 种单体物种）"""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_vocs_species",
            "description": (
                "查询广东省超级站组分站点的 VOCs 物种级浓度数据（117 种单体物种："
                "烷烃、烯烃、炔烃、芳香烃、卤代烃、OVOCs、有机硫），用于物种组成、"
                "活性物种与臭氧生成潜势（OFP）物种贡献、特征比值（B/T 等）与来源指向分析。"
                "返回时序浓度、数值化占比和物种浓度 Top10（topTenResultAvg）。"
                "站点名→编码映射内置（组分站点编码以 b 结尾，与常规监测站点是两套体系）；"
                "每次只查询一个组分站点，多站点在同一轮并行多次调用；"
                "小时粒度单次查询窗口不超过 24 小时。"
                "类别级（烷烃/烯烃等 8 大类）汇总用 get_vocs_data，不要用本工具。"
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
                        "description": "数据审核类型：0原始（默认），1终审，4初审，5复审"
                    },
                    "species": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "可选：指定物种中文名列表（如 ['乙烯','丙烯','苯','甲苯']），"
                            "留空返回全部 117 种"
                        ),
                    }
                },
                "required": ["start_time", "end_time"],
            }
        }

        super().__init__(
            name="get_vocs_species",
            description="Query VOCs species-level data (117 species) from Guangdong super station.",
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
        species: Union[List[str], None] = None,
        **_: Any
    ) -> Dict[str, Any]:
        """执行 VOCs 物种级查询"""

        station, code, error = resolve_component_station(locations=locations, station=station, code=code, require_domain="vocs")
        if error:
            return error

        granularity_raw = time_granularity if time_granularity is not None else table_type
        if granularity_raw is None:
            granularity_raw = 1
        table_type_value = int(granularity_raw)

        # 物种过滤：只接受字典内物种名；未识别的 speciesname 忽略并记录
        unknown_species: List[str] = []
        selected_species: Union[List[str], None] = None
        if species:
            selected_species = []
            for name in species:
                name = str(name).strip()
                if name in VOC_SPECIES_SET:
                    if name not in selected_species:
                        selected_species.append(name)
                elif name:
                    unknown_species.append(name)

        logger.info(
            "voc_species_tool_query_start",
            station=station,
            code=code,
            start_time=start_time,
            end_time=end_time,
            time_granularity=table_type_value,
            data_type=data_type,
            species_filter=len(selected_species) if selected_species else "all"
        )

        client = get_voc_api_client()
        api_result = client.get_voc_species(
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
            records = result.get("dataList", [])
            prop_data = result.get("resultDataProp", [])
            top_ten = result.get("topTenResultAvg", [])

            if not records:
                return {
                    "success": False,
                    "error": "No VOCs species records found",
                    "station": station,
                    "code": code
                }

            # 剥离 *_Mark 标识字段后标准化
            records = filter_mark_fields(records)
            standardized_records = [
                self._standardize_species_record(record, selected_species)
                for record in records
            ]

            # 数据外部化：117 物种全量数据必须落盘，返回 Top 物种样本
            sample_species = selected_species if selected_species else _SAMPLE_SPECIES
            file_path = None
            sample_data = standardized_records
            try:
                file_path = context.save_data(
                    data=standardized_records,
                    schema="vocs_species_unified",
                    metadata={
                        "component_type": "vocs_species",
                        "station": station,
                        "station_name": station,
                        "code": code,
                        "start_time": start_time,
                        "end_time": end_time,
                        "record_count": len(standardized_records),
                        "table_type": table_type_value,
                        "data_type": data_type,
                        "species_requested": selected_species,
                        "species_total": len(VOC_ALL_SPECIES),
                    }
                )
                if len(standardized_records) > 24:
                    sample_data = (
                        self._sample_records(standardized_records[:12], sample_species)
                        + self._sample_records(standardized_records[-12:], sample_species)
                    )
                else:
                    sample_data = self._sample_records(standardized_records, sample_species)

                logger.info(
                    "voc_species_data_externalized",
                    total_count=len(standardized_records),
                    file_path=file_path
                )
            except Exception as save_error:
                logger.warning("voc_species_save_failed", error=str(save_error))
                file_path = None

            quality_report = self._analyze_quality(standardized_records, selected_species)

            if file_path:
                summary_msg = (
                    f"成功获取{len(standardized_records)}条VOCs物种级数据"
                    f"（已保存数据引用，返回样本{len(sample_data)}条）"
                )
            else:
                summary_msg = f"成功获取{len(standardized_records)}条VOCs物种级数据"

            return {
                "success": True,
                "data": sample_data,
                "file_path": file_path,
                "count": len(standardized_records),
                "sample_count": len(sample_data),
                "station": station,
                "code": code,
                "table_type": table_type_value,
                "data_type": data_type,
                "species_requested": selected_species,
                "unknown_species": unknown_species,
                "top_ten_avg": top_ten,
                "prop_data": prop_data if selected_species else None,
                "quality_report": quality_report,
                "summary": summary_msg,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "get_vocs_species",
                    "station_name": station,
                    "code": code,
                    "total_count": len(standardized_records),
                    "externalized": file_path is not None,
                    "species_catalog": voc_species_catalog_text() if not selected_species else None,
                }
            }

        except Exception as e:
            logger.error("voc_species_tool_query_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "station": station,
                "code": code
            }

    def _standardize_species_record(
        self,
        record: Dict[str, Any],
        selected_species: Union[List[str], None]
    ) -> Dict[str, Any]:
        """标准化单条物种记录：时间/站点元信息 + measurements 物种浓度。"""
        measurements: Dict[str, Any] = {}
        for key, value in record.items():
            if key in ("TimePoint", "Code", "StationName", "DataType", "TimeType"):
                continue
            if selected_species is not None and key not in selected_species:
                continue
            measurements[key] = self._safe_float(value)

        return {
            "timestamp": record.get("TimePoint"),
            "station_code": record.get("Code"),
            "station_name": record.get("StationName"),
            "data_type": record.get("DataType"),
            "measurements": measurements,
        }

    def _sample_records(self, records: List[Dict[str, Any]], species: List[str]) -> List[Dict[str, Any]]:
        """样本裁剪：每条记录只保留样本物种列。"""
        sampled = []
        for record in records:
            measurements = record.get("measurements", {})
            sampled.append({
                "timestamp": record.get("timestamp"),
                "station_name": record.get("station_name"),
                "measurements": {k: measurements.get(k) for k in species if k in measurements},
            })
        return sampled

    def _analyze_quality(
        self,
        records: List[Dict[str, Any]],
        selected_species: Union[List[str], None]
    ) -> Dict[str, Any]:
        """数据完整性：物种字段有效率统计（Top 物种逐项，其余汇总）。"""
        if not records:
            return {}

        measured_keys = list(records[0].get("measurements", {}).keys())
        report: Dict[str, Any] = {
            "total_records": len(records),
            "species_fields": len(measured_keys),
        }

        def completeness(field: str) -> Dict[str, Any]:
            valid = sum(
                1 for r in records
                if r.get("measurements", {}).get(field) is not None
            )
            return {"valid_count": valid, "total": len(records), "completeness": round(valid / len(records), 3)}

        focus = selected_species if selected_species else measured_keys[:10]
        for field in focus:
            report[field] = completeness(field)

        all_valid = sum(
            1
            for r in records
            for v in r.get("measurements", {}).values()
            if v is not None
        )
        total_cells = len(records) * len(measured_keys)
        report["overall_completeness"] = round(all_valid / total_cells, 3) if total_cells else None
        return report

    def _safe_float(self, value: Any) -> Any:
        """安全转换为浮点数（占位符 — 返回 None）。"""
        if value is None or value == "" or value == "—":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return value


def __init__() -> GetVOCsSpeciesTool:
    return GetVOCsSpeciesTool()
