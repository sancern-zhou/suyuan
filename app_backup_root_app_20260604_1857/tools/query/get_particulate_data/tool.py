"""
Particulate component data query tool.

This tool fetches particulate matter (PM2.5, PM10) component data
including ion species (SO4, NO3, NH4), carbonaceous species (OC, EC),
and trace elements using natural language queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.http_client import http_client
from app.validators import validate_particulate_samples
from config.settings import settings

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetParticulateDataTool(LLMTool):
    """Natural-language particulate component data query tool."""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_particulate_data",
            "description": (
                "【兜底工具】使用自然语言查询颗粒物组分数据。"
                "IMPORTANT: 优先使用专业工具："
                "- 离子组分(SO4, NO3, NH4等) → 使用 get_pm25_ionic 工具"
                "- 碳组分(OC/EC) → 使用 get_pm25_carbon 工具"
                "- 地壳元素/微量元素 → 使用 get_pm25_crustal 工具"
                "只有在专业工具不可用时，才使用此工具进行自然语言查询。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Natural language query describing the particulate data to fetch. "
                            "Should include location (city/station name), time range, "
                            "and data type (e.g., '广州PM2.5组分数据，2025年1月1日到7日')."
                        ),
                    }
                },
                "required": ["question"],
            },
        }

        super().__init__(
            name="get_particulate_data",
            description="Fetch particulate matter component data (PM2.5, PM10 components).",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            requires_context=True,
        )

        # 禁用此工具，强制使用结构化查询工具
        # get_pm25_ionic (水溶性离子)
        # get_pm25_carbon (碳组分 OC/EC)
        # get_pm25_crustal (地壳元素)
        self.disable(reason="已禁用：请使用结构化查询工具（get_pm25_ionic/get_pm25_carbon/get_pm25_crustal）")

    async def execute(
        self,
        context: "ExecutionContext",
        question: str,
        **_: Any
    ) -> Dict[str, Any]:
        # 【调试日志】显示查询参数
        logger.info(
            "particulate_data_query_start",
            question=question,
            question_length=len(question)
        )

        data = await self._query_particulate(question)
        data_type = "particulate components"

        if not isinstance(data, list):
            return {
                "success": False,
                "error": "API returned an unexpected structure.",
                "summary": "Particulate query failed due to unexpected response format.",
                "question": question,
            }

        count = len(data)
        if count == 0:
            return {
                "success": False,
                "error": "No particulate data found.",
                "summary": "No particulate data was available for the requested query.",
                "data": [],
                "count": 0,
                "question": question,
            }

        # 【调试日志】显示返回数据的字段统计
        if data:
            first_record = data[0] if isinstance(data[0], dict) else {}
            all_fields = set()
            for record in data[:10]:  # 检查前10条
                if isinstance(record, dict):
                    all_fields.update(record.keys())

            # 检查目标离子/元素是否存在
            target_ions = ['SO4', 'NO3', 'NH4', 'Cl', 'Ca', 'Mg', 'K', 'Na']
            target_carbon = ['OC', 'EC']
            target_crustal = ['Al', 'Si', 'Fe', 'Ca', 'Mg', 'K', 'Na', 'Ti']
            target_trace = ['Zn', 'Pb', 'Cu', 'Cd', 'As', 'Ni', 'Cr', 'Mn']

            found_ions = [f for f in target_ions if f in all_fields]
            found_carbon = [f for f in target_carbon if f in all_fields]
            found_crustal = [f for f in target_crustal if f in all_fields]
            found_trace = [f for f in target_trace if f in all_fields]

            logger.info(
                "particulate_data_query_result",
                question=question,
                record_count=count,
                total_fields=len(all_fields),
                fields=list(all_fields)[:20],  # 只显示前20个字段
                found_ions=found_ions,
                found_carbon=found_carbon,
                found_crustal=found_crustal,
                found_trace=found_trace,
                sample_record={k: v for k, v in list(first_record.items())[:15]}  # 显示前15个字段
            )

        validation_result = self._validate_records(data)

        logger.info(
            "particulate_data_query_success",
            question=question,
            count=count,
        )

        # Context-Aware V2: 保存数据到执行上下文
        # 【修复】使用 particulate_unified schema，因为API返回扁平数据需要转换
        data_id = None
        try:
            data_id = context.save_data(
                data=data,
                schema="particulate_unified",
                metadata={
                    "question": question,
                    "record_count": count,
                    "data_type": "particulate",
                }
            )
            # 【调试日志】显示保存的数据ID和关键信息
            logger.info(
                "particulate_data_saved",
                data_id=data_id,
                record_count=count,
                question_preview=question[:100] if len(question) > 100 else question
            )
        except Exception as save_error:
            logger.warning("particulate_data_save_failed", error=str(save_error))

        # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
        sample_record = data[0] if data else None
        if sample_record:
            # 提取关键字段用于样本展示
            sample_summary = {
                "station_name": sample_record.get("station_name"),
                "timestamp": sample_record.get("timestamp"),
                "measurements": sample_record.get("measurements", {}),
                "components": sample_record.get("components"),
            }
        else:
            sample_summary = None

        return {
            "success": True,
            "status": "success",
            "data": data,
            "data_id": data_id,  # 顶层 data_id
            "count": count,
            "question": question,
            "data_type": data_type,
            "summary": f"[OK] 成功获取{count}条颗粒物组分数据，已保存为 {data_id}。",  # summary包含data_id
            "registry_schema": "particulate_unified",
            "metadata": {
                "tool_name": "get_particulate_data",
                "question": question,
                "record_count": count,
                "data_type": "particulate",
                "sample_record": sample_summary,  # 添加数据样本
            },
            "quality_report": (
                validation_result["quality_report"] if validation_result else None
            ),
            "field_stats": (
                validation_result["field_stats"] if validation_result else None
            ),
            "validation_issues": (
                validation_result["issues"] if validation_result else None
            ),
            "validation_summary": (
                validation_result["summary"] if validation_result else None
            ),
        }

    async def _query_particulate(self, question: str) -> List[Dict[str, Any]]:
        url = f"{settings.particulate_data_api_url}/api/uqp/query"
        # 使用专用超时配置（2分钟，与VOCs工具一致）
        timeout = getattr(settings, 'particulate_api_timeout_seconds', 120)
        response = await http_client.post(url, json_data={"question": question}, timeout=timeout)
        return self._extract_list(response)

    def _extract_list(self, response: Any) -> List[Dict[str, Any]]:
        # 【调试】记录响应结构
        logger.info("particulate_response_debug", response_type=type(response).__name__)
        if isinstance(response, dict):
            logger.info("particulate_response_keys", keys=list(response.keys()))
            # 检查 data 字段
            data_value = response.get("data")
            if data_value is not None:
                logger.info("particulate_data_field_type", data_type=type(data_value).__name__)
                if isinstance(data_value, dict):
                    logger.info("particulate_data_field_keys", keys=list(data_value.keys()))

        records = self._seek_records(response)
        if records:
            return records

        logger.warning(
            "particulate_data_unexpected_response",
            response_type=type(response),
        )
        return []

    def _seek_records(self, payload: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(payload, list):
            # 列表直接规范化
            result = self._ensure_dict_list(payload)
            if result:
                return result
            return None

        if isinstance(payload, dict):
            # 【关键修复】优先检查嵌套路径 data.result（颗粒物API返回结构）
            data_value = payload.get("data")
            if isinstance(data_value, dict):
                # 【新增】检查并发查询返回结构：data.results（数组）
                results_value = data_value.get("results")
                if isinstance(results_value, list) and len(results_value) > 0:
                    # 并发查询返回结构，需要合并所有结果
                    logger.info("particulate_concurrent_query_detected", results_count=len(results_value))
                    all_records = []
                    for i, result_item in enumerate(results_value):
                        if isinstance(result_item, dict):
                            result_data = result_item.get("data")
                            if isinstance(result_data, dict):
                                result_inner = result_data.get("result")
                                if isinstance(result_inner, dict):
                                    # 优先检查 resultData（碳组分）
                                    result_data_list = result_inner.get("resultData")
                                    if isinstance(result_data_list, list) and len(result_data_list) > 0:
                                        records = self._ensure_dict_list(result_data_list)
                                        if records:
                                            all_records.extend(records)
                                            logger.info(f"particulate_records_from_resultData_{i}", count=len(records))

                                    # 再检查 resultOne（水溶性离子、地壳元素、微量元素）
                                    result_one_list = result_inner.get("resultOne")
                                    if isinstance(result_one_list, list) and len(result_one_list) > 0:
                                        records = self._ensure_dict_list(result_one_list)
                                        if records:
                                            all_records.extend(records)
                                            logger.info(f"particulate_records_from_resultOne_{i}", count=len(records))
                    if all_records:
                        logger.info("particulate_all_records_merged", total_count=len(all_records))
                        return all_records

                result_value = data_value.get("result")
                if isinstance(result_value, dict):
                    # 【碳组分使用 resultData，水溶性离子/地壳元素/微量元素使用 resultOne】
                    # 优先检查 resultData（碳组分）
                    result_data = result_value.get("resultData")
                    if isinstance(result_data, list) and len(result_data) > 0:
                        result = self._ensure_dict_list(result_data)
                        if result:
                            logger.info("particulate_records_found", source="data.result.resultData", count=len(result))
                            return result

                    # 再检查 resultOne（水溶性离子、地壳元素、微量元素）
                    result_one = result_value.get("resultOne")
                    if isinstance(result_one, list) and len(result_one) > 0:
                        result = self._ensure_dict_list(result_one)
                        if result:
                            logger.info("particulate_records_found", source="data.result.resultOne", count=len(result))
                            return result

                # 【调试】检查 result 中是否有数据
                if result_value is not None:
                    logger.info("particulate_result_field", result_type=type(result_value).__name__, result_keys=list(result_value.keys()) if isinstance(result_value, dict) else "not_dict")

            # 【调试】记录顶层 keys
            logger.info("particulate_seek_top_keys", keys=list(payload.keys()))

            # 优先查找常见的记录容器key (包括 resultData, resultOne)
            for key in ("hours", "dataList", "data_list", "records", "items",
                        "resultData", "resultOne", "data", "result"):
                value = payload.get(key)
                if isinstance(value, list) and len(value) > 0:
                    result = self._ensure_dict_list(value)
                    if result:
                        return result

            # 递归检查嵌套的dict/list
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    nested = self._seek_records(value)
                    if nested:
                        return nested

        return None

    def _ensure_dict_list(self, payload: List[Any]) -> Optional[List[Dict[str, Any]]]:
        """规范化列表，只返回包含字典的列表"""
        result = []
        for item in payload:
            if isinstance(item, dict):
                result.append(item)
        return result if result else None

    def _validate_records(self, data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate particulate data records."""
        try:
            result = validate_particulate_samples(data)
            # ValidationResult是Pydantic模型，使用属性访问而非get方法
            return {
                "quality_report": result.report,
                "field_stats": result.field_stats,
                "issues": list(result.report.issues) if result.report.issues else [],
                "summary": result.report.summary,
            }
        except Exception as e:
            logger.warning("particulate_validation_failed", error=str(e))
            return None
