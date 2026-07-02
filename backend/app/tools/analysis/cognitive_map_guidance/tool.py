"""Generic cognitive map guidance tool for Agent planning."""

from __future__ import annotations

from typing import Any

import structlog

from app.api.cognitive_map_routes import (
    CognitiveMapGraphQueryRequest,
    _build_graph_query_view,
    _enabled_binding_map_ids,
    _load_json,
    _meta_path,
)
from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


FAULT_RELATIONS = {
    "alarm_indicates",
    "indicates",
    "root_cause_causes",
    "causes",
    "fault_related_to_pollutant",
    "work_order_about",
}
DATA_RELATIONS = {
    "fault_affects_metric",
    "data_source_validates",
    "check_requires",
    "requires_data",
    "affects",
    "measures",
}
WORK_ORDER_RELATIONS = {"work_order_about", "maintenance_handles", "handled_by_agent"}


def _standard_success(tool_name: str, summary: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "success": True,
        "summary": summary,
        "data": data,
        "metadata": {
            "tool_name": tool_name,
            "generator": tool_name,
        },
    }


def _standard_failure(tool_name: str, summary: str, error: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "failed",
        "success": False,
        "summary": summary,
        "data": data or {"error": error},
        "metadata": {
            "tool_name": tool_name,
            "generator": tool_name,
            "error": error,
        },
    }


def _clean_list(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = values.split(",")
    cleaned = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _relation_label(relation: dict[str, Any]) -> str:
    return str(relation.get("relation_type") or relation.get("label") or "").strip().lower()


def _relation_names(relation: dict[str, Any]) -> tuple[str, str]:
    source = str(relation.get("source_name") or relation.get("source") or relation.get("source_entity_id") or "").strip()
    target = str(relation.get("target_name") or relation.get("target") or relation.get("target_entity_id") or "").strip()
    return source, target


def _append_unique(items: list[dict[str, Any]], item: dict[str, Any], key: str) -> None:
    value = item.get(key)
    if value and any(existing.get(key) == value for existing in items):
        return
    items.append(item)


def _suggest_tool(
    suggestions: list[dict[str, Any]],
    tool_name: str,
    reason: str,
    required_inputs: list[str] | None = None,
) -> None:
    _append_unique(
        suggestions,
        {
            "tool_name": tool_name,
            "reason": reason,
            "required_inputs": required_inputs or [],
        },
        "tool_name",
    )


def build_guidance_response(
    guidance: dict[str, Any],
    *,
    include_views: bool = False,
) -> dict[str, Any]:
    data = {
        "matched": guidance.get("matched", False),
        "task": guidance.get("task", ""),
        "agent_mode": guidance.get("agent_mode", "graph"),
        "analysis_directions": guidance.get("analysis_directions", []),
        "data_requirements": guidance.get("data_requirements", []),
        "suggested_tools": guidance.get("suggested_tools", []),
        "missing_hints": guidance.get("missing_hints", []),
        "map_ids": guidance.get("map_ids", []),
        "entity_hints": guidance.get("entity_hints", []),
        "sources": guidance.get("sources", {}),
        "graph_entity_count": len(guidance.get("graph_entities") or []),
        "graph_relation_count": len(guidance.get("graph_relations") or []),
    }
    if include_views:
        data["views"] = guidance.get("views", [])
        data["graph_entities"] = guidance.get("graph_entities", [])
        data["graph_relations"] = guidance.get("graph_relations", [])
    summary = (
        f"认知地图命中 {data['graph_entity_count']} 个实体、"
        f"{data['graph_relation_count']} 条关系，形成 "
        f"{len(data['analysis_directions'])} 个分析方向。"
    )
    return _standard_success("cognitive_map_guidance", summary, data)


def build_guidance_from_views(
    views: list[dict[str, Any]],
    task: str,
    agent_mode: str,
) -> dict[str, Any]:
    """Convert cognitive map query views into deterministic Agent guidance."""
    graph_entities: list[dict[str, Any]] = []
    graph_relations: list[dict[str, Any]] = []
    analysis_directions: list[dict[str, Any]] = []
    data_requirements: list[dict[str, Any]] = []
    suggested_tools: list[dict[str, Any]] = []

    for view in views:
        map_id = view.get("map_id")
        map_name = view.get("map_name") or map_id
        for entity in view.get("entities") or []:
            item = dict(entity)
            item.setdefault("map_id", map_id)
            item.setdefault("map_name", map_name)
            _append_unique(graph_entities, item, "entity_id")
        for relation in view.get("relations") or []:
            item = dict(relation)
            item.setdefault("map_id", map_id)
            item.setdefault("map_name", map_name)
            item["relation_type"] = _relation_label(item)
            _append_unique(graph_relations, item, "relation_id")

    for relation in graph_relations:
        label = _relation_label(relation)
        source, target = _relation_names(relation)
        if label in FAULT_RELATIONS:
            hypothesis = target or source
            if source and target:
                hypothesis = f"{source} -> {target}"
            analysis_directions.append({
                "direction": "root_cause_hypothesis",
                "hypothesis": hypothesis,
                "basis_relation": label,
                "source": source,
                "target": target,
            })
        if label in DATA_RELATIONS:
            data_requirements.append({
                "requirement": target or source,
                "reason": f"图谱关系 `{label}` 指向需要用数据核验。",
                "source": source,
                "target": target,
            })
        if label in WORK_ORDER_RELATIONS:
            _suggest_tool(
                suggested_tools,
                "ops_audit_fetch_dataset",
                "图谱路径涉及工单/处置关系，需要抽取目标工单、流程、RF表单和附件记录。",
                ["working_order_codes", "station_id", "create_time_start/create_time_end"],
            )

    text_blob = " ".join([
        task,
        " ".join(str(item.get("name") or "") for item in graph_entities),
        " ".join(f"{rel.get('source_name', '')} {rel.get('relation_type', '')} {rel.get('target_name', '')}" for rel in graph_relations),
    ])
    if agent_mode == "ops":
        _suggest_tool(
            suggested_tools,
            "ops_audit_fetch_dataset",
            "故障工单/告警原因分析需要先拿到工单上下文、处置记录和附件记录。",
            ["working_order_codes", "station_id", "order_type", "time_range"],
        )
        _suggest_tool(
            suggested_tools,
            "query_gd_suncere_station_hour_new",
            "需要用站点小时数据核验告警前后污染物或设备指标变化。",
            ["station_id/station_name", "start_time", "end_time", "pollutants"],
        )
        _suggest_tool(
            suggested_tools,
            "query_gd_suncere_station_day_new",
            "需要按日聚合对比故障前后趋势时使用。",
            ["station_id/station_name", "start_date", "end_date", "pollutants"],
        )
        if "表" in text_blob or "字段" in text_blob or "质控" in text_blob:
            _suggest_tool(
                suggested_tools,
                "execute_ops_sql_query",
                "需要补查白名单运维表、质控表或基础表单结构化记录。",
                ["describe_table 或 SELECT 白名单表"],
            )

    if agent_mode == "query":
        query_terms = ("站点", "PM2.5", "PM25", "细颗粒物", "地图", "上图", "定位", "最高", "异常")
        if any(term in text_blob for term in query_terms):
            _suggest_tool(
                suggested_tools,
                "query_station_standard_report",
                "站点污染物排名或最高值判断需要先查询真实站点统计数据。",
                ["cities/stations", "start_time", "end_time", "pollutant_codes"],
            )
            _suggest_tool(
                suggested_tools,
                "read_data_registry",
                "站点查询返回 report_data_id/data_id 后，需要读取结果再排序筛选目标站点。",
                ["data_id", "view"],
            )
            _suggest_tool(
                suggested_tools,
                "cognitive_map_entity_query",
                "按实体类型和属性发现真实站点目录、城市/区县归属和经纬度。",
                ["entity_type", "attribute_filters"],
            )
            _suggest_tool(
                suggested_tools,
                "cognitive_map_graph_traverse",
                "从城市或区县实体沿 located_in 反向遍历，发现其下辖站点实体。",
                ["start_entity", "relation_type", "direction", "depth", "target_entity_type"],
            )
            _suggest_tool(
                suggested_tools,
                "resolve_station_geo",
                "站点上图或定位前需要解析确定性站点经纬度、城市、区县和类型。",
                ["stations 或 station_codes"],
            )
            _suggest_tool(
                suggested_tools,
                "create_map_point_asset",
                "Agent 判定目标站点后，将带经纬度的点记录注册成真实 DataRegistry data_id。",
                ["name", "records", "longitude_field", "latitude_field", "layer_id"],
            )
            _suggest_tool(
                suggested_tools,
                "visual_interaction",
                "获得 create_map_point_asset 返回的 data_id 后，通过 map_program 生成点图层并定位地图，让用户真实看见结果。",
                ["point-layer 或 set-view command"],
            )
            data_requirements.append({
                "requirement": "站点 PM2.5 查询结果、最高站点名称/编码、站点经纬度",
                "reason": "问数地图闭环需要先以真实数据筛选站点，再解析地理属性并生成地图程序。",
                "source": "query-mode station workflow",
                "target": "map_program",
            })

    if not analysis_directions and graph_relations:
        for relation in graph_relations[:5]:
            source, target = _relation_names(relation)
            analysis_directions.append({
                "direction": "graph_relation_followup",
                "hypothesis": f"{source} -> {target}".strip(" ->"),
                "basis_relation": _relation_label(relation),
                "source": source,
                "target": target,
            })

    missing_hints = []
    if agent_mode == "ops":
        for label in ["站点", "告警/故障现象", "时间范围"]:
            if label not in text_blob:
                missing_hints.append(label)

    return {
        "matched": bool(graph_entities or graph_relations),
        "task": task,
        "agent_mode": agent_mode,
        "graph_entities": graph_entities,
        "graph_relations": graph_relations,
        "analysis_directions": analysis_directions,
        "data_requirements": data_requirements,
        "suggested_tools": suggested_tools,
        "missing_hints": missing_hints,
    }


class CognitiveMapGuidanceTool(LLMTool):
    """Query bound cognitive maps and return planning guidance."""

    def __init__(self) -> None:
        super().__init__(
            name="cognitive_map_guidance",
            description="Query bound cognitive maps for graph-guided analysis directions, evidence needs, and suggested tools.",
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "cognitive_map_guidance",
                "description": "通用认知地图指导工具。根据当前任务、Agent模式和实体线索查询绑定认知地图，返回图谱关系、分析方向、待核验数据和推荐工具。运维故障/告警原因分析应优先调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "用户任务或当前诊断问题。"},
                        "agent_mode": {
                            "type": "string",
                            "description": "当前Agent模式；图谱编辑传 graph，运维传 ops，问数传 query。未传时按 graph 处理。",
                        },
                        "agent_role": {"type": "string", "description": "可选Agent角色。"},
                        "map_ids": {"type": "array", "items": {"type": "string"}, "description": "可选认知地图ID；不传则使用当前模式绑定并启用的地图。"},
                        "entity_hints": {"type": "array", "items": {"type": "string"}, "description": "站点、设备、告警、污染物、故障现象、工单号等图谱检索线索。"},
                        "station": {"type": "string", "description": "站点名称或ID。"},
                        "alarm_type": {"type": "string", "description": "告警类型或告警名称。"},
                        "fault_symptom": {"type": "string", "description": "故障现象。"},
                        "pollutants": {"type": "array", "items": {"type": "string"}, "description": "污染物或监测指标。"},
                        "working_order_code": {"type": "string", "description": "工单编号。"},
                        "time_range": {"type": "string", "description": "分析时间范围。"},
                        "depth": {"type": "integer", "description": "图谱关系展开深度，默认2。"},
                        "limit": {"type": "integer", "description": "最多读取的图谱关系数量，默认30。"},
                        "include_views": {"type": "boolean", "description": "是否返回原始子图 views，默认 false，仅调试使用。"},
                    },
                    "required": ["task"],
                },
            },
            version="0.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        context=None,
        task: str = "",
        agent_mode: str = "graph",
        agent_role: str | None = None,
        map_ids: list[str] | None = None,
        entity_hints: list[str] | None = None,
        station: str | None = None,
        alarm_type: str | None = None,
        fault_symptom: str | None = None,
        pollutants: list[str] | str | None = None,
        working_order_code: str | None = None,
        time_range: str | None = None,
        depth: int = 2,
        limit: int = 30,
        include_views: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        task = str(task or "").strip()
        if not task:
            return _standard_failure(self.name, "认知地图查询失败：task 不能为空。", "task is required")

        selected_map_ids = _clean_list(map_ids) or _enabled_binding_map_ids(agent_mode)
        if not selected_map_ids:
            return _standard_failure(
                self.name,
                f"未找到绑定到 `{agent_mode}` 模式且已启用的认知地图。",
                "no enabled cognitive map bindings",
                {"agent_mode": agent_mode, "map_ids": []},
            )

        hints = _clean_list(entity_hints)
        hints.extend(_clean_list(station))
        hints.extend(_clean_list(alarm_type))
        hints.extend(_clean_list(fault_symptom))
        hints.extend(_clean_list(pollutants))
        hints.extend(_clean_list(working_order_code))
        hints.extend(_clean_list(time_range))
        hints = _clean_list(hints)

        views: list[dict[str, Any]] = []
        sources: dict[str, str] = {}
        for map_id in selected_map_ids[:5]:
            payload = CognitiveMapGraphQueryRequest(
                task=task,
                agent_mode=agent_mode,
                agent_role=agent_role,
                entity_hints=hints,
                depth=max(1, min(int(depth or 2), 4)),
                limit=max(1, min(int(limit or 30), 100)),
                max_entities=30,
                max_relations=50,
            )
            try:
                view, source = _build_graph_query_view(map_id, payload)
            except Exception as exc:
                logger.warning("cognitive_map_guidance_view_failed", map_id=map_id, error=str(exc))
                continue
            item = view.model_dump(mode="json")
            meta = _load_json(_meta_path(map_id), {})
            item["map_name"] = meta.get("name") or map_id
            item["source"] = source
            views.append(item)
            sources[map_id] = source

        guidance = build_guidance_from_views(views=views, task=task, agent_mode=agent_mode)
        guidance["map_ids"] = selected_map_ids
        guidance["entity_hints"] = hints
        guidance["sources"] = sources
        guidance["views"] = views

        if not guidance["matched"]:
            return _standard_failure(
                self.name,
                "认知地图未命中可用实体或关系；请补充站点、告警、故障现象、污染物、工单号或时间范围。",
                "no graph matches",
                guidance,
            )

        return build_guidance_response(
            guidance,
            include_views=include_views,
        )


async def cognitive_map_guidance(context=None, **kwargs: Any) -> dict[str, Any]:
    return await CognitiveMapGuidanceTool().execute(context=context, **kwargs)
