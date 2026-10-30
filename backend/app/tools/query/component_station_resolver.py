"""超级站组分站点名称→编码解析（PM2.5 组分与 VOCs 查询工具共享）。

单一事实来源：`ParticulateGeoMatcher` + `geo_mappings.json`。
组分站点与常规空气质量监测站点是两套体系（编码以 `b` 结尾），
城市名不在映射表内：调用方须传入具体站点名或站点编码。

组分监测能力（geo_mappings.json 的 station_capabilities）用于取数前拦截：
对无 VOCs 设备的站调 VOCs 工具只会拿到全"—"的占位行，容易被误读成
"该时段无数据"；`require_domain` 在解析阶段直接拦下并给出有能力的站点清单。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from app.tools.guangdong.component_station_catalog.provider import load_capability_map
from app.utils.particulate_geo_matcher import get_particulate_geo_matcher


def available_station_text() -> str:
    """全部可用组分站点的 `站点名=编码` 文本（按编码排序）。"""
    matcher = get_particulate_geo_matcher()
    return "、".join(
        f"{name}={code}"
        for name, code in sorted(matcher.station_codes.items(), key=lambda item: item[1])
    )


def _capable_station_text(domain: str) -> str:
    """具备指定组分监测能力的 `站点名=编码` 文本（按编码排序）。"""

    matcher = get_particulate_geo_matcher()
    capabilities = load_capability_map()
    return "、".join(
        f"{name}={matcher.station_codes[name]}"
        for name in sorted(matcher.station_codes, key=lambda item: matcher.station_codes[item])
        if domain in capabilities.get(name, ())
    )


def resolve_component_station(
    *,
    locations: Union[List[str], None],
    station: Union[str, None],
    code: Union[str, None],
    require_domain: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """解析组分站点名/编码，返回 `(station, code, error)`。

    - `locations` / `station` 接受站点全名（精确匹配优先，子串匹配兜底）；
      一次只允许一个站点，多站点由调用方在同一轮并行多次调用。
    - 只提供 `code` 时直接放行（station 为 None）。
    - `require_domain`（"vocs"/"pm25"）：解析命中的站点不具备该组分监测能力时
      返回错误并列出有能力站点，避免拿占位空值当业务数据。
    - 失败时 `error` 携带完整可用站点清单，供编排模型自行修正。
    """
    names: List[str] = []
    if locations:
        names = [str(item).strip() for item in locations if str(item).strip()]
    elif station:
        names = [str(station).strip()]

    if len(names) > 1:
        return None, None, {
            "success": False,
            "error": (
                "一次只支持查询一个组分站点；请在同一轮对多个站点并行多次调用本工具。"
                f"本次收到 {len(names)} 个站点：{'、'.join(names)[:120]}"
            ),
        }

    if not names:
        if code:
            return None, str(code).strip(), None
        return None, None, {
            "success": False,
            "error": (
                "必须提供组分站点名称 station（或站点编码 code）。"
                f"可用组分站点：{available_station_text()}"
            ),
        }

    name = names[0]
    matcher = get_particulate_geo_matcher()
    matched_name = resolve_station_name(matcher, name)
    if not matched_name:
        return None, None, {
            "success": False,
            "error": (
                f"站点 '{name}' 不在超级站组分站点清单中，不要用城市名或常规监测站名代替。"
                f"可用组分站点：{available_station_text()}"
            ),
        }

    resolved_code = str(code).strip() if code else matcher.station_codes[matched_name]
    if require_domain:
        capabilities = load_capability_map()
        if require_domain not in capabilities.get(matched_name, ()):
            return None, None, {
                "success": False,
                "error": (
                    f"组分站 '{matched_name}'（{resolved_code}）无该类组分监测能力"
                    "（接口只会返回占位空值，不代表该时段无数据）。"
                    f"具备该能力的组分站：{_capable_station_text(require_domain)}。"
                ),
            }
    return matched_name, resolved_code, None


def resolve_station_name(matcher, name: str) -> str:
    """站点名解析：精确 → 前缀 → 包含；同级取最短名（更具体、歧义更小）。"""
    if name in matcher.station_codes:
        return name
    candidates = sorted(matcher.station_codes, key=lambda item: (len(item), matcher.station_codes[item]))
    for candidate in candidates:
        if candidate.startswith(name):
            return candidate
    for candidate in candidates:
        if name in candidate:
            return candidate
    return ""
