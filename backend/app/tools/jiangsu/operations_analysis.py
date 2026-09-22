"""Read-only Jiangsu operations data tools for personnel activity analysis."""

from __future__ import annotations

import asyncio
from datetime import datetime
import time
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.result_filter import externalize_compact_records
from app.tools.jiangsu.station_type import filter_station_rows, station_type_from_row

logger = structlog.get_logger(__name__)

# The interactive operations tools are intentionally scoped to provincial-
# control stations managed by the operations platform.  National- and
# municipal-control stations are excluded from both the relationship graph and
# the station directory so downstream answers cannot mix jurisdictions.
PROVINCIAL_STATION_TYPE = "省控"


def _operation_unit_id(row: dict[str, Any]) -> str:
    return str(row.get("operationUnitId") or row.get("OperationUnitId") or "").strip()


class _JiangsuOperationsTool(LLMTool):
    """Shared authenticated read-only client for the Jiangsu operations API."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        function_schema: dict[str, Any],
        requires_context: bool = False,
    ) -> None:
        from config.settings import settings

        self.base_url = settings.jiangsu_ops_api_base_url.rstrip("/")
        self.token_url = settings.jiangsu_ops_token_url.rstrip("/")
        self.username = settings.jiangsu_ops_api_username or settings.jiangsu_air_api_username
        self.password = settings.jiangsu_ops_api_password or settings.jiangsu_air_api_password
        self.timeout_seconds = settings.jiangsu_ops_api_timeout_seconds
        self._token: str | None = None
        self._token_lock = asyncio.Lock()
        super().__init__(
            name=name,
            description=description,
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema=function_schema,
            requires_context=requires_context,
        )

    def _validate_config(self) -> None:
        if not self.base_url or not self.token_url or not self.username or not self.password:
            raise ValueError("未配置江苏运维接口地址、Token 地址、账号或密码")

    async def _request(self, path: str, params: list[tuple[str, Any]]) -> dict[str, Any]:
        self._validate_config()
        response = await self._get(path, params, await self._get_token())
        if response.status_code == 401:
            self._token = None
            response = await self._get(path, params, await self._get_token())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("江苏运维接口返回格式无效")
        if payload.get("success") is False:
            raise ValueError(str(payload.get("msg") or payload.get("message") or "江苏运维接口返回失败"))
        return payload

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with self._token_lock:
            if self._token:
                return self._token
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.token_url, params={"UserName": self.username, "Pwd": self.password})
            response.raise_for_status()
            payload = response.json()
            token = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or not payload.get("success") or not isinstance(token, str) or not token:
                raise ValueError(str(payload.get("msg") if isinstance(payload, dict) else "江苏运维接口 Token 获取失败"))
            self._token = token
            return token

    async def _get(self, path: str, params: list[tuple[str, Any]], token: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.get(
                f"{self.base_url}/{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "SysCode": "SunOps", "Accept": "application/json"},
            )

    @staticmethod
    def _page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        result = payload.get("result", payload)
        if isinstance(result, list):
            return result, len(result)
        if not isinstance(result, dict):
            raise ValueError("江苏运维接口返回 result 无效")
        records = result.get("items", result.get("data", result.get("records", [])))
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError("江苏运维接口返回记录列表无效")
        return records, int(result.get("totalCount", result.get("total", len(records))))


class JiangsuOperationsKnowledgeGraphTool(_JiangsuOperationsTool):
    """Query a live, minimal personnel-unit-station relationship graph.

    Personnel and station ownership are operational master data and can change
    independently of a document knowledge base.  Build the graph from the live
    platform directories, cache it briefly, and expose only identifiers, names
    and responsibility relationships needed by the Agent.
    """

    _GROUP_TREE_PATH = "operation/AirOperaBase/GetUserGroupTreeAsync"
    _STATION_PATH = "operation/AirOperaBase/GetOpaEnabledStationAsync"
    _CACHE_TTL_SECONDS = 300
    # Keep the graph response small enough for the model context.  The full
    # selected graph is saved through ExecutionContext when these limits are
    # exceeded; the inline response remains a useful seed/type-balanced
    # preview and carries the path to the complete artifact.
    _INLINE_ENTITY_LIMIT = 48
    _INLINE_RELATION_LIMIT = 96

    def __init__(self) -> None:
        self._graph_cache: dict[str, Any] | None = None
        self._graph_cached_at = 0.0
        self._graph_lock = asyncio.Lock()
        super().__init__(
            name="jiangsu_query_operations_graph",
            description="查询江苏运维人员、运维单位、省控责任站点、城市和区县的实时业务关系图，用于解析接口所需的人员/单位/站点标识。",
            requires_context=True,
            function_schema={
                "name": "jiangsu_query_operations_graph",
                "description": (
                    "从江苏运维平台实时目录检索人员—运维单位—责任站点—区县—城市关系。"
                    "当后续接口需要人员姓名、运维单位编码或站点编码而用户只给出自然名称时，先调用本工具；"
                    "查询“运维单位”可返回目录中的全部运维单位（建议将 depth 设为 1）；"
                    "站点、区县、城市、运维单位和运维人员之间支持双向关系展开；"
                    "不得猜测或编造人员、单位和站点标识。返回的是实时业务目录关系，不依赖用户手动选择知识库。"
                    "本工具只保留省控站点：国控、市控站点一律不返回，站点类型固定为省控。"
                    "仅返回精简标识与关系（名称、编码、归属、站点类型），不含站点完整台账字段（如经纬度）。"
                    "如果结果超过上下文容量，完整实体/关系会外置保存并返回 file_path；需要完整清单时应让 execute_python 使用 load_data(file_path) 读取，"
                    "不要把内联 preview 当作全量结果。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "queries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 20,
                            "description": "人员、运维单位、站点、区县、城市名称或平台编码。",
                        },
                        "depth": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 2,
                            "default": 2,
                            "description": "关系展开深度；0仅返回命中实体，1返回直接关系，2返回两跳关系。",
                        },
                        "max_entities": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 300,
                            "default": 120,
                            "description": "最多返回实体数，避免把全量人员目录写入上下文。",
                        },
                    },
                    "required": ["queries"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        queries: list[str] | None = None,
        depth: int = 2,
        max_entities: int = 120,
        **_: Any,
    ) -> dict[str, Any]:
        try:
            if (
                not queries
                or len(queries) > 20
                or not all(isinstance(item, str) and item.strip() for item in queries)
            ):
                raise ValueError("queries 需要 1 至 20 个人员、单位、站点或区域名称/编码")
            if not isinstance(depth, int) or not 0 <= depth <= 2:
                raise ValueError("depth 必须在 0 到 2 之间")
            if not isinstance(max_entities, int) or not 1 <= max_entities <= 300:
                raise ValueError("max_entities 必须在 1 到 300 之间")
            effective_station_type = PROVINCIAL_STATION_TYPE

            graph = await self._load_graph()
            graph, type_filter_applied = self._filter_graph_station_type(
                graph, effective_station_type, require_operation_unit=True
            )
            entities: dict[str, dict[str, Any]] = graph["entities"]
            relations: list[dict[str, str]] = graph["relations"]
            seed_ids = self._match_entities(entities, queries)
            if not seed_ids:
                return {
                    "status": "empty",
                    "success": True,
                    "data": {"entities": [], "relations": [], "matched_queries": []},
                    "metadata": {
                        "source": "jiangsu_operations_live_directory_graph",
                        "queries": queries,
                        "station_type": effective_station_type,
                        "station_type_filter_applied": type_filter_applied,
                        "graph_counts": graph["counts"],
                    },
                    "summary": "江苏运维关系图未找到与查询名称或编码匹配的实体。",
                }

            selected_ids = self._expand(seed_ids, relations, depth, max_entities, entities)
            selected_entities = [entities[entity_id] for entity_id in selected_ids]
            selected_relations = [
                relation for relation in relations
                if relation["source_id"] in selected_ids and relation["target_id"] in selected_ids
            ]
            matched_queries = [
                {
                    "query": query,
                    "entity_ids": self._match_entities(entities, [query]),
                }
                for query in queries
            ]
            complete_data = {
                "entities": selected_entities,
                "relations": selected_relations,
                "matched_queries": matched_queries,
            }
            selected_type_counts: dict[str, int] = {}
            for entity in selected_entities:
                entity_type = str(entity.get("entity_type") or "unknown")
                selected_type_counts[entity_type] = selected_type_counts.get(entity_type, 0) + 1
            inline_entities = selected_entities
            inline_relations = selected_relations
            file_path: str | None = None
            externalized = (
                len(selected_entities) > self._INLINE_ENTITY_LIMIT
                or len(selected_relations) > self._INLINE_RELATION_LIMIT
            )
            if externalized and context is not None and hasattr(context, "save_data"):
                file_path = context.save_data(
                    data=complete_data,
                    schema="jiangsu_operations_graph",
                    metadata={
                        "source_tool": self.name,
                        "queries": queries,
                        "depth": depth,
                        "station_type": effective_station_type,
                        "entity_count": len(selected_entities),
                        "relation_count": len(selected_relations),
                        "root_type": "object",
                    },
                )
                inline_ids = self._preview_entity_ids(
                    selected_ids, entities, self._INLINE_ENTITY_LIMIT
                )
                inline_id_set = set(inline_ids)
                inline_entities = [entities[entity_id] for entity_id in inline_ids]
                inline_relations = [
                    relation
                    for relation in selected_relations
                    if relation["source_id"] in inline_id_set
                    and relation["target_id"] in inline_id_set
                ][: self._INLINE_RELATION_LIMIT]
            return {
                "status": "success",
                "success": True,
                "data": {
                    "entities": inline_entities,
                    "relations": inline_relations,
                    "matched_queries": matched_queries,
                },
                "metadata": {
                    "source": "jiangsu_operations_live_directory_graph",
                    "endpoints": [self._GROUP_TREE_PATH, self._STATION_PATH],
                    "queries": queries,
                    "depth": depth,
                    "record_count": len(selected_entities),
                    "relation_count": len(selected_relations),
                    "returned_entity_count": len(inline_entities),
                    "returned_relation_count": len(inline_relations),
                    "entity_type_counts": selected_type_counts,
                    "data_complete": not externalized or file_path is None,
                    "externalized": bool(file_path),
                    **(
                        {"externalization_skipped": "execution context unavailable"}
                        if externalized and file_path is None
                        else {}
                    ),
                    "graph_counts": graph["counts"],
                    "cache_ttl_seconds": self._CACHE_TTL_SECONDS,
                    "station_type": effective_station_type,
                    "station_type_filter_applied": type_filter_applied,
                    "queried_at": datetime.now().astimezone().isoformat(),
                },
                "summary": (
                    f"江苏运维关系图查询完成：命中 {len(seed_ids)} 个实体，"
                    f"展开得到 {len(selected_entities)} 个实体和 {len(selected_relations)} 条关系；"
                    + (f"内联展示 {len(inline_entities)} 个实体，完整结果已保存到 file_path。" if file_path else "结果已完整内联返回。")
                ),
                **({"file_path": file_path, "data_complete": False} if file_path else {"data_complete": True}),
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_operations_graph_failed", error=str(exc))
            return {
                "status": "failed",
                "success": False,
                "data": {"entities": [], "relations": []},
                "summary": f"江苏运维关系图查询失败：{exc}",
            }

    @staticmethod
    def _preview_entity_ids(
        selected_ids: list[str],
        entities: dict[str, dict[str, Any]],
        limit: int,
    ) -> list[str]:
        """Choose a deterministic preview retaining seeds and entity types."""
        if len(selected_ids) <= limit:
            return selected_ids
        result: list[str] = []
        selected_types: set[str] = set()
        # Preserve the first occurrence of every type (seeds are first in the
        # selected list), then fill remaining slots in original order.
        for entity_id in selected_ids:
            entity_type = str(entities.get(entity_id, {}).get("entity_type"))
            if entity_type not in selected_types:
                result.append(entity_id)
                selected_types.add(entity_type)
        for entity_id in selected_ids:
            if entity_id not in result:
                result.append(entity_id)
            if len(result) >= limit:
                break
        return result[:limit]

    async def _load_graph(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._graph_cache is not None and now - self._graph_cached_at < self._CACHE_TTL_SECONDS:
            return self._graph_cache
        async with self._graph_lock:
            now = time.monotonic()
            if self._graph_cache is not None and now - self._graph_cached_at < self._CACHE_TTL_SECONDS:
                return self._graph_cache
            # Deliberately serial: these are small directories and should not
            # add avoidable concurrent pressure to the operations platform.
            group_rows, _ = self._page(await self._request(self._GROUP_TREE_PATH, []))
            station_rows, _ = self._page(await self._request(self._STATION_PATH, []))
            self._graph_cache = self._build_graph(group_rows, station_rows)
            self._graph_cached_at = time.monotonic()
            return self._graph_cache

    @classmethod
    def _build_graph(
        cls,
        group_rows: list[dict[str, Any]],
        station_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        entities: dict[str, dict[str, Any]] = {}
        relation_keys: set[tuple[str, str, str]] = set()

        def add_entity(entity_id: str, entity_type: str, name: str, **properties: Any) -> None:
            entities.setdefault(
                entity_id,
                {
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "name": name,
                    "properties": {key: value for key, value in properties.items() if value not in (None, "")},
                },
            )

        def add_relation(source_id: str, relation_type: str, target_id: str) -> None:
            if source_id in entities and target_id in entities:
                relation_keys.add((source_id, relation_type, target_id))

        unit_rows = [row for row in group_rows if row.get("level") == 2 and row.get("id")]
        unit_ids = {str(row["id"]) for row in unit_rows}

        # The platform directory represents the label “运维单位” as a level-1
        # catalog node, while the actual companies are level-2 children.  Keep
        # that catalog node in the graph so a query such as “有哪些运维单位” can
        # resolve to the complete unit list instead of being reported empty.
        unit_group_ids = {
            str(row.get("pId"))
            for row in unit_rows
            if row.get("pId") not in (None, "")
        }
        group_rows_by_id = {
            str(row["id"]): row
            for row in group_rows
            if row.get("id") and str(row["id"]) in unit_group_ids
        }
        for group_id in sorted(unit_group_ids):
            group_row = group_rows_by_id.get(group_id, {})
            add_entity(
                f"operation_unit_group:{group_id}",
                "operation_unit_group",
                str(group_row.get("name") or "运维单位"),
                group_id=group_id,
            )
        for row in unit_rows:
            unit_id = str(row["id"])
            add_entity(
                f"operation_unit:{unit_id}",
                "operation_unit",
                str(row.get("name") or unit_id),
                operation_unit_id=unit_id,
            )
            group_id = str(row.get("pId") or "")
            if group_id:
                add_relation(
                    f"operation_unit_group:{group_id}",
                    "contains",
                    f"operation_unit:{unit_id}",
                )
        for row in group_rows:
            parent_id = str(row.get("pId") or "")
            if row.get("level") != 3 or not row.get("id") or parent_id not in unit_ids:
                continue
            person_id = str(row["id"])
            person_entity_id = f"person:{person_id}"
            unit_entity_id = f"operation_unit:{parent_id}"
            add_entity(
                person_entity_id,
                "person",
                str(row.get("name") or person_id),
                person_id=person_id,
            )
            add_relation(person_entity_id, "member_of", unit_entity_id)

        for row in station_rows:
            station_code = str(row.get("stationCode") or row.get("StationCode") or "").strip()
            if not station_code:
                continue
            station_entity_id = f"station:{station_code}"
            city_code = str(row.get("cityCode") or "").strip()
            city_name = str(row.get("cityName") or "").strip()
            district_code = str(row.get("districtCode") or row.get("areaCode") or "").strip()
            district_name = str(row.get("districtName") or "").strip()
            unit_id = str(row.get("operationUnitId") or "").strip()
            station_type = station_type_from_row(row)
            add_entity(
                station_entity_id,
                "station",
                str(row.get("positionName") or row.get("stationName") or station_code),
                station_code=station_code,
                city_name=city_name,
                district_name=district_name,
                operation_unit_id=unit_id,
                station_type=station_type,
            )
            if city_name:
                city_entity_id = f"city:{city_code or city_name}"
                add_entity(city_entity_id, "city", city_name, city_code=city_code)
                add_relation(station_entity_id, "located_in", city_entity_id)
            if district_name:
                district_entity_id = f"district:{district_code or district_name}"
                add_entity(
                    district_entity_id,
                    "district",
                    district_name,
                    district_code=district_code,
                    district_name=district_name,
                    city_name=city_name,
                )
                add_relation(station_entity_id, "located_in", district_entity_id)
                if city_name:
                    add_relation(district_entity_id, "part_of", f"city:{city_code or city_name}")
            if unit_id:
                unit_entity_id = f"operation_unit:{unit_id}"
                if unit_entity_id not in entities:
                    add_entity(
                        unit_entity_id,
                        "operation_unit",
                        str(row.get("operationUnitName") or unit_id),
                        operation_unit_id=unit_id,
                    )
                add_relation(unit_entity_id, "responsible_for", station_entity_id)
                # Keep aggregate unit-to-area edges in addition to the
                # station ownership edge.  This makes all five operational
                # entity types reachable from one another within two hops:
                # person -> unit -> city/district and city/district -> unit
                # -> person, without expanding the full station directory.
                if city_name:
                    add_relation(unit_entity_id, "operates_in", city_entity_id)
                if district_name:
                    add_relation(unit_entity_id, "operates_in", district_entity_id)

        relation_priority = {
            "contains": 0,
            "member_of": 1,
            "responsible_for": 2,
            "operates_in": 3,
            "located_in": 4,
            "part_of": 5,
        }
        relations = [
            {"source_id": source, "relation_type": relation_type, "target_id": target}
            for source, relation_type, target in sorted(
                relation_keys,
                key=lambda item: (relation_priority.get(item[1], 99), item[0], item[2]),
            )
        ]
        counts: dict[str, int] = {}
        for entity in entities.values():
            entity_type = entity["entity_type"]
            counts[entity_type] = counts.get(entity_type, 0) + 1
        counts["relations"] = len(relations)
        return {"entities": entities, "relations": relations, "counts": counts}

    @classmethod
    def _filter_graph_station_type(
        cls,
        graph: dict[str, Any],
        requested_type: str,
        *,
        require_operation_unit: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Return a filtered graph while preserving non-station context nodes.

        ``require_operation_unit`` drops stations the operations platform does
        not manage.  A provincial superstation can carry the 省控 type while
        having no operation unit; it is not part of the managed network and
        must not inflate the station count.  The requirement is only applied
        when at least one station exposes an operation unit so directories that
        omit the field keep their previous behavior.
        """

        if requested_type == "全部":
            return graph, False
        entities = graph["entities"]
        station_rows = [
            (entity_id, entity)
            for entity_id, entity in entities.items()
            if entity.get("entity_type") == "station"
        ]
        typed = [(entity_id, entity) for entity_id, entity in station_rows if entity.get("properties", {}).get("station_type")]
        if not typed:
            return graph, False
        selected = [
            (entity_id, entity)
            for entity_id, entity in typed
            if entity.get("properties", {}).get("station_type") == requested_type
        ]
        if require_operation_unit:
            def has_unit(entity: dict[str, Any]) -> bool:
                return bool(str(entity.get("properties", {}).get("operation_unit_id") or "").strip())

            if any(has_unit(entity) for _, entity in selected):
                selected = [(entity_id, entity) for entity_id, entity in selected if has_unit(entity)]
        allowed = {entity_id for entity_id, _ in selected}
        filtered_entities = {
            entity_id: entity
            for entity_id, entity in entities.items()
            if entity.get("entity_type") != "station" or entity_id in allowed
        }
        filtered_relations = [
            relation
            for relation in graph["relations"]
            if relation["source_id"] in filtered_entities and relation["target_id"] in filtered_entities
        ]
        counts: dict[str, int] = {}
        for entity in filtered_entities.values():
            entity_type = str(entity.get("entity_type") or "unknown")
            counts[entity_type] = counts.get(entity_type, 0) + 1
        counts["relations"] = len(filtered_relations)
        return {"entities": filtered_entities, "relations": filtered_relations, "counts": counts}, True

    @classmethod
    def _match_entities(
        cls, entities: dict[str, dict[str, Any]], queries: list[str]
    ) -> list[str]:
        matched: list[str] = []
        for query in queries:
            query_normalized = cls._normalize(query)
            exact: list[str] = []
            partial: list[str] = []
            for entity_id, entity in entities.items():
                properties = entity.get("properties") or {}
                aliases = {
                    cls._normalize(entity_id.split(":", 1)[-1]),
                    cls._normalize(entity.get("name")),
                    cls._normalize(properties.get("station_code")),
                }
                if entity.get("entity_type") == "district":
                    aliases.add(
                        cls._normalize(
                            str(properties.get("city_name") or "")
                            + str(properties.get("district_name") or entity.get("name") or "")
                        )
                    )
                aliases.discard("")
                if query_normalized in aliases:
                    exact.append(entity_id)
                elif any(query_normalized in alias or alias in query_normalized for alias in aliases):
                    partial.append(entity_id)
            # A category question such as “有哪些运维单位” names an entity
            # type, not an entity.  The level-1 catalog node normally makes
            # this resolvable by name, but some platform directories leave the
            # unit rows parentless; fall back to seeding every entity of the
            # labelled type so the listing still works.
            hits = exact or partial or cls._match_type_label(entities, query_normalized)
            for entity_id in hits:
                if entity_id not in matched:
                    matched.append(entity_id)
        return matched

    _TYPE_LABELS: dict[str, str] = {
        "运维单位": "operation_unit",
        "运维公司": "operation_unit",
        "运维人员": "person",
        "人员": "person",
        "监测站点": "station",
        "站点": "station",
        "城市": "city",
        "区县": "district",
    }

    @classmethod
    def _match_type_label(
        cls, entities: dict[str, dict[str, Any]], query_normalized: str
    ) -> list[str]:
        if not query_normalized:
            return []
        for label in sorted(cls._TYPE_LABELS, key=len, reverse=True):
            if label in query_normalized:
                entity_type = cls._TYPE_LABELS[label]
                return [
                    entity_id
                    for entity_id, entity in entities.items()
                    if entity.get("entity_type") == entity_type
                ]
        return []

    @staticmethod
    def _expand(
        seed_ids: list[str],
        relations: list[dict[str, str]],
        depth: int,
        max_entities: int,
        entities: dict[str, dict[str, Any]],
    ) -> list[str]:
        selected = list(dict.fromkeys(seed_ids))[:max_entities]
        selected_set = set(selected)
        seed_types = {
            str(entities[entity_id].get("entity_type"))
            for entity_id in selected
            if entity_id in entities
        }
        frontier = list(selected)
        for current_depth in range(depth):
            candidates: list[str] = []
            for relation in relations:
                source_id, target_id = relation["source_id"], relation["target_id"]
                candidate = None
                if source_id in frontier and target_id not in selected_set:
                    candidate = target_id
                elif target_id in frontier and source_id not in selected_set:
                    candidate = source_id
                if candidate is not None:
                    # Do not expand through a shared parent into a large list
                    # of same-type siblings (person -> unit -> all coworkers,
                    # station -> unit -> all sibling stations). The requested
                    # entity remains present and cross-type responsibility
                    # paths stay available.
                    if str(entities.get(candidate, {}).get("entity_type")) in seed_types:
                        continue
                    if candidate not in candidates:
                        candidates.append(candidate)
            if not candidates:
                break

            # A city or district can own hundreds of stations.  If all first
            # hop candidates are consumed in relation order, the entity cap
            # prevents the next hop (often people via their unit) from ever
            # being visited.  Before consuming the remaining slots, distribute
            # candidates across entity types so every cross-type path gets a
            # chance to remain in the frontier.  The final hop keeps the old
            # behavior and returns all direct candidates up to max_entities.
            if current_depth < depth - 1:
                candidates_by_type: dict[str, list[str]] = {}
                type_order: list[str] = []
                for candidate in candidates:
                    candidate_type = str(entities.get(candidate, {}).get("entity_type"))
                    if candidate_type not in candidates_by_type:
                        candidates_by_type[candidate_type] = []
                        type_order.append(candidate_type)
                    candidates_by_type[candidate_type].append(candidate)
                selected_types = {
                    str(entities[entity_id].get("entity_type"))
                    for entity_id in selected
                    if entity_id in entities
                }
                type_order_index = {item: index for index, item in enumerate(type_order)}
                type_order.sort(
                    key=lambda item: (item in selected_types, type_order_index[item])
                )
                remaining_slots = max_entities - len(selected)
                per_type = max(
                    1,
                    (remaining_slots + len(type_order) - 1) // len(type_order),
                )
                candidates = [
                    candidate
                    for candidate_type in type_order
                    for candidate in candidates_by_type[candidate_type][:per_type]
                ]

            next_frontier = candidates[:max_entities - len(selected)]
            selected.extend(next_frontier)
            selected_set.update(next_frontier)
            if len(selected) >= max_entities:
                return selected
            frontier = next_frontier
            if not frontier:
                break
        return selected

    @staticmethod
    def _normalize(value: Any) -> str:
        return "".join(str(value or "").strip().lower().split())


class JiangsuAttendanceRecordsTool(_JiangsuOperationsTool):
    """Fetch personnel station sign-in records, not continuous location tracking."""

    _PATH = "operation/AirCityAPPAttendance/GetAttendanceManagement"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_attendance_records",
            description="查询江苏运维人员到站签到记录（含站点、时间、定位、距站距离）；仅用于分析，不代表连续轨迹或签退记录。",
            function_schema={
                "name": "jiangsu_fetch_attendance_records",
                "description": "按人员、单位、站点和时间范围读取运维人员到站签到记录。仅只读查询。",
                "parameters": {"type": "object", "properties": {
                    "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "user_name": {"type": "string", "description": "可选人员姓名。"},
                    "unit_id": {"type": "string", "description": "可选运维单位编码。"},
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "skip_count": {"type": "integer", "minimum": 0, "default": 0},
                    "max_result_count": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
                }, "required": ["start_time", "end_time"]},
            },
        )

    async def execute(self, context=None, start_time: str | None = None, end_time: str | None = None,
                      user_name: str | None = None, unit_id: str | None = None, station_code: str | None = None,
                      skip_count: int = 0, max_result_count: int = 200, **_: Any) -> dict[str, Any]:
        try:
            self._validate(start_time, end_time, skip_count, max_result_count)
            # The platform endpoint is paginated.  A single first page made
            # monthly reports silently incomplete once a month exceeded 500
            # sign-ins, so fetch bounded pages until totalCount is covered.
            page_size = min(max_result_count, 500)
            records: list[dict[str, Any]] = []
            reported_total: int | None = None
            page = skip_count
            page_count = 0
            max_pages = 200
            while page_count < max_pages:
                params: list[tuple[str, Any]] = [
                    ("warrantytime[0]", start_time or ""), ("warrantytime[1]", end_time or ""),
                    ("skipCount", page), ("maxResultCount", page_size),
                ]
                for key, value in (("UserName", user_name), ("UnitID", unit_id), ("StationCode", station_code)):
                    if value and value.strip():
                        params.append((key, value.strip()))
                batch, total_count = self._page(await self._request(self._PATH, params))
                reported_total = total_count if reported_total is None else max(reported_total, total_count)
                records.extend(batch)
                page_count += 1
                if not batch or len(records) >= reported_total:
                    break
                page += len(batch)
            total_count = reported_total if reported_total is not None else len(records)
            return {
                "status": "success" if records else "empty", "success": True, "data": records,
                "metadata": {"source": "jiangsu_operations_attendance_api", "endpoint": self._PATH,
                             "time_range": [start_time, end_time], "filters": {"user_name": user_name, "unit_id": unit_id, "station_code": station_code},
                             "pagination": {"skip_count": skip_count, "page_size": page_size, "pages_fetched": page_count,
                                             "complete": len(records) >= total_count or (page_count == 1 and len(records) < page_size)},
                             "record_count": len(records), "total_count": total_count, "queried_at": datetime.now().astimezone().isoformat()},
                "summary": f"江苏运维人员到站签到记录查询完成：返回 {len(records)} 条，共 {total_count} 条。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_attendance_records_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维人员签到记录查询失败：{exc}"}

    @staticmethod
    def _validate(start_time: str | None, end_time: str | None, skip_count: int, max_result_count: int) -> None:
        try:
            start, end = (datetime.fromisoformat((value or "").replace("Z", "+00:00")) for value in (start_time, end_time))
        except ValueError as exc:
            raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
        if start > end or (end - start).days > 93:
            raise ValueError("时间范围必须有效且单次不超过 93 天")
        if not isinstance(skip_count, int) or skip_count < 0:
            raise ValueError("skip_count 必须是非负整数")
        if not isinstance(max_result_count, int) or not 1 <= max_result_count <= 500:
            raise ValueError("max_result_count 必须在 1 到 500 之间")


class JiangsuStationDirectoryTool(_JiangsuOperationsTool):
    """Fetch enabled station directory used to interpret sign-in locations."""

    _PATH = "operation/AirOperaBase/GetOpaEnabledStationAsync"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_station_directory",
            description="查询江苏运维省控站点台账明细：返回省控站点完整原始字段（城市、区县、运维单位、经纬度、站点类型等），适合解读签到定位、核对站点属性。",
            function_schema={
                "name": "jiangsu_fetch_station_directory",
                "description": (
                    "只读获取江苏运维省控站点台账明细，返回站点完整字段（城市、区县、运维单位、经纬度、站点类型等空间位置）。"
                    "仅保留省控站点，国控、市控站点一律不返回。"
                    "适用场景：解读签到定位、核对站点属性、按站点编码筛选台账。不得用台账修改站点。"
                ),
                "parameters": {"type": "object", "properties": {
                    "station_codes": {"type": "array", "items": {"type": "string"}, "maxItems": 100, "description": "可选站点编码筛选（精确匹配）。"},
                }},
            },
        )

    async def execute(self, context=None, station_codes: list[str] | None = None, **_: Any) -> dict[str, Any]:
        try:
            if station_codes is not None and (len(station_codes) > 100 or not all(isinstance(item, str) and item.strip() for item in station_codes)):
                raise ValueError("station_codes 最多 100 个，且必须均为有效站点编码")
            records, total_count = self._page(await self._request(self._PATH, []))
            records = [item for item in records if isinstance(item, dict)]
            records, type_filter_applied = filter_station_rows(records, PROVINCIAL_STATION_TYPE)
            # A provincial superstation can carry the 省控 type without an
            # operation unit; it is not part of the managed network.  Only
            # enforce the requirement when the directory exposes the field.
            operation_unit_filter_applied = False
            if type_filter_applied and any(_operation_unit_id(item) for item in records):
                records = [item for item in records if _operation_unit_id(item)]
                operation_unit_filter_applied = True
            requested = {item.strip() for item in station_codes or []}
            if requested:
                records = [item for item in records if str(item.get("stationCode") or item.get("StationCode") or "").strip() in requested]
            return {
                "status": "success" if records else "empty", "success": True, "data": records,
                "metadata": {"source": "jiangsu_operations_station_directory_api", "endpoint": self._PATH,
                             "station_codes": sorted(requested), "record_count": len(records), "total_count": total_count,
                             "station_type": PROVINCIAL_STATION_TYPE, "station_type_filter_applied": type_filter_applied,
                             "operation_unit_filter_applied": operation_unit_filter_applied,
                             "queried_at": datetime.now().astimezone().isoformat()},
                "summary": f"江苏运维省控站点台账查询完成：返回 {len(records)} 条记录。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_station_directory_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维站点台账查询失败：{exc}"}

class JiangsuWorkOrderTrackAnalysisTool(_JiangsuOperationsTool):
    """Deterministic monthly trajectory analysis; report-only, no writes."""
    def __init__(self):
        super().__init__(name="jiangsu_analyze_work_order_tracks", description="分析签到轨迹疑似串单和多站点签到", function_schema={"name":"jiangsu_analyze_work_order_tracks","description":"按时间范围分析运维签到轨迹","parameters":{"type":"object","properties":{"start_time":{"type":"string"},"end_time":{"type":"string"},"speed_limit":{"type":"number","default":250},"overlap_minutes":{"type":"number","default":10},"distance_limit":{"type":"number","default":1},"gps_limit":{"type":"number","default":0.5}},"required":["start_time","end_time"]}})
    async def execute(self, context=None, start_time=None, end_time=None, speed_limit=250, overlap_minutes=10, distance_limit=1, gps_limit=0.5, **kwargs):
        records = await JiangsuAttendanceRecordsTool().execute(context=context, start_time=start_time, end_time=end_time, max_result_count=500)
        if not records.get("success", False):
            return {
                "success": False,
                "status": "failed",
                "findings": [],
                "remote_signins": [],
                "users": [],
                "finding_count": 0,
                "metadata": {"start_time": start_time, "end_time": end_time, "source_status": records.get("status")},
                "summary": f"轨迹分析失败：{records.get('summary') or '签到数据源不可用'}",
            }
        rows = records.get("data", [])
        findings, remote, users = [], [], {}
        def get(r, *ks):
            return next((r.get(k) for k in ks if r.get(k) is not None), None)
        from datetime import datetime
        from math import asin, cos, radians, sin, sqrt
        def dist(a,b):
            la,lo,lb,lp=map(radians,(*a,*b)); h=sin((lb-la)/2)**2+cos(la)*cos(lb)*sin((lp-lo)/2)**2; return 6371*2*asin(sqrt(h))
        for r in rows: users.setdefault(str(get(r,'user_name','UserName','userName','name') or '未知人员'),[]).append(r)
        for user, rs in users.items():
            rs.sort(key=lambda r:str(get(r,'sign_time','SignTime','signInTime','attendance_time','time') or ''))
            for a,b in zip(rs,rs[1:]):
                try:
                    ta=datetime.fromisoformat(str(get(a,'sign_time','SignTime','signInTime','attendance_time','time')).replace('Z','+00:00')); tb=datetime.fromisoformat(str(get(b,'sign_time','SignTime','signInTime','attendance_time','time')).replace('Z','+00:00')); hours=(tb-ta).total_seconds()/3600
                    pa=(float(get(a,'station_lat','lat','StationLat','latitude')),float(get(a,'station_lon','lon','StationLon','longitude'))); pb=(float(get(b,'station_lat','lat','StationLat','latitude')),float(get(b,'station_lon','lon','StationLon','longitude'))); km=dist(pa,pb); speed=km/hours if hours>0 else float('inf')
                except (TypeError,ValueError,ZeroDivisionError): continue
                different=str(get(a,'station_code','StationCode','stationCode'))!=str(get(b,'station_code','StationCode','stationCode'))
                if speed>speed_limit: findings.append({'user_name':user,'type':'cross_region_speed','speed_kmh':round(speed,1),'distance_km':round(km,2),'previous':a,'current':b})
                if different and hours*60<overlap_minutes and km>distance_limit: findings.append({'user_name':user,'type':'multi_station_overlap','minutes':round(hours*60,2),'distance_km':round(km,2),'previous':a,'current':b})
            for r in rs:
                try:
                    if float(get(r,'distance_to_station','Distance','distance') or 0)>gps_limit: remote.append({'user_name':user,'record':r})
                except (TypeError,ValueError): pass
        return {'success': True, 'status':'success' if rows else 'empty', 'findings':findings, 'remote_signins':remote, 'users':sorted(users), 'finding_count':len(findings), 'metadata': {'start_time':start_time,'end_time':end_time,'record_count':len(rows),'rules': {'speed_limit':speed_limit,'overlap_minutes':overlap_minutes,'distance_limit':distance_limit,'gps_limit':gps_limit}}, 'summary':f'轨迹分析完成：{len(rows)}条签到，发现{len(findings)}条疑似线索。'}


# ---------------------------------------------------------------------------
# Shared helpers for the door-access and device-ledger tools
# ---------------------------------------------------------------------------


def _clean_station_codes(
    station_codes: Any, maximum: int, *, required: bool = True
) -> list[str]:
    if station_codes is None:
        if required:
            raise ValueError("station_codes 不能为空")
        return []
    if isinstance(station_codes, str):
        station_codes = [station_codes]
    if not isinstance(station_codes, list) or not all(
        isinstance(item, str) and item.strip() for item in station_codes
    ):
        raise ValueError("station_codes 必须为站点编码列表")
    codes = list(dict.fromkeys(item.strip() for item in station_codes))
    if not codes:
        raise ValueError("station_codes 不能为空")
    if len(codes) > maximum:
        raise ValueError(f"station_codes 最多 {maximum} 个")
    return codes


def _parse_time_range(
    start_time: str | None, end_time: str | None, maximum_days: int
) -> tuple[datetime, datetime]:
    try:
        start, end = (
            datetime.fromisoformat((value or "").replace("Z", "+00:00"))
            for value in (start_time, end_time)
        )
    except ValueError as exc:
        raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
    if start > end or (end - start).days > maximum_days:
        raise ValueError(f"时间范围必须有效且单次不超过 {maximum_days} 天")
    return start, end


def _take_field(record: dict[str, Any], keys: tuple[str, ...], used: set[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip() != "":
            used.add(key)
            return value
    return None


def _extra_fields(record: dict[str, Any], used: set[str]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in used and value not in (None, "")
    }


class JiangsuDoorAccessRecordsTool(LLMTool):
    """Read-only station door access-control records (independent entry evidence).

    A door/opening event is independent corroboration that a person physically
    entered a station, complementing discrete sign-in records.  It is still a
    discrete card/opening event, not a continuous location track, and a shared
    card cannot prove who actually entered.
    """

    _PATH = "stationintegrate/HK/GetACSDoorRecordsAsync"
    _MAX_STATIONS = 10
    _MAX_RANGE_DAYS = 31
    _MAX_RESULT_COUNT = 1000
    _CONCURRENCY = 6

    _STATION_CODE_KEYS = ("stationCode", "StationCode", "code", "Code")
    _STATION_NAME_KEYS = ("stationName", "StationName", "positionName", "PositionName")
    _PERSON_KEYS = ("personName", "PersonName", "employeeName", "staffName", "name", "Name")
    _TIME_KEYS = (
        "eventTime", "EventTime", "swipeTime", "SwipeTime", "openTime", "OpenTime",
        "createTime", "CreateTime", "timePoint", "TimePoint", "occurredAt",
    )
    _TYPE_KEYS = ("eventType", "EventType", "eventName", "accessType", "openType", "doorEventType")
    _DOOR_KEYS = ("doorName", "DoorName", "deviceName", "channelName", "readerName", "pointName")
    _CARD_KEYS = ("cardNo", "CardNo", "cardNumber", "icCard", "idCard", "credentialNo")

    def __init__(self) -> None:
        from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi

        self._api = _JiangsuAuthenticatedApi(source="air")
        super().__init__(
            name="jiangsu_fetch_door_access_records",
            description=(
                "只读查询江苏运维省控站点门禁开关门/刷卡记录，用于核验人员是否实际进站；"
                "门禁记录是离散事件，不代表连续轨迹，刷卡信息不能证明实际进站人员身份。"
            ),
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_fetch_door_access_records",
                "description": (
                    "按站点和时间范围只读读取江苏省控站点门禁开关门/刷卡记录，用作签到到站之外的独立进站证据。"
                    "返回记录会归一为人员、站点、事件时间、事件类型、门名称和卡号等字段，并保留平台原始字段。"
                    "本工具只读查询；门禁记录为离散事件，不是连续位置轨迹，也不等同于责任认定；"
                    "签到与门禁不一致只能作为待核查线索。"
                ),
                "parameters": {"type": "object", "properties": {
                    "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                      "description": "省控站点编码（1-10 个）。"},
                    "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "max_result_count": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 1000,
                                         "description": "单站最多返回记录数，1-1000。需要完整月度清单时可先调高再结合 file_path 读取。"},
                }, "required": ["station_codes", "start_time", "end_time"]},
            },
        )

    async def execute(
        self,
        context=None,
        station_codes: list[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        max_result_count: int = 1000,
        **_: Any,
    ) -> dict[str, Any]:
        try:
            codes = _clean_station_codes(station_codes, self._MAX_STATIONS)
            _parse_time_range(start_time, end_time, self._MAX_RANGE_DAYS)
            if not isinstance(max_result_count, int) or not 1 <= max_result_count <= self._MAX_RESULT_COUNT:
                raise ValueError(f"max_result_count 必须在 1 到 {self._MAX_RESULT_COUNT} 之间")
            semaphore = asyncio.Semaphore(self._CONCURRENCY)

            async def guarded(station_code: str) -> Any:
                async with semaphore:
                    return await self._fetch_station(station_code, start_time or "", end_time or "", max_result_count)

            outcomes = await asyncio.gather(*(guarded(code) for code in codes), return_exceptions=True)
            records: list[dict[str, Any]] = []
            station_status: dict[str, dict[str, Any]] = {}
            for code, outcome in zip(codes, outcomes, strict=True):
                if isinstance(outcome, BaseException):
                    station_status[code] = {"record_count": 0, "status": "failed", "error": str(outcome)}
                    continue
                rows = self._rows(outcome)
                normalized = [self._normalize(row, code) for row in rows if isinstance(row, dict)]
                records.extend(normalized)
                state = {
                    "record_count": len(normalized),
                    "status": "success" if normalized else "empty",
                }
                total = self._total(outcome)
                if total is not None and total > len(normalized):
                    state["total_count"] = total
                    state["truncated"] = True
                station_status[code] = state
            failed_stations = [code for code, state in station_status.items() if state["status"] == "failed"]
            truncated_stations = [code for code, state in station_status.items() if state.get("truncated")]
            if failed_stations and len(failed_stations) == len(codes):
                status = "failed"
            elif records:
                status = "success"
            else:
                status = "empty"
            preview, file_path, externalization = externalize_compact_records(
                records,
                context=context,
                schema="jiangsu_door_access_records",
                metadata={
                    "source_tool": self.name,
                    "station_codes": codes,
                    "time_range": [start_time, end_time],
                },
            )
            metadata = {
                "source": "jiangsu_air_stationintegrate_door_api",
                "endpoint": self._PATH,
                "time_range": [start_time, end_time],
                "station_codes": codes,
                "station_status": station_status,
                "record_count": len(records),
                "failed_station_count": len(failed_stations),
                "truncated_stations": truncated_stations,
                "boundary": "门禁记录是离散开关门/刷卡事件，不是连续轨迹；卡可能共用，不能据此认定实际进站人员或违规事实。",
                "queried_at": datetime.now().astimezone().isoformat(),
                **externalization,
            }
            return {
                "status": status,
                "success": status != "failed",
                "data": preview,
                "metadata": metadata,
                "summary": (
                    f"江苏站点门禁记录查询完成：{len(codes)} 个站点共返回 {len(records)} 条记录；"
                    + (f"{len(failed_stations)} 个站点取数失败。" if failed_stations else "无失败站点。")
                ),
                **({"file_path": file_path, "data_complete": False} if file_path else {"data_complete": True}),
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_door_access_records_failed", error=str(exc))
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "summary": f"江苏站点门禁记录查询失败：{exc}",
            }

    async def _fetch_station(
        self, station_code: str, start_time: str, end_time: str, max_result_count: int
    ) -> dict[str, Any]:
        return await self._api.get(self._PATH, [
            ("StationCode", station_code),
            ("EventTime", start_time),
            ("EventTime", end_time),
            ("MaxResultCount", str(max_result_count)),
        ])

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        result = payload.get("result", payload) if isinstance(payload, dict) else payload
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
        if isinstance(result, dict):
            for key in ("list", "items", "data", "records", "rows"):
                value = result.get(key)
                if isinstance(value, list):
                    return [row for row in value if isinstance(row, dict)]
        return []

    @staticmethod
    def _total(payload: Any) -> int | None:
        result = payload.get("result", payload) if isinstance(payload, dict) else payload
        if isinstance(result, dict):
            for key in ("total", "totalCount", "Total", "TotalCount"):
                try:
                    return int(result.get(key))
                except (TypeError, ValueError):
                    continue
        return None

    @classmethod
    def _normalize(cls, row: dict[str, Any], fallback_station: str) -> dict[str, Any]:
        used: set[str] = set()
        record = {
            "station_code": _take_field(row, cls._STATION_CODE_KEYS, used) or fallback_station,
            "station_name": _take_field(row, cls._STATION_NAME_KEYS, used),
            "person_name": _take_field(row, cls._PERSON_KEYS, used),
            "event_time": _take_field(row, cls._TIME_KEYS, used),
            "event_type": _take_field(row, cls._TYPE_KEYS, used),
            "door_name": _take_field(row, cls._DOOR_KEYS, used),
            "card_no": _take_field(row, cls._CARD_KEYS, used),
        }
        extra = _extra_fields(row, used)
        if extra:
            record["extra"] = extra
        return {key: value for key, value in record.items() if value not in (None, "")}


class JiangsuDeviceLedgerTool(_JiangsuOperationsTool):
    """Read the operations-platform station device ledger for backup analysis."""

    _PATH = "asset/DeviceManagement/GetBSDDeviceListAsync"
    _MAX_STATIONS = 20
    _CONCURRENCY = 6

    _DEVICE_ID_KEYS = ("id", "deviceId", "DeviceId", "Id")
    _DEVICE_CODE_KEYS = ("deviceCode", "DeviceCode")
    _DEVICE_TYPE_KEYS = ("deviceType", "DeviceType")
    _DEVICE_TYPE_NAME_KEYS = ("deviceTypeName", "DeviceTypeName")
    _DEVICE_BRAND_KEYS = ("deviceBrand", "DeviceBrand")
    _DEVICE_MODEL_KEYS = ("deviceModel", "DeviceModel")
    _DEVICE_STATUS_KEYS = ("deviceStatus", "DeviceStatus", "status", "Status", "isEnable", "IsEnable")
    _DEVICE_START_KEYS = (
        "startTime", "StartTime", "installTime", "InstallTime", "onlineTime", "OnlineTime",
        "enableTime", "EnableTime", "productionDate",
    )
    _DEVICE_END_KEYS = (
        "endTime", "EndTime", "offTime", "OffTime", "disableTime", "DisableTime", "scrapTime",
    )
    _DEVICE_ROLE_KEYS = ("deviceRole", "DeviceRole", "isBackup", "IsBackup", "backupFlag", "BackupFlag")

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_device_ledger",
            description=(
                "只读查询江苏运维省控站点的设备台账明细，返回平台登记的每台设备及其原始字段，"
                "用于核对设备构成、识别备用设备，并为备机更换及时性与超期分析提供设备清单。"
            ),
            function_schema={
                "name": "jiangsu_fetch_device_ledger",
                "description": (
                    "只读获取指定江苏运维省控站点的设备台账明细，返回平台登记的每台设备及其完整原始字段。"
                    "适用于核对站点设备构成、识别备用设备、为备机更换与超期分析提供设备清单。"
                    "本工具只读取台账，不新增、变更或报废设备；"
                    "备机备案、设备启用/停用时间、借出与生命周期起止等字段是否可用以平台实际返回为准，"
                    "缺失时必须作为数据盲区如实说明，不得编造。"
                ),
                "parameters": {"type": "object", "properties": {
                    "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 20,
                                      "description": "省控站点编码（1-20 个）。"},
                }, "required": ["station_codes"]},
            },
        )

    async def execute(
        self, context=None, station_codes: list[str] | None = None, **_: Any
    ) -> dict[str, Any]:
        try:
            codes = _clean_station_codes(station_codes, self._MAX_STATIONS)
            semaphore = asyncio.Semaphore(self._CONCURRENCY)

            async def guarded(station_code: str) -> Any:
                async with semaphore:
                    return await self._request(self._PATH, [("StationCode", station_code)])

            outcomes = await asyncio.gather(*(guarded(code) for code in codes), return_exceptions=True)
            records: list[dict[str, Any]] = []
            station_status: dict[str, dict[str, Any]] = {}
            for code, outcome in zip(codes, outcomes, strict=True):
                if isinstance(outcome, BaseException):
                    station_status[code] = {"record_count": 0, "status": "failed", "error": str(outcome)}
                    continue
                rows, _ = self._page(outcome)
                normalized = [self._normalize(row, code) for row in rows if isinstance(row, dict)]
                records.extend(normalized)
                station_status[code] = {
                    "record_count": len(normalized),
                    "status": "success" if normalized else "empty",
                }
            failed_stations = [code for code, state in station_status.items() if state["status"] == "failed"]
            if failed_stations and len(failed_stations) == len(codes):
                status = "failed"
            elif records:
                status = "success"
            else:
                status = "empty"
            preview, file_path, externalization = externalize_compact_records(
                records,
                context=context,
                schema="jiangsu_device_ledger",
                metadata={"source_tool": self.name, "station_codes": codes},
            )
            metadata = {
                "source": "jiangsu_operations_device_ledger_api",
                "endpoint": self._PATH,
                "station_codes": codes,
                "station_status": station_status,
                "record_count": len(records),
                "failed_station_count": len(failed_stations),
                "blind_spots": "备机备案、设备启用/停用时间、借出记录与生命周期起止等字段是否可用以平台实际返回为准；缺失时只能作为数据盲区说明。",
                "queried_at": datetime.now().astimezone().isoformat(),
                **externalization,
            }
            return {
                "status": status,
                "success": status != "failed",
                "data": preview,
                "metadata": metadata,
                "summary": (
                    f"江苏站点设备台账查询完成：{len(codes)} 个站点共返回 {len(records)} 条设备记录；"
                    + (f"{len(failed_stations)} 个站点取数失败。" if failed_stations else "无失败站点。")
                ),
                **({"file_path": file_path, "data_complete": False} if file_path else {"data_complete": True}),
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_device_ledger_failed", error=str(exc))
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "summary": f"江苏站点设备台账查询失败：{exc}",
            }

    @classmethod
    def _normalize(cls, row: dict[str, Any], fallback_station: str) -> dict[str, Any]:
        used: set[str] = set()
        station_code = (
            _take_field(row, ("stationCode", "StationCode", "code", "Code"), used)
            or fallback_station
        )
        record = {
            "station_code": station_code,
            "station_name": _take_field(row, ("stationName", "StationName", "positionName"), used),
            "device_id": _take_field(row, cls._DEVICE_ID_KEYS, used),
            "device_code": _take_field(row, cls._DEVICE_CODE_KEYS, used),
            "device_type": _take_field(row, cls._DEVICE_TYPE_KEYS, used),
            "device_type_name": _take_field(row, cls._DEVICE_TYPE_NAME_KEYS, used),
            "device_brand": _take_field(row, cls._DEVICE_BRAND_KEYS, used),
            "device_model": _take_field(row, cls._DEVICE_MODEL_KEYS, used),
            "device_status": _take_field(row, cls._DEVICE_STATUS_KEYS, used),
            "start_time": _take_field(row, cls._DEVICE_START_KEYS, used),
            "end_time": _take_field(row, cls._DEVICE_END_KEYS, used),
            "backup_role": _take_field(row, cls._DEVICE_ROLE_KEYS, used),
        }
        extra = _extra_fields(row, used)
        if extra:
            record["extra"] = extra
        return {key: value for key, value in record.items() if value not in (None, "")}
