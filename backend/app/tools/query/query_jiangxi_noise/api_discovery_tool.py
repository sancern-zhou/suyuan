"""江西噪声平台接口目录工具（发现式接入）。

三个极小常驻工具替代逐接口注册独立 LLM 工具，避免 schema 常驻膨胀：
- search_jiangxi_noise_apis：关键词检索接口目录；
- describe_jiangxi_noise_api：按需获取单接口参数契约；
- call_jiangxi_noise_api：校验、编码并执行调用。

机制对照 ZCode tool_search/deferred_tools：目录常驻、契约按需（describe_table
模式），不依赖 provider 侧延迟加载能力。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from app.external_apis.jiangxi_noise_api_client import (
    JiangxiNoiseClientError,
    JiangxiNoiseDataClient,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.query.query_jiangxi_noise.api_catalog import API_CATALOG, score_apis
from app.tools.query.query_jiangxi_noise.common import (
    ToolInputError,
    list_response,
    parse_datetime_param,
    platform_time,
    tool_error_response,
    validate_max_results,
)

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()

_CALL_RESULT_LIMIT = 200

_LIST_TYPES = frozenset({"string_list", "datetime_list"})

_search_schema = {
    "name": "search_jiangxi_noise_apis",
    "description": (
        "按关键词检索江西省噪声平台的数据接口目录"
        "（报表/专项分析/日历/排名/噪声源等），返回接口名与一句话说明；"
        "命中后先 describe_jiangxi_noise_api 获取参数契约再调用"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "空格分隔的中文/英文关键词，例如：超标 事件 排名",
            },
            "max_results": {
                "type": "integer",
                "default": 8,
                "description": "最多返回条数",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

_describe_schema = {
    "name": "describe_jiangxi_noise_api",
    "description": (
        "获取目录中指定接口的参数契约（字段/类型/枚举/必填/示例）；"
        "调用 call_jiangxi_noise_api 前必读"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "api": {
                "type": "string",
                "description": "search_jiangxi_noise_apis 返回的接口名",
            },
        },
        "required": ["api"],
        "additionalProperties": False,
    },
}

_call_schema = {
    "name": "call_jiangxi_noise_api",
    "description": (
        "执行目录中的江西噪声平台接口（仅限 search_jiangxi_noise_apis"
        " 列出的接口，参数以 describe_jiangxi_noise_api 契约为准）"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "api": {
                "type": "string",
                "description": "接口名（目录键）",
            },
            "params": {
                "type": "object",
                "description": "按契约传入的参数对象；枚举可传标签或值",
            },
        },
        "required": ["api", "params"],
        "additionalProperties": False,
    },
}


def _resolve_enum(value: Any, contract: dict[str, Any], field: str) -> Any:
    enum = contract.get("enum")
    if enum is None:
        return value
    if isinstance(enum, dict):
        if value in enum.values():
            return value
        if isinstance(value, str) and value in enum:
            return enum[value]
        options = "、".join(enum.keys())
        raise ToolInputError(
            f"invalid_{field}", f"{field} 必须是：{options} 或对应值 {sorted(enum.values())}"
        )
    if value in enum:
        return value
    raise ToolInputError(
        f"invalid_{field}", f"{field} 必须是：{'、'.join(str(item) for item in enum)}"
    )


def build_call_payload(api: str, params: dict[str, Any]) -> dict[str, Any]:
    """按契约校验并编码调用参数（不区分 GET/POST，均转为平台字段形态）。"""
    entry = API_CATALOG.get(api)
    if entry is None:
        known = "、".join(sorted(API_CATALOG))
        raise ToolInputError("unknown_api", f"目录中没有接口 {api}；可用：{known}")
    if not isinstance(params, dict):
        raise ToolInputError("invalid_params", "params 必须是对象")
    contract = entry["params"]
    unknown = sorted(set(params) - set(contract))
    if unknown:
        raise ToolInputError(
            "unknown_param", f"接口 {api} 不支持参数：{'、'.join(unknown)}"
        )
    payload: dict[str, Any] = {}
    for field, rule in contract.items():
        value = params.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            if rule.get("required"):
                raise ToolInputError(f"missing_{field}", f"接口 {api} 缺少必填参数 {field}")
            default = rule.get("default")
            if default is not None:
                payload[field] = default
            continue
        field_type = rule["type"]
        if field_type == "datetime":
            payload[field] = platform_time(parse_datetime_param(value, field))
        elif field_type == "datetime_list":
            if not isinstance(value, list) or not value:
                raise ToolInputError(f"invalid_{field}", f"{field} 必须是时间数组")
            payload[field] = [
                platform_time(parse_datetime_param(item, field)) for item in value
            ]
        elif field_type in _LIST_TYPES:
            if not isinstance(value, list) or not value:
                raise ToolInputError(f"invalid_{field}", f"{field} 必须是非空数组")
            payload[field] = [str(item).strip() for item in value]
        elif field_type == "int_list":
            if not isinstance(value, list) or not value:
                raise ToolInputError(f"invalid_{field}", f"{field} 必须是非空数组")
            resolved_items: list[int] = []
            for item in value:
                if isinstance(item, bool) or not isinstance(item, (int, float, str)):
                    raise ToolInputError(f"invalid_{field}", f"{field} 必须是整数数组")
                resolved = _resolve_enum(item, rule, field)
                try:
                    resolved_items.append(int(resolved))
                except (TypeError, ValueError) as exc:
                    raise ToolInputError(f"invalid_{field}", f"{field} 必须是整数数组") from exc
            payload[field] = resolved_items
        elif field_type == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ToolInputError(f"invalid_{field}", f"{field} 必须是整数")
            resolved = _resolve_enum(value, rule, field)
            try:
                payload[field] = int(resolved)
            except (TypeError, ValueError) as exc:
                raise ToolInputError(f"invalid_{field}", f"{field} 必须是整数") from exc
        else:
            payload[field] = _resolve_enum(value, rule, field)
    return payload


def encode_query_params(payload: dict[str, Any]) -> dict[str, Any]:
    """GET 调用编码：列表按平台 name[i] 形式展开，其余平铺。"""
    query: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            for index, item in enumerate(value):
                query[f"{key}[{index}]"] = item
        else:
            query[key] = value
    return query


class SearchJiangxiNoiseApisTool(LLMTool):
    """检索江西噪声平台接口目录。"""

    def __init__(self) -> None:
        super().__init__(
            name=_search_schema["name"],
            description="检索江西噪声平台可用的数据接口目录",
            category=ToolCategory.QUERY,
            function_schema=_search_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            query = kwargs.get("query")
            if not isinstance(query, str) or not query.strip():
                raise ToolInputError("invalid_query", "query 不能为空")
            max_results = validate_max_results(kwargs.get("max_results", 8))
            results = score_apis(query, max_results=max_results)
            return {
                "success": True,
                "results": results,
                "count": len(results),
                "hint": (
                    "用 describe_jiangxi_noise_api 获取命中接口的参数契约，"
                    "再用 call_jiangxi_noise_api 调用"
                ),
            }
        except ToolInputError as exc:
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description


class DescribeJiangxiNoiseApiTool(LLMTool):
    """按需返回目录接口的参数契约。"""

    def __init__(self) -> None:
        super().__init__(
            name=_describe_schema["name"],
            description="获取江西噪声平台接口的参数契约",
            category=ToolCategory.QUERY,
            function_schema=_describe_schema,
            version="1.0.0",
            requires_context=False,
        )

    async def execute(
        self,
        context: ExecutionContext | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            api = kwargs.get("api")
            if not isinstance(api, str) or not api.strip():
                raise ToolInputError("invalid_api", "api 不能为空")
            entry = API_CATALOG.get(api.strip())
            if entry is None:
                known = "、".join(sorted(API_CATALOG))
                raise ToolInputError("unknown_api", f"目录中没有接口 {api.strip()}；可用：{known}")
            method, _ = JiangxiNoiseDataClient.API_ROUTES[entry["route"]]
            return {
                "success": True,
                "api": api.strip(),
                "summary": entry["summary"],
                "method": method,
                "params": entry["params"],
                "example": entry.get("example", {}),
                "returns": entry.get("returns", ""),
                "note": entry.get("note", ""),
                "hint": "枚举参数可传标签或值；时间用 ISO 8601，编码由 call 工具完成",
            }
        except ToolInputError as exc:
            return tool_error_response(exc)
        except KeyError:
            return tool_error_response(
                JiangxiNoiseClientError("unknown_route", f"接口 {api} 未注册到客户端路由表")
            )

    def get_description(self) -> str:
        return self.description


class CallJiangxiNoiseApiTool(LLMTool):
    """校验并执行目录接口调用。"""

    def __init__(self, client: JiangxiNoiseDataClient | None = None) -> None:
        super().__init__(
            name=_call_schema["name"],
            description="执行江西噪声平台目录接口调用",
            category=ToolCategory.QUERY,
            function_schema=_call_schema,
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
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context
        try:
            api = kwargs.get("api")
            if not isinstance(api, str) or not api.strip():
                raise ToolInputError("invalid_api", "api 不能为空")
            api = api.strip()
            entry = API_CATALOG.get(api)
            if entry is None:
                known = "、".join(sorted(API_CATALOG))
                raise ToolInputError("unknown_api", f"目录中没有接口 {api}；可用：{known}")
            payload = build_call_payload(api, kwargs.get("params") or {})
            method, _ = JiangxiNoiseDataClient.API_ROUTES[entry["route"]]
            if method == "GET":
                result = await self._get_client().query_platform_api(
                    entry["route"], params=encode_query_params(payload)
                )
            else:
                result = await self._get_client().query_platform_api(
                    entry["route"], json_body=payload
                )
            if isinstance(result.get("data"), list):
                response = list_response(
                    variant=api, result=result, limit=_CALL_RESULT_LIMIT,
                    extra={"api": api},
                )
            else:
                response = {"success": True, "api": api, "data": result.get("data")}
            response["params_sent"] = payload
            logger.info("jiangxi_noise_catalog_call_success", api=api)
            return response
        except ToolInputError as exc:
            return tool_error_response(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "jiangxi_noise_catalog_call_unexpected_error",
                error_type=type(exc).__name__,
            )
            return tool_error_response(exc)

    def get_description(self) -> str:
        return self.description
