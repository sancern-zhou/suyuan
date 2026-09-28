"""Build one QMD source for interactive HTML and readable Word exports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .html_report import (
    HTML_HEAD,
    _alert_times,
    _comparison,
    _number,
    _time,
    _wind_text,
    load_report_payload_from_evidence,
    render_map_script,
    render_map_widgets,
)


TITLE = "许昌市空气质量回顾分析日报"
COLS_BASIC = ("站点", "污染物", "升高时段", "浓度变化", "升幅", "绝对增量")
COLS_NEIGHBOR = ("类型", "站名", "距离(km)", "方位", "浓度", "对比")


def _cell(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", "；")


def _table(headers: tuple[str, ...], rows: list[tuple[Any, ...]], right: set[int]) -> str:
    divider = ["---:" if index in right else "---" for index in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(divider) + " |"]
    lines.extend("| " + " | ".join(_cell(item) for item in row) + " |" for row in rows)
    return "\n".join(lines)


def _neighbor_table(event: dict[str, Any], unit: str) -> str:
    rows: list[tuple[Any, ...]] = [(
        "国控点", event.get("station_name"), "—", "—", _number(event.get("target_mean")), "—",
    )]
    rows.extend((
        "上风向乡镇站", item.get("station_name"), _number(item.get("distance_km")),
        item.get("bearing_name"), _number(item.get("concentration_mean")), _comparison(item),
    ) for item in event.get("upwind_township_stations") or [])
    if len(rows) == 1:
        rows.append(("说明", "无符合条件的上风向乡镇站", "—", "—", "—", "—"))
    headers = (*COLS_NEIGHBOR[:4], f"浓度({unit})", COLS_NEIGHBOR[5])
    return _table(headers, rows, {2, 4})


def _event_body(event: dict[str, Any], analysis: str) -> str:
    pollutant = str(event["pollutant"])
    unit = "mg/m³" if pollutant == "CO" else "μg/m³"
    proxy = "（NO₂小时浓度代理）" if pollutant == "NOX" else ""
    segments = event.get("segments") or []
    lines = [f"#### 小时抬升时段｜{_alert_times(event)}", ""]
    if segments:
        lines.extend([
            f"过程跨度：{_time(event.get('start_time'))}—{_time(event.get('end_time'))}；"
            f"包含{len(segments)}段实际告警，间隔{event.get('gap_hour_count', 0)}个无告警小时；"
            f"全过程浓度变化：{_number(event.get('start_concentration'))} → "
            f"{_number(event.get('peak_concentration'))} {unit}；"
            f"峰值时间：{_time(event.get('peak_time'))}。", "",
        ])
        for index, segment in enumerate(segments, 1):
            rise = segment.get("peak_rise_percent")
            rise_text = f"{rise:g}%" if rise is not None else "基数为零或缺测"
            lines.extend([
                f"**第{index}段｜{_alert_times(segment)}**", "",
                f"浓度{proxy}：{_number(segment.get('start_concentration'))} → "
                f"{_number(segment.get('peak_concentration'))} {unit}；"
                f"峰值时间：{_time(segment.get('peak_time'))}；"
                f"峰值较{segment.get('reference_kind') or '参考小时'}变化 "
                f"{_number(segment.get('peak_rise_absolute'))} {unit}（{rise_text}）；"
                f"主导上风向：{_wind_text(segment)}。", "",
                _neighbor_table(segment, unit), "",
            ])
    else:
        rise = event.get("peak_rise_percent")
        rise_text = f"{rise:g}%" if rise is not None else "基数为零或缺测"
        clue_times = sorted({time for clue in event.get("minute_clues") or [] for time in clue.get("matched_times") or []})
        clue_text = "、".join(_time(time) for time in clue_times) if clue_times else "无匹配分钟线索"
        lines.extend([
            f"过程跨度：{_time(event.get('start_time'))}—{_time(event.get('end_time'))}；"
            f"浓度{proxy}：{_number(event.get('start_concentration'))} → "
            f"{_number(event.get('peak_concentration'))} {unit}；"
            f"峰值时间：{_time(event.get('peak_time'))}；"
            f"事件内峰值较{event.get('reference_kind') or '参考小时'}变化 "
            f"{_number(event.get('peak_rise_absolute'))} {unit}（{rise_text}）；"
            f"末值 {_number(event.get('end_concentration'))} {unit}；"
            f"主导上风向：{_wind_text(event)}；分钟线索：{clue_text}。", "",
            _neighbor_table(event, unit), "",
        ])
    lines.extend([
        "浓度为相应时段有效小时均值；对比采用双方同期有效小时，缺测时比较口径可能与整段均值不同。", "",
        analysis, "",
    ])
    return "\n".join(lines)


def _map_css() -> str:
    css = HTML_HEAD.split("<style>", 1)[1].split("</style>", 1)[0]
    return (
        ".xuchang-report-maps{max-width:1280px;margin:0 auto}"
        "section.map-card{background:#fff;border:1px solid #d9e2ec;margin:16px 0;padding:18px;border-radius:10px}"
        "button,select{font:inherit}\n.map-card{" + css.split(".map-card{", 1)[1]
        + ".map-hud{max-width:calc(100% - 28px);box-sizing:border-box}.map-hud span{overflow-wrap:anywhere}"
        + "@media print{.xuchang-html-only{display:none}}"
    )


def build_qmd_report(
    payload: dict[str, Any], *,
    css_name: str = "xuchang_map.css", js_name: str = "xuchang_map.js",
) -> str:
    events = payload.get("events") or []
    maps = payload.get("maps") or []
    date = str(payload.get("target_date") or "")
    gap_message = {
        "data_unavailable": "昨日小时数据不可用，无法判定持续快速抬升。",
        "insufficient_data": "昨日连续有效小时样本不足，无法判定持续快速抬升。",
    }.get(payload.get("alert_source_status"))
    default_summary = (
        gap_message
        if gap_message
        else (f"昨日识别持续快速抬升小时过程 {len(events)} 次。" if events else "昨日没有出现小时告警污染。")
    )
    lines = [
        "---", f'title: "{TITLE}"', f'date: "{date}"',
        "format:", "  html:", "    toc: false", "    number-sections: false",
        "    page-layout: full", f"    css: assets/{css_name}",
        "  docx:", "    toc: false", "    number-sections: false", "---", "",
        f"报告日期：{date}", "", "## 一、持续升高基本情况", "",
        str(payload.get("summary_text") or default_summary), "",
    ]
    if events:
        rows = []
        for event in events:
            ratio = event.get("peak_rise_percent")
            rows.append((
                event.get("station_name"), event.get("pollutant"), _alert_times(event),
                f"{_number(event.get('start_concentration'))} → {_number(event.get('peak_concentration'))}",
                f"{ratio:g}%" if ratio is not None else "—", _number(event.get("peak_rise_absolute")),
            ))
        lines.extend([_table(COLS_BASIC, rows, {4, 5}), ""])
    else:
        lines.extend([gap_message or "昨日没有出现小时告警污染。", ""])
    lines.extend([
        "仅将连续2或3小时严格升高、末值至少为初值1.5倍且达到污染物绝对增量门槛的小时过程列入；"
        "重叠命中窗口合并，分钟告警只作为同站同污染物的时间匹配线索，不单独触发。"
        "CO 单位为 mg/m³，其余为 μg/m³。", "",
        "## 二、持续升高原因分析", "",
        "风向为观测风来向。上风向候选仅表示方位与风向一致，不单独证明污染传输或来源。", "",
    ])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        groups.setdefault((str(event.get("station_id")), str(event["pollutant"])), []).append(event)
    for index, ((station_id, pollutant), group) in enumerate(groups.items(), 1):
        name = str(group[0].get("station_name") or station_id)
        station = name if name.endswith("站") else name + "站"
        lines.extend([f"### 2.{index} {station}｜{pollutant}（{len(group)}次过程）", ""])
        for event in group:
            lines.append(_event_body(event, payload["event_analysis"][event["event_id"]]))
    if not events:
        lines.extend(["昨日小时数据不足，专项分析缺少触发证据。" if gap_message else "昨日没有出现小时告警污染。", ""])
    if maps:
        lines.extend([
            '::: {.content-visible when-format="html"}',
            '<div class="xuchang-report-maps xuchang-html-only">',
            "<h3>污染物时序变化地图</h3>",
            "<p>HTML 版为真实高德地图，逐小时显示有效站点；红色光环标识当前小时告警国控站，"
            "站点填色采用全天固定浓度色阶，地图同步标注许昌气象站小时风向（来向）和风速。</p>",
            render_map_widgets(maps), "</div>",
            f'<script src="assets/{js_name}"></script>', ":::", "",
        ])
    lines.extend(["## 四、结论", "", str(payload.get("conclusion") or ""), ""])
    return "\n".join(lines)




def write_qmd_report_from_evidence(
    manifest_path: str, agent_text: dict[str, Any], output_path: str
) -> dict[str, Any]:
    """Write QMD and deterministic assets; return paths for create_report_package."""
    payload, amap_key = load_report_payload_from_evidence(manifest_path, agent_text)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    maps = payload["maps"]
    assets: list[dict[str, str]] = []
    suffix = re.sub(r"[^A-Za-z0-9_-]", "_", output.stem)
    css_name = f"xuchang_map_{suffix}.css"
    js_name = f"xuchang_map_{suffix}.js"
    css_path = output.parent / css_name
    css_path.write_text(_map_css(), encoding="utf-8")
    assets.append({"path": str(css_path), "type": "asset", "name": css_path.name})
    if maps:
        js_path = output.parent / js_name
        js_path.write_text(render_map_script(maps, payload["events"], amap_key), encoding="utf-8")
        assets.append({"path": str(js_path), "type": "asset", "name": js_path.name})
    output.write_text(build_qmd_report(payload, css_name=css_name, js_name=js_name), encoding="utf-8")
    report_id = "xuchang_daily_review_" + str(payload["target_date"]).replace("-", "")
    return {"report_id": report_id, "source_qmd_path": str(output),
            "source_qmd_name": output.name, "assets": assets,
            "event_count": len(payload["events"]), "pollutant_count": len(maps)}
