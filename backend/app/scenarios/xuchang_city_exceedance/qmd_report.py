"""Render a bounded, evidence-led Xuchang process report from a frozen brief."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.path_config import resolve_agent_path

TITLE = "许昌市城市超标污染快速溯源分析报告"


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "；")


def _table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _station_table(rows: list[dict[str, Any]], *, limit: int = 10) -> str:
    if not rows:
        return "该类站点在分析窗口内没有可比较的有效小时数据。"
    return _table(("站点", "有效小时", "窗口均值", "峰值", "峰值时间"), [
        (item.get("station_name"), item.get("valid_hours"), item.get("mean"),
         item.get("peak"), item.get("peak_time")) for item in rows[:limit]
    ])


def build_qmd_report(evidence: dict[str, Any], agent_text: dict[str, Any]) -> str:
    window = evidence.get("process_window") or {}
    trigger = evidence.get("trigger") or {}
    quality = evidence.get("data_quality") or {}
    meteo = evidence.get("meteorology_evidence") or {}
    space = evidence.get("township_and_provincial_transport") or {}
    trajectory = evidence.get("trajectory_quality") or {}
    diagnosis = evidence.get("transport_diagnosis") or {}
    cwt = evidence.get("cwt") or {}
    screening = evidence.get("enterprise_screening") or {}
    pollutant = str(evidence.get("target_pollutant") or "")
    unit = "指数" if pollutant == "AQI" else "μg/m³"
    process_rows = [row for row in evidence.get("station_hourly") or []
                    if window.get("start") <= row.get("data_time", "") <= window.get("last_trigger_hour", "")]
    field = {"PM2.5": "pm25", "PM10": "pm10", "O3": "o3", "AQI": "aqi"}.get(pollutant)
    concentrations = [(row.get("data_time"), float(row[field])) for row in process_rows
                      if field and row.get(field) is not None]
    peak = max(concentrations, key=lambda item: item[1]) if concentrations else None
    lines = [
        "---", f'title: "{TITLE}"', f'date: "{evidence.get("target_date") or ""}"',
        "format:", "  html:", "    toc: false", "    number-sections: false",
        "  docx:", "    toc: false", "    number-sections: false", "---", "",
        f"报告对象：{_cell(evidence.get('station_name'))}，{pollutant}；"
        f"过程起点 {_cell(window.get('start'))}；最近触发小时 {_cell(window.get('last_trigger_hour'))}。", "",
        "本报告为污染过程初次分析截面。小时 AQI、业务高值与日均法定限值分别解释；"
        "监测和轨迹线索不构成企业责任或贡献率认定。", "",
        "## 一、污染过程概况", "",
        str(agent_text.get("summary_text") or "本次过程已触发分析，具体机制需要结合下列证据核查。"), "",
        _table(("项目", "证据"), [
            ("站点类型", evidence.get("station_type")),
            ("触发小时数", len(trigger.get("hours") or [])),
            ("过程峰值", f"{peak[1]} {unit}" if peak else None),
            ("峰值时间", peak[0] if peak else None),
            ("目标站有效小时", quality.get("target_valid_hours")),
            ("气象有效小时", quality.get("meteorology_hours")),
            ("判定依据", trigger.get("standard")),
        ]), "",
        "## 二、空气质量时空特征", "",
        str(agent_text.get("air_quality_analysis") or "站点时空差异仅作为筛查线索。"), "",
        f"### 国控站同期 {pollutant} 浓度（{unit}）", "",
        _station_table(space.get("national_station_summary") or []), "",
        f"### 乡镇站同期 {pollutant} 浓度（{unit}）", "",
        _station_table(space.get("township_station_summary") or []), "",
        f"### 周边城市同期 {pollutant} 浓度（{unit}）", "",
        _station_table(space.get("regional_city_summary") or []), "",
        "## 三、气象扩散条件", "",
        str(agent_text.get("meteorology_analysis") or "现有气象数据不足以单独判断污染来源。"), "",
        _table(("气象证据", "结果"), [
            ("实测/ERA5小时覆盖", (meteo.get("source_coverage") or {}).get("merged_hours")),
            ("边界层分析", (meteo.get("boundary_layer_analysis") or {}).get("classification")),
            ("高湿转化线索", (meteo.get("high_humidity_conversion_analysis") or {}).get("classification")),
            ("逆温代理判据", (meteo.get("temperature_inversion_analysis") or {}).get("classification")),
        ]), "",
        "## 四、区域传输线索", "",
        str(agent_text.get("transport_analysis") or "仅根据可用轨迹与区域观测描述潜在传输线索。"), "",
        _table(("轨迹证据", "结果"), [
            ("轨迹质量", trajectory.get("status")),
            ("有效轨迹", trajectory.get("valid_trajectories")),
            ("传输倾向", diagnosis.get("classification")),
            ("CWT 状态", cwt.get("status")),
        ]), "",
    ]
    if any(item.get("role") == "regional_trajectory_corridor_map" for item in evidence.get("visualizations") or []):
        image = next(item for item in evidence["visualizations"]
                     if item.get("role") == "regional_trajectory_corridor_map")
        lines.extend(["### 后向轨迹线索图", "",
                      f"![后向轨迹线索图](assets/charts/{Path(image['path']).name})", "",
                      "图示仅为潜在输送路径，不代表源贡献率。", ""])
    lines.extend([
        "## 五、本地候选核查", "",
        str(agent_text.get("local_source_analysis") or "现有证据不足以确定具体企业，建议核对同期活动记录。"), "",
    ])
    if screening.get("status") == "screened" and screening.get("enterprises"):
        lines.extend([_table(("待核查企业", "行业", "距离(km)", "方位", "依据"), [
            (item.get("enterprise_name"), item.get("industry_category"),
             item.get("distance_km"), item.get("bearing_deg"), item.get("screening_reason"))
            for item in screening["enterprises"][:10]
        ]), "", "该清单是核查顺序，不是排放贡献率或责任排名。", ""])
    else:
        lines.extend(["企业候选筛查未具备足够条件，本次不列具体企业。", ""])
    lines.extend(["## 六、结论与建议", "",
                  str(agent_text.get("conclusion") or "请补齐缺测证据并开展现场核查。"), ""])
    return "\n".join(lines)


def write_qmd_report_from_evidence(
    evidence_path: str, agent_text: dict[str, Any], output_path: str,
) -> dict[str, Any]:
    """Write one self-contained QMD; return the report-package tool contract."""
    evidence = json.loads(resolve_agent_path(evidence_path).read_text(encoding="utf-8"))
    if evidence.get("schema_version") != "xuchang_city_source_analysis/v1":
        raise ValueError("city exceedance evidence schema mismatch")
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = []
    for item in evidence.get("visualizations") or []:
        if item.get("role") != "regional_trajectory_corridor_map":
            continue
        image = resolve_agent_path(item["path"])
        if image.is_file() and image.suffix.lower() == ".png":
            assets.append({"path": str(image), "type": "image", "name": image.name})
    if not assets:
        evidence = {**evidence, "visualizations": []}
    output.write_text(build_qmd_report(evidence, agent_text), encoding="utf-8")
    return {"report_id": f"{evidence['analysis_id']}-report", "source_qmd_path": str(output),
            "source_qmd_name": output.name, "assets": assets}
