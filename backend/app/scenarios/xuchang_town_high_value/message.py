"""用户指定格式的乡镇高值提醒文案。"""

from __future__ import annotations

from typing import Any

from app.scenarios.xuchang_station_deviation.alert_notification import _meteorology_clause


def _value(value: float) -> str:
    return f"{value:.1f}"


def render_message(group: dict[str, Any], weather: dict[str, Any]) -> str:
    stations = group["stations"]
    pollutant = group["pollutant"]
    hour = group["hour"]
    facts = []
    for item in stations:
        facts.append(
            f"{item['station_name']}{pollutant}浓度实时小时数据为{_value(item['value'])}微克/立方米"
            f"，其他有效乡镇站中位数为{_value(item['baseline'])}微克/立方米"
            f"（{item['level_name']}，高于空间基线{item['level_difference']}级，"
            f"浓度差{_value(item['absolute_difference'])}微克/立方米，"
            f"相对差{item['relative_difference']:.1%}）"
        )
    if len(stations) > 2:
        headline = f"{len(stations)}个乡镇站出现{pollutant}空间高值：" + "；".join(facts)
    else:
        headline = "；".join(facts)
    meteorology = _meteorology_clause(weather, hour.isoformat())
    return (
        f"【乡镇高值提醒】{hour:%H}时{hour:%M}分乡镇站数据显示{headline}。"
        "请属地加强上风向及乡镇站点周边污染源排查，"
        f"当前气象情况：{meteorology}。"
    )
