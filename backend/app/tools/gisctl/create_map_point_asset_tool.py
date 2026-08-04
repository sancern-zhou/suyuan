from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.tools.base.tool_interface import LLMTool, ToolCategory


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in record.items()}


class CreateMapPointAssetTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="create_map_point_asset",
            description=(
                "Create a session point-data file from Agent-selected records with coordinates. "
                "Use this after the Agent has selected stations/features and before calling visual_interaction point-layer."
            ),
            category=ToolCategory.VISUALIZATION,
            function_schema={
                "name": "create_map_point_asset",
                "description": (
                    "地图点数据资产创建工具。Agent 已经从查询/分析结果中确定要上图的点对象后，"
                    "传入带经纬度的 records，工具保存会话数据文件并登记统一资源，返回可继续传给 visual_interaction 的命令草案。"
                    "本工具不负责判断最高值或业务结论。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "点数据/图层显示名称。"},
                        "records": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Agent 选出的点记录。每条记录必须包含经纬度字段。",
                        },
                        "longitude_field": {
                            "type": "string",
                            "description": "经度字段名，默认 longitude。",
                        },
                        "latitude_field": {
                            "type": "string",
                            "description": "纬度字段名，默认 latitude。",
                        },
                        "layer_id": {"type": "string", "description": "建议的地图图层 ID。"},
                        "color_by": {"type": "string", "description": "可选，后续 visual_interaction 着色字段。"},
                        "zoom": {"type": "number", "description": "可选，单点定位缩放级别。"},
                        "turn_id": {"type": "string", "description": "可选，对话轮次 ID。"},
                        "metadata": {"type": "object", "description": "可选，附加元数据。"},
                    },
                    "required": ["name", "records"],
                },
            },
            version="0.1.0",
            requires_context=True,
        )

    async def execute(
        self,
        context,
        name: str,
        records: list[dict[str, Any]],
        longitude_field: str = "longitude",
        latitude_field: str = "latitude",
        layer_id: str | None = None,
        color_by: str | None = None,
        zoom: float | int | None = 14,
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        if not records:
            return self._failed(
                "MAP_POINT_RECORDS_REQUIRED",
                "No point records were provided.",
                ["resolve_station_geo", "execute_python"],
            )

        clean_records = [_clean_record(record) for record in records if isinstance(record, dict)]
        valid_records: list[dict[str, Any]] = []
        invalid_count = 0
        for record in clean_records:
            lon = _to_float(record.get(longitude_field))
            lat = _to_float(record.get(latitude_field))
            if lon is None or lat is None:
                invalid_count += 1
                continue
            record[longitude_field] = lon
            record[latitude_field] = lat
            valid_records.append(record)

        if not valid_records:
            return self._failed(
                "MAP_POINT_COORDINATES_REQUIRED",
                f"No records contain usable {longitude_field}/{latitude_field} coordinates.",
                ["resolve_station_geo", "execute_python"],
                metadata_extra={
                    "longitude_field": longitude_field,
                    "latitude_field": latitude_field,
                    "invalid_record_count": invalid_count,
                },
            )

        layer_id = layer_id or f"agent_point_{uuid4().hex[:10]}"
        file_path = context.save_data(
            valid_records,
            schema="map_point_asset",
            metadata={
                "name": name,
                "source": "create_map_point_asset",
                "longitude_field": longitude_field,
                "latitude_field": latitude_field,
                "layer_id": layer_id,
                "color_by": color_by,
                "turn_id": turn_id,
                **(metadata or {}),
            },
        )

        first = valid_records[0]
        point_layer_command: dict[str, Any] = {
            "family": "map-spec",
            "action": "create",
            "kind": "point-layer",
            "file_path": file_path,
            "layer_id": layer_id,
            "name": name,
            "lon": longitude_field,
            "lat": latitude_field,
            "fit_bounds": True,
        }
        if color_by:
            point_layer_command["color_by"] = color_by
        if turn_id:
            point_layer_command["turn_id"] = turn_id

        set_view_command: dict[str, Any] = {
            "family": "map-spec",
            "action": "create",
            "kind": "set-view",
            "name": str(first.get("station_name") or first.get("name") or name),
            "center": [first[longitude_field], first[latitude_field]],
        }
        if zoom is not None:
            set_view_command["zoom"] = zoom
        if turn_id:
            set_view_command["turn_id"] = turn_id

        return {
            "status": "success",
            "success": True,
            "file_path": file_path,
            "summary": f"已创建地图点数据文件 {file_path}，包含 {len(valid_records)} 个点。",
            "data": {
                "file_path": file_path,
                "record_count": len(valid_records),
                "longitude_field": longitude_field,
                "latitude_field": latitude_field,
                "layer_id": layer_id,
                "sample": valid_records[:5],
                "suggested_visual_interaction_commands": [point_layer_command, set_view_command],
                "suggested_gisctl_commands": [point_layer_command, set_view_command],
            },
            "metadata": {
                "tool_name": "create_map_point_asset",
                "generator": "create_map_point_asset",
                "file_path": file_path,
                "record_count": len(valid_records),
                "invalid_record_count": invalid_count,
                "longitude_field": longitude_field,
                "latitude_field": latitude_field,
                "suggested_next_tool": "visual_interaction",
            },
        }

    @staticmethod
    def _failed(
        error_code: str,
        summary: str,
        suggested_next_tools: list[str],
        metadata_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "success": False,
            "summary": summary,
            "data": {"file_path": None, "suggested_visual_interaction_commands": [], "suggested_gisctl_commands": []},
            "metadata": {
                "tool_name": "create_map_point_asset",
                "generator": "create_map_point_asset",
                "error_code": error_code,
                "suggested_next_tools": suggested_next_tools,
                **(metadata_extra or {}),
            },
        }
