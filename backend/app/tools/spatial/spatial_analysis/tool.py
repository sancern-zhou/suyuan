from __future__ import annotations

from typing import Any

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.spatial.spatial_analysis.engine import execute_spatial_spec


SPATIAL_ANALYSIS_GUIDE_PATH = "/home/xckj/suyuan/backend/app/tools/spatial/spatial_analysis/spatial_analysis_guide.md"


class SpatialAnalysisTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="spatial_analysis",
            description=(
                "Execute an Agent-authored GIS spatial analysis spec. "
                "Use this for generic spatial operations such as buffer, intersect, filter, nearest, distance, aggregate, top_n, and upwind_sector, "
                "then pass returned data_id values to gisctl for map display. "
                f"Before complex use, read {SPATIAL_ANALYSIS_GUIDE_PATH}."
            ),
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "spatial_analysis",
                "description": (
                    "通用空间分析执行工具。Agent 生成 spatial-spec JSON，后端校验并执行基础 GIS 操作，"
                    "将结果注册为 DataRegistry 资产。适合站点周边污染源、空间相交、缓冲区、按区域聚合等场景。"
                    "本工具只做空间分析和资产注册，不直接控制地图；需要展示时继续调用 gisctl。"
                    "复杂空间分析前先用 read_file 阅读 "
                    f"{SPATIAL_ANALYSIS_GUIDE_PATH}。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "spec": {
                            "type": "object",
                            "description": (
                                "spatial-spec.v1 JSON。包含 inputs、steps、outputs。"
                                "首版支持 inline-feature、data-asset 经纬度点输入；"
                                "支持 op: buffer, intersect, filter, distance, nearest, aggregate, top_n, upwind_sector。"
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
        return execute_spatial_spec(spec)
