"""
Carbon component data query tool.

This tool fetches PM2.5/PM10 carbon component data (OC, EC) from the external API.
Uses resultData path from the API response.

Usage:
    get_carbon_data(question: str) -> Dict
    - question: Natural language query with location, time range, and carbon components requirement
    - Returns: Dict with data_id, records containing OC/EC data
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.utils.http_client import http_client
from config.settings import settings

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetCarbonDataTool(LLMTool):
    """Carbon component data query tool (OC, EC only)."""

    def __init__(self) -> None:
        function_schema = {
            "name": "get_carbon_data",
            "description": (
                "Fetch PM2.5/PM10 carbon component data (OC, EC) using natural language. "
                "This tool specifically queries carbon components from resultData API path. "
                "Use this tool when you need OC (organic carbon) and EC (elemental carbon) data "
                "for carbon analysis, EC/OC ratio, POC/SOC calculation, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Natural language query describing the carbon data to fetch. "
                            "Should include location (city/station name), time range, "
                            "and explicit mention of carbon components (OC, EC). "
                            "Example: '清远市2025-12-24的PM2.5碳组分数据，时间粒度为小时，要求包含 OC（有机碳）、EC（元素碳）'"
                        ),
                    }
                },
                "required": ["question"],
            },
        }

        super().__init__(
            name="get_carbon_data",
            description="Fetch PM2.5/PM10 carbon component data (OC, EC).",
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
        logger.info("carbon_data_query_start", question=question)

        data = await self._query_carbon_data(question)

        if not isinstance(data, list):
            return {
                "success": False,
                "error": "API returned an unexpected structure.",
                "summary": "Carbon data query failed due to unexpected response format.",
                "question": question,
            }

        count = len(data)
        if count == 0:
            return {
                "success": False,
                "error": "No carbon data found.",
                "summary": "No carbon data was available for the requested query.",
                "data": [],
                "count": 0,
                "question": question,
            }

        # 记录返回的字段，用于调试
        if data:
            first_record = data[0]
            fields = list(first_record.keys()) if isinstance(first_record, dict) else []
            logger.info(
                "carbon_data_query_success",
                question=question,
                count=count,
                fields=fields[:10],  # 只记录前10个字段
            )

        # Context-Aware V2: 保存数据到执行上下文
        data_id = None
        try:
            data_id = context.save_data(
                data=data,
                schema="particulate_unified",
                metadata={
                    "question": question,
                    "record_count": count,
                    "data_type": "carbon_components",
                    "components": ["OC", "EC"],
                }
            )
            logger.info("carbon_data_saved", data_id=data_id, record_count=count)
        except Exception as save_error:
            logger.warning("carbon_data_save_failed", error=str(save_error))

        # 检查数据中是否有 OC 和 EC
        has_oc = any(
            isinstance(r, dict) and ('OC' in r or 'oc' in r.lower())
            for r in data
        )
        has_ec = any(
            isinstance(r, dict) and ('EC' in r or 'ec' in r.lower())
            for r in data
        )

        # 生成数据样本（第一条记录，用于LLM快速了解数据结构）
        sample_record = None
        if data:
            first = data[0]
            sample_record = {
                "timestamp": first.get("timestamp"),
                "station_name": first.get("station_name"),
                "measurements": first.get("measurements", {}),
                "components": first.get("components")
            }

        return {
            "success": True,
            "data": data,
            "data_id": data_id,
            "count": count,
            "question": question,
            "data_type": "carbon_components",
            "has_oc": has_oc,
            "has_ec": has_ec,
            "summary": f"[OK] 成功获取{count}条碳组分数据（OC/EC），已保存为 {data_id}。",
            "registry_schema": "particulate_unified",
            "metadata": {
                "question": question,
                "records": count,
                "data_type": "carbon_components",
                "components": ["OC", "EC"],
                "sample_record": sample_record
            },
        }

    async def _query_carbon_data(self, question: str) -> List[Dict[str, Any]]:
        """Query carbon data from the external API."""
        url = f"{settings.particulate_data_api_url}/api/uqp/query"
        timeout = getattr(settings, 'particulate_api_timeout_seconds', 120)
        response = await http_client.post(url, json_data={"question": question}, timeout=timeout)
        return self._extract_carbon_records(response)

    def _extract_carbon_records(self, response: Any) -> List[Dict[str, Any]]:
        """Extract carbon component records from API response.

        The API returns carbon data in resultData path.
        """
        logger.info(
            "carbon_response_debug",
            response_type=type(response).__name__
        )

        if isinstance(response, dict):
            # 检查嵌套结构
            data_value = response.get("data")
            if isinstance(data_value, dict):
                result_value = data_value.get("result")
                if isinstance(result_value, dict):
                    # 碳组分在 resultData 中
                    result_data = result_value.get("resultData")
                    if isinstance(result_data, list) and len(result_data) > 0:
                        logger.info(
                            "carbon_records_found",
                            source="data.result.resultData",
                            count=len(result_data)
                        )
                        return self._ensure_dict_list(result_data)

            # 调试：记录顶层 keys
            logger.info(
                "carbon_seek_top_keys",
                keys=list(response.keys())
            )

        # 兜底：尝试查找任何包含 OC/EC 的数据
        return self._seek_carbon_records(response)

    def _seek_carbon_records(self, payload: Any) -> List[Dict[str, Any]]:
        """Seek carbon records from any nested structure."""
        if isinstance(payload, dict):
            # 优先查找 resultData
            for key in ("resultData", "dataList", "records", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    # 检查是否包含 OC/EC
                    if self._contains_carbon_data(value):
                        return self._ensure_dict_list(value)

            # 递归检查
            for value in payload.values():
                if isinstance(value, (dict, list)):
                    result = self._seek_carbon_records(value)
                    if result:
                        return result

        elif isinstance(payload, list):
            if self._contains_carbon_data(payload):
                return self._ensure_dict_list(payload)

        logger.warning("carbon_data_not_found_in_response")
        return []

    def _contains_carbon_data(self, data: List[Any]) -> bool:
        """Check if the list contains carbon component data (OC, EC)."""
        for item in data[:5]:  # 只检查前5条
            if isinstance(item, dict):
                keys = [k.upper() for k in item.keys()]
                if 'OC' in keys or 'EC' in keys:
                    return True
        return False

    def _ensure_dict_list(self, payload: List[Any]) -> Optional[List[Dict[str, Any]]]:
        """Ensure the payload is a list of dictionaries."""
        result = []
        for item in payload:
            if isinstance(item, dict):
                result.append(item)
        return result if result else None


# Export for tool registration
GetCarbonDataTool = GetCarbonDataTool


if __name__ == "__main__":
    # Test example
    import asyncio

    async def test():
        tool = GetCarbonDataTool()
        result = await tool.execute(
            context=None,
            question="清远市2025-12-24的PM2.5碳组分数据，要求包含 OC、EC"
        )
        print(f"Success: {result['success']}")
        print(f"Count: {result.get('count', 0)}")
        print(f"Has OC: {result.get('has_oc', False)}")
        print(f"Has EC: {result.get('has_ec', False)}")

    asyncio.run(test())
