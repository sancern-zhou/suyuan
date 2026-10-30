"""广东组分体系站点地理目录工具。

服务组分问数与综合问数中的组分站名录问题：
- 按站点名称（模糊/简称）、组分站点编码（b 结尾）、城市或区县展开组分站，
  每站带 `data_domains` 组分监测能力标注（`vocs`=VOCs 组分、`pm25`=PM2.5 组分）
- 支持 `component_types` 过滤："VOCs"（VOCs 属性站）/"颗粒物组分"（PM2.5 组分站）——
  两类监测能力不属于同一批站点，回答"某城市有无 VOCs 站"必须按能力过滤，不能按名称猜
- 城市展开后把站点名称传给 get_vocs_*/get_pm25_* 取数（不接受城市名）
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.station_directory import StationQuery
from app.services.station_directory.format import records_to_payload
from app.tools.base.tool_interface import LLMTool, ToolCategory

from .provider import ComponentStationCatalogProvider

logger = structlog.get_logger()

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

_DOMAIN_LABELS: dict[str, str] = {
    "vocs": "VOCs组分",
    "pm25": "PM2.5组分",
}

# 用户/模型可用的组分类型别名 → data_domains 值
_TYPE_ALIASES: dict[str, str] = {
    "vocs": "vocs",
    "voc": "vocs",
    "vocs组分": "vocs",
    "vocs属性": "vocs",
    "vocs属性站": "vocs",
    "挥发性有机物": "vocs",
    "pm25": "pm25",
    "pm2.5": "pm25",
    "pm2.5组分": "pm25",
    "颗粒物组分": "pm25",
    "颗粒物": "pm25",
}

_ALL_TYPE_TOKENS = frozenset({"全部", "所有", "all", "*", "any"})

_TOOL_SUMMARY = (
    "广东超站组分体系站点地理查询。按站点名称（模糊/简称）、组分站点编码（以 b 结尾）、"
    "城市或区县解析组分站，返回站点名称、组分站点编码、城市/区县归属与组分监测能力标注"
    "（data_domains：vocs=VOCs组分、pm25=PM2.5组分，含水溶性离子/碳组分/地壳元素/微量元素/质量重构）。"
    "覆盖组分取数接口支持的 38 个超站组分站点（与 get_vocs_*/get_pm25_* 工具同一清单，"
    "对比方派生站随母站归属）。注意：VOCs 属性站与颗粒物组分站不是同一批站，"
    "全省仅少数珠三角站点具备 VOCs 监测能力（多数城市只有 PM2.5 组分站），"
    "回答'某城市有无 VOCs 站/颗粒物组分站'必须按 component_types 过滤，不要按站名猜。"
    "用户按城市询问组分数据时，先用本工具展开该城市下辖组分站，"
    "再把返回的站点名称传给组分取数工具（组分工具按站点名解析编码，不接受城市名）。"
    "本工具只服务组分体系：常规监测站用 monitoring_station_catalog，运维台账用 guangdong_station_catalog。"
)


def _normalize_component_types(values: Any) -> tuple[str, ...]:
    """把 component_types 输入规范化为能力域元组；无法识别的词忽略。"""

    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    domains: list[str] = []
    for value in values:
        token = str(value or "").strip()
        if not token or token in _ALL_TYPE_TOKENS:
            continue
        domain = _TYPE_ALIASES.get(token) or _TYPE_ALIASES.get(token.lower())
        if domain and domain not in domains:
            domains.append(domain)
    return tuple(domains)


def _capability_labels(domains: tuple[str, ...] | list[str]) -> list[str]:
    return [_DOMAIN_LABELS[domain] for domain in domains if domain in _DOMAIN_LABELS]


class ComponentStationCatalogTool(LLMTool):
    """组分体系站点地理目录查询工具。"""

    def __init__(self, provider: ComponentStationCatalogProvider | None = None) -> None:
        self._provider = provider or ComponentStationCatalogProvider()
        function_schema = {
            "name": "component_station_catalog",
            "description": _TOOL_SUMMARY,
            "parameters": {
                "type": "object",
                "properties": {
                    "stations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "组分站点名称列表，支持模糊或简称匹配",
                    },
                    "station_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "组分站点编码列表（如 1004b），精确匹配",
                    },
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表（如 广州、江门市、深圳市），展开该城市下辖组分站",
                    },
                    "districts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "区县名称列表（如 从化区、鹤山市），展开该区县下辖组分站",
                    },
                    "component_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["VOCs", "颗粒物组分"],
                        },
                        "description": (
                            "组分监测类型过滤：VOCs=VOCs属性站，颗粒物组分=PM2.5组分站；"
                            "缺省返回全部组分站（含每站能力标注）"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"返回条数上限，默认 {DEFAULT_LIMIT}，最大 {MAX_LIMIT}",
                    },
                },
            },
        }
        super().__init__(
            name="component_station_catalog",
            description="Resolve Guangdong super-station component station directory",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        stations: list[str] | None = None,
        station_codes: list[str] | None = None,
        cities: list[str] | None = None,
        districts: list[str] | None = None,
        component_types: list[str] | None = None,
        limit: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        requested_limit = self._normalize_limit(limit)
        wanted_domains = _normalize_component_types(component_types)
        query = StationQuery.create(
            station_names=stations,
            station_codes=station_codes,
            cities=cities,
            districts=districts,
        )
        try:
            records = await self._provider.list_stations(query)
            all_records = await self._provider.list_stations(None)
        except Exception as exc:
            logger.error(
                "component_station_catalog_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return self._failed(str(exc))

        available_cities = sorted({item.city for item in all_records if item.city})
        domain_stats = {
            domain: sum(1 for item in all_records if domain in item.data_domains)
            for domain in _DOMAIN_LABELS
        }

        # component_types 过滤放在目录解析之后：城市/名称匹配命中但无该组分
        # 能力时，返回专用 empty 结论（"有组分站但没有这类监测能力"），
        # 避免模型把"无 VOCs 站"误报成"没有组分站"。
        matched = list(records)
        if wanted_domains:
            matched = [
                record
                for record in matched
                if any(domain in record.data_domains for domain in wanted_domains)
            ]
        payload = records_to_payload(matched, limit=requested_limit)
        for item, record in zip(payload, matched):
            item["component_capabilities"] = _capability_labels(record.data_domains)

        if not matched:
            return self._empty_result(
                records=records,
                wanted_domains=wanted_domains,
                all_records=all_records,
                available_cities=available_cities,
                domain_stats=domain_stats,
            )

        metadata = {
            "tool_name": self.name,
            "station_count": len(matched),
            "directory_total": len(all_records),
            "returned": len(payload),
            "available_cities": available_cities,
            "component_types": list(wanted_domains),
            **{
                f"{domain}_station_count": count
                for domain, count in domain_stats.items()
            },
        }
        scope = (
            f"（{'/'.join(_capability_labels(wanted_domains))}能力站）"
            if wanted_domains
            else ""
        )
        summary = f"解析到 {len(matched)} 个组分站{scope}"
        if len(payload) < len(matched):
            summary += f"（按 limit 返回前 {len(payload)} 条）"
        summary += "；每站 component_capabilities 标注其组分监测能力，"
        summary += "VOCs 组分站仅少数珠三角站点；"
        summary += "取数时把站点名称传给组分工具即可（工具内部解析编码）。"
        return {
            "status": "success",
            "success": True,
            "data": payload,
            "metadata": metadata,
            "summary": summary,
        }

    def _empty_result(
        self,
        *,
        records: list,
        wanted_domains: tuple[str, ...],
        all_records: list,
        available_cities: list[str],
        domain_stats: dict[str, int],
    ) -> dict[str, Any]:
        """构造 empty 结果：区分'目录无此站'与'有组分站但无该类监测能力'。"""

        metadata = {
            "tool_name": self.name,
            "station_count": 0,
            "directory_total": len(all_records),
            "available_cities": available_cities,
            "component_types": list(wanted_domains),
            **{
                f"{domain}_station_count": count
                for domain, count in domain_stats.items()
            },
        }
        if not records:
            return {
                "status": "empty",
                "success": True,
                "data": [],
                "metadata": metadata,
                "summary": (
                    "组分站目录中未匹配到站点；该城市/名称不在 38 个超站组分站清单内。"
                    f"有组分站的城市：{'、'.join(available_cities)}。"
                    "清单外站点没有组分数据，不要用常规监测站名代替。"
                ),
            }

        labels = "、".join(_capability_labels(wanted_domains))
        matched_names = "、".join(
            f"{record.station_name}({record.station_code})"
            for record in records[:10]
        )
        capable = [
            f"{record.station_name}({record.station_code})"
            for record in all_records
            if any(domain in record.data_domains for domain in wanted_domains)
        ]
        return {
            "status": "empty",
            "success": True,
            "data": [],
            "metadata": metadata,
            "summary": (
                f"匹配到 {len(records)} 个组分站（{matched_names}），"
                f"但它们都不具备{labels}监测能力；"
                f"全省具备{labels}能力的组分站：{'、'.join(capable) or '无'}。"
                "回答时如实区分'没有这类组分站'与'没有组分站'，不要笼统说没有组分站。"
            ),
        }

    @staticmethod
    def _normalize_limit(limit: int | None) -> int:
        if limit is None:
            return DEFAULT_LIMIT
        try:
            value = int(limit)
        except (TypeError, ValueError):
            return DEFAULT_LIMIT
        return max(1, min(value, MAX_LIMIT))

    def _failed(self, message: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "error": message,
            "data": None,
            "metadata": {"tool_name": self.name},
            "summary": f"组分站目录解析失败: {message}",
        }
