from __future__ import annotations

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.gisctl.asset_resolver import resolve_map_data_asset


RESOLVE_MAP_DATA_ASSET_SCHEMA = {
    "name": "resolve_map_data_asset",
    "description": """地图数据资产发现工具。创建 GIS 数据图层前必须先调用本工具，按语义资产 profile 查找真实存在且允许 Agent 自动选择的 DataRegistry 数据资产，再校验经纬度等字段。

适用场景：
- 用户要求打开站点图层、热力图、高亮站点、把查询结果显示到地图
- 需要为 gisctl point-layer 命令选择真实 data_id
- 需要确认 longitude/latitude 或等价经纬度字段名

不要编造 data_id；不要选择 test/temp/debug/hidden 资产；如果没有候选资产，应先查询数据或告知缺少可地图化数据。""",
    "parameters": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": "用户希望展示的地图数据意图，例如“广东站点图层”“当前查询结果站点分布”。",
            },
            "asset_profile": {
                "type": "string",
                "description": "语义资产画像。站点点图层使用 map_layer_source.station_points，污染源点图层使用 map_layer_source.pollution_sources；不确定时可省略，由工具根据 intent 推断。",
            },
            "required_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "必须存在的字段。点图层通常包含 longitude 和 latitude。",
            },
            "preferred_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "优先匹配字段，例如 station_name、city、aqi、pm25。",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "最多返回候选数量。",
                "default": 5,
            },
            "scan_limit": {
                "type": "integer",
                "minimum": 100,
                "maximum": 20000,
                "description": "最多扫描最近多少个 DataRegistry 资产；默认优先最近资产。",
                "default": 1000,
            },
        },
        "required": ["intent"],
    },
}


class ResolveMapDataAssetTool(LLMTool):
    def __init__(self):
        super().__init__(
            name="resolve_map_data_asset",
            description="Discover real mappable DataRegistry assets before creating GIS layers.",
            category=ToolCategory.QUERY,
            function_schema=RESOLVE_MAP_DATA_ASSET_SCHEMA,
            version="0.1.0",
            requires_context=False,
        )

    async def execute(
        self,
        intent: str,
        asset_profile: str | None = None,
        required_fields: list[str] | None = None,
        preferred_fields: list[str] | None = None,
        limit: int = 5,
        scan_limit: int = 1000,
        **kwargs,
    ) -> dict:
        return resolve_map_data_asset(
            intent=intent,
            asset_profile=asset_profile,
            required_fields=required_fields,
            preferred_fields=preferred_fields,
            limit=limit,
            scan_limit=scan_limit,
        )
