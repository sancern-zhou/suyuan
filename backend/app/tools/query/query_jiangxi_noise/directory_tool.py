"""江西省噪声站点与区县目录 LLM 查询工具。

为其他江西噪声工具提供“名称→编码”解析依据：站点编码、区县编码、城市编码、
功能区类型、经纬度与设备状态。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import (
    JIANGXI_CITY_CODES,
    JiangxiNoiseDataClient,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.common import (
    ToolInputError,
    list_response,
    tool_error_response,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class GetJiangxiNoiseDirectoryTool(LLMTool):
    """查询江西省噪声监测站点与区县编码目录。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        function_schema = {
            "name": "get_jiangxi_noise_directory",
            "description": (
                "查询江西省噪声监测站点与行政区划目录，用于把站点/区县名称解析成其他"
                "江西噪声工具所需的编码。"
                "target=station 返回启用监测站点清单（站点编码stationCode、名称、"
                "所属区县与城市、功能区类型、经纬度、启停状态）；"
                "target=region 返回行政区划清单（区县/城市编码与名称、层级）。"
                "站点查询可按城市名过滤（支持：" + "、".join(JIANGXI_CITY_CODES.keys()) + "）。"
            ),
            "parameters": {
                "type": "object",
                "oneOf": [
                    {
                        "title": "站点目录",
                        "type": "object",
                        "properties": {
                            "target": {"const": "station"},
                            "city_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "按城市名称过滤（可选），例如 [\"南昌市\"]",
                            },
                        },
                        "required": ["target"],
                        "additionalProperties": False,
                    },
                    {
                        "title": "行政区划目录",
                        "type": "object",
                        "properties": {
                            "target": {"const": "region"},
                        },
                        "required": ["target"],
                        "additionalProperties": False,
                    },
                ],
            },
        }
        super().__init__(
            name="get_jiangxi_noise_directory",
            description="查询江西省噪声监测站点清单与行政区划编码（名称→编码解析）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False,
        )
        self._client = client

    def _get_client(self) -> JiangxiNoiseDataClient:
        if self._client is None:
            self._client = JiangxiNoiseDataClient.from_env()
        return self._client

    async def execute(
        self,
        context: ExecutionContext | None = None,
        target: str = "",
        city_names: list[str] | None = None,
    ) -> dict[str, Any]:
        del context
        try:
            client = self._get_client()
            if target == "station":
                result = await client.query_platform_api("station_directory")
                data = result.get("data", [])
                if city_names:
                    from app.external_apis.jiangxi_noise_api_client import (
                        resolve_city_codes,
                    )

                    wanted = set(resolve_city_codes(
                        [str(name).strip() for name in city_names if str(name).strip()]
                    ))
                    data = [
                        item
                        for item in data
                        if isinstance(item, dict)
                        and str(item.get("cityCode") or item.get("CityCode") or "") in wanted
                    ]
                response = list_response(
                    variant="station_directory",
                    result={"success": True, "data": data, "total_count": len(data)},
                    limit=1000,
                    extra={"target": "station"},
                )
            elif target == "region":
                result = await client.query_platform_api("region_directory")
                response = list_response(
                    variant="region_directory", result=result, limit=1000,
                    extra={"target": "region"},
                )
            else:
                raise ToolInputError("invalid_target", "target 必须是 station 或 region")
            logger.info(
                "jiangxi_noise_directory_success",
                target=target,
                count=response.get("count"),
            )
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_directory_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
