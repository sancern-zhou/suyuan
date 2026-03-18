"""
VOCs component data query tool.

This tool fetches VOCs (Volatile Organic Compounds) component data
including OFP (Ozone Formation Potential) data using natural language queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.http_client import http_client
from app.validators import validate_vocs_samples
from config.settings import settings

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetVOCsDataTool(LLMTool):
    """Natural-language VOCs component data query tool."""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_vocs_data",
            "description": (
                "Fetch VOCs (Volatile Organic Compounds) component data or OFP "
                "(Ozone Formation Potential) data using a natural language query "
                "that includes station/city, time range, and data type. "
                "Use this tool for VOCs species concentrations, OFP analysis, "
                "and related organic compound data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Natural language query describing the VOCs data to fetch. "
                            "Should include location (city/station name), time range, "
                            "and data type (e.g., '广州VOCs数据，2025年1月1日到7日')."
                        ),
                    }
                },
                "required": ["question"],
            },
        }

        super().__init__(
            name="get_vocs_data",
            description="Fetch VOCs component data (VOCs, OFP, volatile organic compounds).",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            requires_context=True,
        )

    async def execute(
        self,
        context: "ExecutionContext",
        question: str,
        **_: Any
    ) -> Dict[str, Any]:
        logger.info("vocs_data_query_start", question=question)

        data = await self._query_vocs(question)
        data_type = "VOCs components"

        if not isinstance(data, list):
            return {
                "success": False,
                "error": "API returned an unexpected structure.",
                "summary": "VOCs query failed due to unexpected response format.",
                "question": question,
            }

        count = len(data)
        if count == 0:
            return {
                "success": False,
                "error": "No VOCs data found.",
                "summary": "No VOCs data was available for the requested query.",
                "data": [],
                "count": 0,
                "question": question,
            }

        validation_result = self._validate_records(data)

        logger.info(
            "vocs_data_query_success",
            question=question,
            count=count,
        )

        # 【修复】使用验证后的标准化数据，而非原始数据
        # validate_vocs_samples 返回 VOCsSample 对象列表，包含 species 字段
        validated_data = None
        if validation_result and validation_result.get("normalized_samples"):
            # 将 VOCsSample 对象转换为字典列表供保存
            validated_data = validation_result["normalized_samples"]
            logger.info(
                "vocs_data_validated",
                original_count=count,
                validated_count=len(validated_data),
                species_count=len(validated_data[0].get("species", {})) if validated_data else 0
            )

        # 使用验证后的数据（如果验证失败则使用原始数据）
        data_to_save = validated_data if validated_data else data

        # Context-Aware V2: 保存数据到执行上下文
        # 【修复】使用 vocs_unified schema，数据会通过Schema层的model_validator自动转换
        # 【关键修复】同时传入 field_stats，供 PMF 验证时检查物种数量
        data_ref = None
        file_path = None
        field_stats = validation_result["field_stats"] if validation_result else None
        try:
            data_ref = context.save_data(
                data=data_to_save,  # 【修复】使用验证后的数据，包含完整的 species 字段
                schema="vocs_unified",
                field_stats=field_stats,  # 传入验证器生成的字段统计
                metadata={
                    "question": question,
                    "record_count": count,
                    "data_type": "vocs",
                }
            )
            data_id = data_ref["data_id"]
            file_path = data_ref["file_path"]
            logger.info("vocs_data_saved", data_id=data_id, file_path=file_path, record_count=count, field_stats_count=len(field_stats) if field_stats else 0)
        except Exception as save_error:
            logger.warning("vocs_data_save_failed", error=str(save_error))

        # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
        sample_record = data[0] if data else None
        if sample_record:
            # 提取关键字段用于样本展示
            sample_summary = {
                "station_name": sample_record.get("station_name"),
                "timestamp": sample_record.get("timestamp"),
                "measurements": sample_record.get("measurements", {}),
                "species_data": sample_record.get("species_data"),
            }
        else:
            sample_summary = None

        return {
            "success": True,
            "status": "success",
            "data": data,
            "data_id": data_id,
            "file_path": file_path,  # 顶层 data_id
            "file_path": file_path,  # 新增：文件路径（混合方案）
            "count": count,
            "question": question,
            "data_type": data_type,
            "summary": f"[OK] 成功获取{count}条VOCs数据，已保存为 {data_id}（路径: {file_path}）。",
            "metadata": {
                "schema_version": "v2.0",
                "generator": "get_vocs_data",
                "question": question,
                "record_count": count,
                "data_type": "vocs",
                "sample_record": sample_summary,  # 添加数据样本
            },
            "registry_schema": "vocs",
            "registry_metadata": {
                "question": question,
                "records": count,
                "data_type": "vocs",
            },
            "quality_report": (
                validation_result["quality_report"] if validation_result else None
            ),
            "field_stats": field_stats,
            "validation_issues": (
                validation_result["issues"] if validation_result else None
            ),
            "validation_summary": (
                validation_result["summary"] if validation_result else None
            ),
        }

    async def _query_vocs(self, question: str) -> List[Dict[str, Any]]:
        url = f"{settings.vocs_data_api_url}/api/uqp/query"
        response = await http_client.post(url, json_data={"question": question})
        return self._extract_list(response)

    def _extract_list(self, response: Any) -> List[Dict[str, Any]]:
        records = self._seek_records(response)
        if records:
            return records

        logger.warning(
            "vocs_data_unexpected_response",
            response_type=type(response),
        )
        return []

    def _seek_records(self, payload: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(payload, list):
            for item in payload:
                nested = self._seek_records(item)
                if nested:
                    return nested
            return self._ensure_dict_list(payload)

        if isinstance(payload, dict):
            for key in ("hours", "dataList", "data_list", "records", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    normalised = self._ensure_dict_list(value)
                    if normalised:
                        return normalised

            for value in payload.values():
                nested = self._seek_records(value)
                if nested:
                    return nested

        return None

    def _ensure_dict_list(self, payload: List[Any]) -> List[Dict[str, Any]]:
        normalised: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                nested = self._seek_records(item)
                if nested:
                    return nested
                normalised.append(item)
        return normalised

    def _validate_records(self, data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate VOCs data records."""
        try:
            result = validate_vocs_samples(data)
            # 【修复】ValidationResult是Pydantic BaseModel，使用属性访问而非.get()
            # 将issues转换为可序列化的dict列表，同时保留normalized_samples供保存使用
            issues = [issue.dict() for issue in result.report.issues] if result.report.issues else []
            normalized_samples = [sample.dict() for sample in result.normalized_samples] if result.normalized_samples else []
            return {
                "quality_report": result.report.dict() if result.report else None,
                "field_stats": [fs.dict() for fs in result.field_stats] if result.field_stats else [],
                "issues": issues,
                "summary": result.report.summary if result.report else None,
                "normalized_samples": normalized_samples,  # 【新增】保留标准化后的样本数据
            }
        except Exception as e:
            logger.warning("vocs_validation_failed", error=str(e))
            return None
