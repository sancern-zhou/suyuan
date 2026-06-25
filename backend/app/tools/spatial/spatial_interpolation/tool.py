from __future__ import annotations

from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.spatial.spatial_interpolation.engine import execute_interpolation


SPATIAL_INTERPOLATION_GUIDE_PATH = "/home/xckj/suyuan/backend/app/tools/spatial/spatial_interpolation/spatial_interpolation_guide.md"


class SpatialInterpolationTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="spatial_interpolation",
            description=(
                "Execute concentration spatial interpolation under the GIS spatial capability layer. "
                "Use this for pollutant concentration surfaces, IDW/griddata fallback, and kriging when PyKrige is available. "
                "Outputs DataRegistry grid/surface/contour assets for map analysis; use the surface data_id with gisctl interpolation-layer for map rendering. "
                f"Before complex use, read {SPATIAL_INTERPOLATION_GUIDE_PATH}."
            ),
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "spatial_interpolation",
                "description": (
                    "浓度空间插值分析工具。输入 DataRegistry data_id、经纬度字段和值字段，"
                    "生成插值网格、插值渲染面和等值线 DataRegistry 资产，用于后续地图分析渲染；本工具不生成静态图片。"
                    "支持 method: kriging, idw, linear, cubic, nearest。"
                    "kriging 需要 PyKrige；缺失时除非 allow_fallback=true，否则返回依赖错误。"
                    "复杂插值、需要地图展示或不确定字段/方法时，先用 read_file 阅读 "
                    f"{SPATIAL_INTERPOLATION_GUIDE_PATH}。"
                    "需要显示到地图时，优先使用返回的 surface data_id 调用 gisctl map-spec create interpolation-layer；"
                    "contours data_id 可用 gisctl map-spec create line-layer 作为可选等值线叠加。"
                    "再调用 wait_map_program_receipt；没有有效回执前不得声称插值图层已显示。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "spec": {
                            "type": "object",
                            "description": (
                                "空间插值 spec。字段包括 data_id, lon, lat, value, pollutant, unit, method, "
                                "grid_size, contour_levels, allow_fallback。"
                            ),
                        }
                    },
                    "required": ["spec"],
                },
            },
            version="0.1.0",
            requires_context=False,
        )

    async def execute(self, spec: dict[str, Any], **_: Any) -> dict[str, Any]:
        return execute_interpolation(spec)
