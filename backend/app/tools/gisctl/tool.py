from __future__ import annotations

import json
from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.context.data_files import resolve_data_path
from app.tools.gisctl.map_spec import (
    create_dashboard_layer_program,
    create_interpolation_layer_program,
    create_line_layer_program,
    create_point_layer_program,
    create_polygon_layer_program,
    create_set_view_program,
)
from app.tools.gisctl.models import GisctlResult
from app.tools.gisctl.place_resolver import resolve_place
from app.services.map_program_receipts import map_program_receipt_store


GISCTL_FUNCTION_SCHEMA = {
    "name": "visual_interaction",
    "description": """Agentic GIS 用户视觉交互工具。用于生成前端地图可执行的 map_program，把问数查询、分析结论和地图所见同步起来，实现回答即所见。

本工具不是简单的地图控制命令。每次问数查询都应同时判断是否需要更新用户视觉上下文：定位视角、叠加图层、高亮对象、打开/关闭看板图层或清除/替换当前回答图层。只要用户问题涉及城市、区域、站点、污染源、经纬度、空间范围或“在地图上看”的表达，就应优先考虑调用本工具让答案进入地图。

当前支持：
- map-spec create point-layer: 基于已有 file_path 生成点图层 map_program
- map-spec create polygon-layer: 基于已有 GeoJSON geometry file_path 生成面图层 map_program
- map-spec create line-layer: 基于已有 GeoJSON geometry file_path 生成线图层 map_program，适合插值等值线
- map-spec create interpolation-layer: 基于 spatial_interpolation 返回的 surface file_path 生成插值渲染面图层
- map-spec create set-view: 生成地图视图定位/缩放 map_program
- map-spec create dashboard-layer: 控制问数看板内置图层显隐，支持 city_metrics、stations、heatmap

point-layer 图标：
- 支持受控图标类型：station、pollution_source、factory、dust、traffic、fire、monitor、selected
- 可直接传 icon 让 Agent 为整层选择图标类型
- 可传 icon_by + icon_map + default_icon 根据要素字段映射图标
- 不支持任意 HTML、SVG 或图片 URL 图标

适用场景：
- 用户要求“在地图上显示/高亮/叠加”某类站点、污染物、区域分析结果
- 用户要求“定位到/缩放到/移动到”某城市、区域或坐标
- 用户要求“打开/关闭城市指标、站点、热力图”等问数看板内置图层
- 已有查询或分析结果 file_path，需要转成地图图层
- spatial_interpolation 已返回 surface file_path，需要在地图上新增插值渲染图层
- 对话中有 map_context，用户框选/切换图层后需要继续控制地图
- 查询结果有明确空间对象时，即使用户没有显式说“显示地图”，也应判断是否需要同步视觉呈现

注意：
- point-layer 必须使用真实存在的 DataRegistry file_path；如果不知道 file_path，先调用 resolve_map_data_asset。
- 插值分析展示优先使用 spatial_interpolation 输出的 surface file_path 调用 interpolation-layer；contours line-layer 只作为可选等值线叠加。
- 创建 point-layer、polygon-layer、line-layer、interpolation-layer 时默认 fit_bounds=true，前端会自动移动/放大到 Agent 本次操作生成的图层位置；只有用户明确要求保持当前视角时才传 fit_bounds=false。
- 不要编造 gd_stations 之类语义 file_path。
- map_program 是前端执行协议对象，不是给用户阅读的最终答案；生成 map_program 后应等待前端回执确认用户真实看见。
""",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "object",
                "description": "结构化视觉交互命令对象，用于生成前端可执行的 map_program。",
                "properties": {
                    "family": {"type": "string", "enum": ["map-spec"]},
                    "action": {"type": "string", "enum": ["create"]},
                    "kind": {"type": "string", "enum": ["point-layer", "polygon-layer", "line-layer", "interpolation-layer", "set-view", "dashboard-layer"]},
                    "file_path": {"type": "string", "description": "已存在的会话数据文件绝对路径。"},
                    "layer_id": {"type": "string", "description": "地图图层 ID。"},
                    "name": {"type": "string", "description": "地图图层显示名称；set-view 可省略，默认使用 target。"},
                    "lon": {"type": "string", "description": "经度字段名。"},
                    "lat": {"type": "string", "description": "纬度字段名。"},
                    "center": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "set-view 使用，[longitude, latitude]。"
                    },
                    "target": {
                        "type": "string",
                        "description": "set-view 使用，地名或业务空间对象名称；未提供 center 时由 visual_interaction 解析。"
                    },
                    "zoom": {"type": "number", "description": "set-view 使用，目标缩放级别。"},
                    "color_by": {"type": "string", "description": "可选，分类或连续着色字段名。"},
                    "breaks": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "可选，分级断点。"
                    },
                    "colors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选，颜色数组。"
                    },
                    "icon": {
                        "type": "string",
                        "description": "point-layer 使用，整层点图标类型。允许：station、pollution_source、factory、dust、traffic、fire、monitor、selected。"
                    },
                    "icon_by": {
                        "type": "string",
                        "description": "point-layer 使用，按该字段值映射点图标。"
                    },
                    "icon_map": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "point-layer 使用，字段值到图标类型的映射；图标类型必须来自受控列表。"
                    },
                    "default_icon": {
                        "type": "string",
                        "description": "point-layer 使用，字段映射未命中时使用的图标类型。"
                    },
                    "fit_bounds": {"type": "boolean", "description": "是否让地图自适应到本次 Agent 操作生成的图层范围；图层创建默认 true，用户明确要求保持当前视角时才设为 false。"},
                    "visible": {"type": "boolean", "description": "dashboard-layer 使用，是否显示图层。"},
                    "fill_color": {"type": "string", "description": "polygon-layer/interpolation-layer 使用，默认填充色。"},
                    "fill_opacity": {"type": "number", "description": "polygon-layer/interpolation-layer 使用，默认填充透明度。"},
                    "stroke_color": {"type": "string", "description": "polygon-layer/line-layer/interpolation-layer 使用，边框或线色。"},
                    "stroke_weight": {"type": "number", "description": "polygon-layer/line-layer/interpolation-layer 使用，边框或线宽度。"},
                    "stroke_opacity": {"type": "number", "description": "line-layer/polygon-layer/interpolation-layer 使用，线透明度。"},
                    "turn_id": {"type": "string", "description": "可选，对话轮次 ID。"}
                },
                "required": ["family", "action", "kind"]
            }
        },
        "required": ["command"]
    }
}


def _sample_fields(file_path: str) -> set[str]:
    path = resolve_data_path(file_path)
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    records = payload if isinstance(payload, list) else []
    fields: set[str] = set()
    for record in records[:5]:
        if isinstance(record, dict):
            fields.update(str(key) for key in record.keys())
    return fields


def _data_file_exists(file_path: str) -> bool:
    try:
        resolve_data_path(file_path)
        return True
    except (ValueError, PermissionError, FileNotFoundError):
        return False


def _failed_point_layer_result(
    *,
    summary: str,
    error_code: str,
    file_path: str | None = None,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    return GisctlResult.from_map_program(
        success=False,
        command="map-spec create point-layer",
        file_paths=[file_path] if file_path else [],
        map_program=None,
        summary=summary,
        metadata_extra={
            "error_code": error_code,
            "suggested_next_tool": "resolve_map_data_asset",
            **({"file_path": file_path} if file_path else {}),
            **({"missing_fields": missing_fields} if missing_fields else {}),
        },
    ).model_dump()


def execute_gisctl(command: dict[str, Any]) -> dict[str, Any]:
    family = command.get("family")
    action = command.get("action")
    kind = command.get("kind")

    if family == "map-spec" and action == "create" and kind == "point-layer":
        file_path = command["file_path"]
        if not _data_file_exists(file_path):
            return _failed_point_layer_result(
                file_path=file_path,
                error_code="MAP_DATA_ASSET_NOT_FOUND",
                summary=f"file_path not found: {file_path}. Call resolve_map_data_asset before creating a layer.",
            )

        fields = _sample_fields(file_path)
        required_fields = [command["lon"], command["lat"]]
        if command.get("color_by"):
            required_fields.append(command["color_by"])
        if command.get("icon_by"):
            required_fields.append(command["icon_by"])
        missing_fields = [field for field in required_fields if field not in fields]
        if missing_fields:
            return _failed_point_layer_result(
                file_path=file_path,
                error_code="MAP_DATA_ASSET_FIELDS_NOT_FOUND",
                missing_fields=missing_fields,
                summary=f"file_path {file_path} is missing map fields: {', '.join(missing_fields)}",
            )

        program = create_point_layer_program(
            file_path=file_path,
            layer_id=command["layer_id"],
            name=command["name"],
            longitude_field=command["lon"],
            latitude_field=command["lat"],
            color_by=command.get("color_by"),
            breaks=command.get("breaks"),
            colors=command.get("colors"),
            icon=command.get("icon"),
            icon_by=command.get("icon_by"),
            icon_map=command.get("icon_map"),
            default_icon=command.get("default_icon"),
            fit_bounds=command.get("fit_bounds", True),
            turn_id=command.get("turn_id"),
        )
        return GisctlResult.from_map_program(
            command="map-spec create point-layer",
            file_paths=[file_path],
            map_program=program.model_dump(),
            summary=f"Created point layer map program {command['layer_id']}",
        ).model_dump()

    if family == "map-spec" and action == "create" and kind == "polygon-layer":
        file_path = command["file_path"]
        if not _data_file_exists(file_path):
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create polygon-layer",
                file_paths=[file_path],
                map_program=None,
                summary=f"file_path not found: {file_path}. Call spatial_analysis or resolve_map_data_asset before creating a layer.",
                metadata_extra={
                    "error_code": "MAP_DATA_ASSET_NOT_FOUND",
                    "suggested_next_tool": "spatial_analysis",
                    "file_path": file_path,
                },
            ).model_dump()

        fields = _sample_fields(file_path)
        if "geometry" not in fields:
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create polygon-layer",
                file_paths=[file_path],
                map_program=None,
                summary=f"file_path {file_path} is missing GeoJSON geometry field.",
                metadata_extra={
                    "error_code": "MAP_DATA_ASSET_FIELDS_NOT_FOUND",
                    "suggested_next_tool": "spatial_analysis",
                    "file_path": file_path,
                    "missing_fields": ["geometry"],
                },
            ).model_dump()

        program = create_polygon_layer_program(
            file_path=file_path,
            layer_id=command["layer_id"],
            name=command["name"],
            fill_color=command.get("fill_color"),
            fill_opacity=command.get("fill_opacity"),
            stroke_color=command.get("stroke_color"),
            stroke_weight=command.get("stroke_weight"),
            fit_bounds=command.get("fit_bounds", True),
            turn_id=command.get("turn_id"),
        )
        return GisctlResult.from_map_program(
            command="map-spec create polygon-layer",
            file_paths=[file_path],
            map_program=program.model_dump(),
            summary=f"Created polygon layer map program {command['layer_id']}",
        ).model_dump()

    if family == "map-spec" and action == "create" and kind == "line-layer":
        file_path = command["file_path"]
        if not _data_file_exists(file_path):
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create line-layer",
                file_paths=[file_path],
                map_program=None,
                summary=f"file_path not found: {file_path}. Call spatial_interpolation or resolve_map_data_asset before creating a layer.",
                metadata_extra={
                    "error_code": "MAP_DATA_ASSET_NOT_FOUND",
                    "suggested_next_tool": "spatial_interpolation",
                    "file_path": file_path,
                },
            ).model_dump()

        fields = _sample_fields(file_path)
        if "geometry" not in fields:
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create line-layer",
                file_paths=[file_path],
                map_program=None,
                summary=f"file_path {file_path} is missing GeoJSON geometry field.",
                metadata_extra={
                    "error_code": "MAP_DATA_ASSET_FIELDS_NOT_FOUND",
                    "suggested_next_tool": "spatial_interpolation",
                    "file_path": file_path,
                    "missing_fields": ["geometry"],
                },
            ).model_dump()

        program = create_line_layer_program(
            file_path=file_path,
            layer_id=command["layer_id"],
            name=command["name"],
            stroke_color=command.get("stroke_color"),
            stroke_weight=command.get("stroke_weight"),
            stroke_opacity=command.get("stroke_opacity"),
            fit_bounds=command.get("fit_bounds", True),
            turn_id=command.get("turn_id"),
        )
        return GisctlResult.from_map_program(
            command="map-spec create line-layer",
            file_paths=[file_path],
            map_program=program.model_dump(),
            summary=f"Created line layer map program {command['layer_id']}",
        ).model_dump()

    if family == "map-spec" and action == "create" and kind == "interpolation-layer":
        file_path = command["file_path"]
        if not _data_file_exists(file_path):
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create interpolation-layer",
                file_paths=[file_path],
                map_program=None,
                summary=f"file_path not found: {file_path}. Call spatial_interpolation before creating an interpolation layer.",
                metadata_extra={
                    "error_code": "MAP_DATA_ASSET_NOT_FOUND",
                    "suggested_next_tool": "spatial_interpolation",
                    "file_path": file_path,
                },
            ).model_dump()

        fields = _sample_fields(file_path)
        if "geometry" not in fields:
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create interpolation-layer",
                file_paths=[file_path],
                map_program=None,
                summary=f"file_path {file_path} is missing GeoJSON geometry field.",
                metadata_extra={
                    "error_code": "MAP_DATA_ASSET_FIELDS_NOT_FOUND",
                    "suggested_next_tool": "spatial_interpolation",
                    "file_path": file_path,
                    "missing_fields": ["geometry"],
                },
            ).model_dump()

        program = create_interpolation_layer_program(
            file_path=file_path,
            layer_id=command["layer_id"],
            name=command["name"],
            fill_color=command.get("fill_color"),
            fill_opacity=command.get("fill_opacity"),
            stroke_color=command.get("stroke_color"),
            stroke_weight=command.get("stroke_weight"),
            stroke_opacity=command.get("stroke_opacity"),
            fit_bounds=command.get("fit_bounds", True),
            turn_id=command.get("turn_id"),
        )
        return GisctlResult.from_map_program(
            command="map-spec create interpolation-layer",
            file_paths=[file_path],
            map_program=program.model_dump(),
            summary=f"Created interpolation surface map program {command['layer_id']}",
        ).model_dump()

    if family == "map-spec" and action == "create" and kind == "dashboard-layer":
        layer_id = command["layer_id"]
        if layer_id not in {"city_metrics", "stations", "heatmap"}:
            return GisctlResult.from_map_program(
                success=False,
                command="map-spec create dashboard-layer",
                summary=f"Unsupported dashboard layer {layer_id}",
                map_program=None,
                metadata_extra={
                    "error_code": "DASHBOARD_LAYER_NOT_SUPPORTED",
                    "layer_id": layer_id,
                    "supported_layers": ["city_metrics", "stations", "heatmap"],
                },
            ).model_dump()

        program = create_dashboard_layer_program(
            layer_id=layer_id,
            name=command["name"],
            visible=command.get("visible", True),
            turn_id=command.get("turn_id"),
        )
        return GisctlResult.from_map_program(
            command="map-spec create dashboard-layer",
            file_paths=[],
            map_program=program.model_dump(),
            summary=f"Set dashboard layer {layer_id} visible={command.get('visible', True)}",
            metadata_extra={"dashboard_layer_id": layer_id},
        ).model_dump()

    if family == "map-spec" and action == "create" and kind == "set-view":
        center = command.get("center")
        zoom = command.get("zoom")
        target = command.get("target")
        name = command.get("name") or target or "地图视图"
        if not center:
            place = resolve_place(target or name)
            if not place:
                return GisctlResult.from_map_program(
                    success=False,
                    command="map-spec create set-view",
                    summary=f"Unable to resolve map target {target or name}",
                    map_program=None,
                ).model_dump()
            center = place.center
            zoom = zoom if zoom is not None else place.zoom
            name = place.name

        program = create_set_view_program(
            center=center,
            zoom=zoom,
            name=name,
            turn_id=command.get("turn_id"),
        )
        return GisctlResult.from_map_program(
            command="map-spec create set-view",
            file_paths=[],
            map_program=program.model_dump(),
            summary=f"Created set-view map program {name}",
        ).model_dump()

    return GisctlResult.from_map_program(
        success=False,
        command=f"{family or ''} {action or ''} {kind or ''}".strip(),
        summary="Unsupported visual_interaction command",
        map_program=None,
    ).model_dump()


class GisctlTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="visual_interaction",
            description="Generate executable map_program specs for query-mode visual interaction so answers are reflected in the map.",
            category=ToolCategory.VISUALIZATION,
            function_schema=GISCTL_FUNCTION_SCHEMA,
            version="0.1.0",
            requires_context=True,
        )

    async def execute(self, context: Any = None, command: dict[str, Any] | None = None, **kwargs) -> dict[str, Any]:
        if command is None and isinstance(context, dict):
            command = context
            context = None
        result = execute_gisctl(command or {})
        session_id = getattr(context, "session_id", None) if context is not None else None
        map_program = result.get("data", {}).get("map_program") if isinstance(result, dict) else None
        if session_id and isinstance(map_program, dict):
            try:
                pending = map_program_receipt_store.register_pending(session_id, map_program)
                result.setdefault("metadata", {})["map_program_pending"] = {
                    "session_id": session_id,
                    "program_id": pending.get("program_id"),
                    "status": pending.get("status"),
                }
                result.setdefault("data", {})["map_program_pending"] = {
                    "session_id": session_id,
                    "program_id": pending.get("program_id"),
                    "status": pending.get("status"),
                }
            except ValueError:
                pass
        return result
