"""Render a bounded, evidence-led Xuchang process report from a frozen brief."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.utils.path_config import resolve_agent_path

TITLE = "许昌市城市超标污染快速溯源分析报告"
TZ = ZoneInfo("Asia/Shanghai")

DAILY_SCHEMA_VERSION = "xuchang_station_daily_source_analysis/v3"
UNIT_LABEL = "μg/m³"
PM25_DAY_LEVELS = ((75.0, 115.0, "轻度污染"), (115.0, 150.0, "中度污染"),
                   (150.0, 250.0, "重度污染"), (250.0, float("inf"), "严重污染"))
O3_DAY_LEVELS = ((160.0, 215.0, "轻度污染"), (215.0, 265.0, "中度污染"),
                 (265.0, 800.0, "重度污染"), (800.0, float("inf"), "严重污染"))


def _local_stamp(value: Any) -> datetime | None:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return stamp.astimezone(TZ) if stamp.tzinfo else stamp.replace(tzinfo=TZ)


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


def _daily_pollution_level(daily_value: Any, pollutant: str) -> str | None:
    try:
        value = float(daily_value)
    except (TypeError, ValueError):
        return None
    levels = O3_DAY_LEVELS if pollutant == "O3" else PM25_DAY_LEVELS
    for low, high, label in levels:
        if low < value <= high:
            return label
    return None


def _image_lines(images: dict[str, dict[str, Any]], role: str, caption: str) -> list[str]:
    artifact = images.get(role)
    if not artifact:
        return [f"{caption}：本次证据包未生成该图。", ""]
    return [f"![{caption}](assets/charts/{Path(artifact['path']).name})", "",
            f"{caption}", ""]


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _hour_label(value: Any) -> str:
    stamp = _local_stamp(value)
    return f"{stamp.hour}时" if stamp else "—"


def _peak_value(city_hourly: list[dict[str, Any]]) -> float:
    return max((point.get("peak") or 0) for point in city_hourly) if city_hourly else 0.0


def build_city_day_qmd_report(evidence: dict[str, Any], agent_text: dict[str, Any]) -> str:
    """Render the city-day exceedance report in the approved seven-section layout."""
    stats = evidence.get("city_day_statistics") or {}
    daypart = stats.get("daypart") or {}
    night = daypart.get("night") or {}
    afternoon = daypart.get("afternoon") or {}
    correlation = stats.get("pollutant_correlation") or {}
    medians = correlation.get("medians") or {}
    regional = stats.get("regional") or []
    township_top = stats.get("township_daily_top") or []
    peak_township = stats.get("peak_township") or {}
    coverage = stats.get("coverage") or {}
    quality = evidence.get("data_quality") or {}
    pollutant = str(evidence.get("target_pollutant") or "PM2.5")
    target_date = str(evidence.get("target_date") or "")
    level = _daily_pollution_level((evidence.get("daily_evaluation") or {}).get("value"), pollutant)
    title = (f"许昌市 {target_date} {level}溯源分析报告" if level
             else f"许昌市 {target_date} {pollutant}超标污染溯源分析报告")
    images = {item.get("role"): item for item in evidence.get("visualizations") or []
              if item.get("role") and item.get("path")}
    generated_at = _local_stamp(evidence.get("generated_at"))
    analysis_date = generated_at.date().isoformat() if generated_at else ""
    sync_cities = [item for item in regional
                   if (item.get("correlation_with_target") or 0) >= 0.8]
    city_peak = _peak_value(stats.get("city_hourly") or [])
    higher_peaks = [item["city"] for item in regional
                    if (item.get("peak") or 0) > city_peak]
    label_map = {"pm25": "PM2.5", "pm10": "PM10", "o3": "O3", "no2": "NO2", "so2": "SO2", "co": "CO"}
    key_pairs = ("pm25_co", "pm25_no2", "pm25_so2", "pm25_o3")
    lines = [
        "---", f'title: "{title}"', f'date: "{target_date}"',
        "format:", "  html:", "    toc: false", "    number-sections: false",
        "  docx:", "    toc: false", "    number-sections: false", "---", "",
        f"分析日期：{analysis_date}　　数据时段：{target_date} 00:00—23:00", "",
        "本报告为日尺度溯源分析。小时浓度、日均浓度与法定限值分别解释；"
        "企业清单为筛查排序，不构成贡献率或责任认定。", "",
        "## 一、分析摘要", "",
        str(agent_text.get("summary_text") or "本次超标过程的具体机制需结合以下证据核查。"), "",
        _table(("项目", "内容"), [
            ("超标站点", evidence.get("station_name")),
            ("目标污染物", pollutant),
            ("日均浓度", _fmt((evidence.get("daily_evaluation") or {}).get("value"), 1)),
            ("污染等级", level or "按发布值核定了超标"),
            ("国控站", f"{coverage.get('national_stations', '—')} 站"),
            ("乡镇站", f"{coverage.get('township_stations', '—')} 站"),
            ("周边城市", f"{coverage.get('regional_cities', '—')} 市"),
            ("气象小时", coverage.get("meteo_hours", "—")),
        ]), "",
        "## 二、污染过程与多点小时变化", "",
        str(agent_text.get("air_quality_analysis") or "全市国控站小时变化见下图。"), "",
        *_image_lines(images, "national_station_hourly_curves",
                      f"图1 国控站{pollutant}小时变化（各站+全市均值）"),
        *_image_lines(images, "urban_district_hourly_comparison",
                      "图2 城区均值与各区县乡镇站均值小时对比"),
        "## 三、气象扩散条件", "",
        str(agent_text.get("meteorology_analysis") or "气象扩散条件见下表与图3。"), "",
        *_image_lines(images, "meteorology_hourly_panel",
                      f"图3 {pollutant}与气象条件（风速/风向/湿度）小时变化"),
        _table(("要素", f"夜间({daypart.get('night_label', '0-8时')})",
                f"午后({daypart.get('afternoon_label', '12-17时')})", "判读"), [
            ("风速", f"{_fmt(night.get('wind_speed_mean_ms'), 2)} m/s",
             f"{_fmt(afternoon.get('wind_speed_mean_ms'), 2)} m/s",
             "夜间静风" if (night.get("wind_speed_mean_ms") or 9) < (afternoon.get("wind_speed_mean_ms") or 0) else "夜间风大于午后"),
            ("相对湿度", f"{_fmt(night.get('humidity_mean'), 0)}%",
             f"{_fmt(afternoon.get('humidity_mean'), 0)}%",
             "高湿促二次生成" if (night.get("humidity_mean") or 0) >= 80 else "湿度一般"),
            ("静风小时数", f"{night.get('calm_hours', '—')}/{night.get('meteo_hours', '—')}",
             f"{afternoon.get('calm_hours', '—')}/{afternoon.get('meteo_hours', '—')}",
             f"静风指风速<{daypart.get('calm_wind_definition', '').split('<')[-1] or '0.5 m/s'}"),
            ("主导风向",
             (night.get("dominant_wind") or {}).get("direction_from_name", "—"),
             (afternoon.get("dominant_wind") or {}).get("direction_from_name", "—"),
             "按风来向矢量平均"),
        ]), "",
        "## 四、本地排放与外来传输", "",
        str(agent_text.get("transport_analysis") or "区域对比与轨迹线索见下图。"), "",
        *_image_lines(images, "regional_city_hourly_comparison",
                      f"图4 许昌及周边城市{pollutant}小时变化对比"),
        *_image_lines(images, "regional_city_daypart_comparison",
                      "图5 周边城市夜间与午后均值对比"),
        _table(("城市", "日均", "峰值", "峰值时刻", "夜间均值", "午后均值", "夜/午比", "与许昌相关(r)"), [
            (item.get("city"), _fmt(item.get("daily_mean")), _fmt(item.get("peak")),
             _hour_label(item.get("peak_time") or ""), _fmt(item.get("night_mean")),
             _fmt(item.get("afternoon_mean")), _fmt(item.get("night_to_afternoon_ratio"), 2),
             _fmt(item.get("correlation_with_target"), 2))
            for item in regional
        ]), "",
        f"区域同步性：与许昌逐小时相关 r≥0.8 的城市为{'、'.join(item['city'] for item in sync_cities) or '无（样本不足）'}。",
        f"高于许昌峰值的周边城市：{'、'.join(higher_peaks) or '无'}。轨迹与传输定性判断见上文分析。", "",
        "## 五、污染源类型指示", "",
        str(agent_text.get("source_type_analysis") or "污染物相关性指示的源类型见下图。"), "",
        *_image_lines(images, "pollutant_correlation_heatmap",
                      "图6 污染物相关性热力图（Pearson 相关系数，逐站中位数）"),
        _table(("污染物对", "逐站中位数相关系数", "指示意义"), [
            ("PM2.5—CO", _fmt(medians.get("pm25_co"), 2), "不完全燃烧源（机动车/燃煤/生物质）"),
            ("PM2.5—NO2", _fmt(medians.get("pm25_no2"), 2), "NOx 共变，二次硝酸盐参与"),
            ("PM2.5—SO2", _fmt(medians.get("pm25_so2"), 2), "高硫燃煤固定源共变性"),
            ("PM2.5—O3", _fmt(medians.get("pm25_o3"), 2), "二次转化昼夜反相特征"),
        ]) if medians else "有效小时样本不足，未计算稳定的污染物相关性。", "",
        "## 六、空间分布与嫌疑企业", "",
        str(agent_text.get("spatial_analysis") or "乡镇站高值区空间分布见下图。"), "",
        f"日均浓度最高的乡镇站为{peak_township.get('station_name') or '—'}"
        f"（{peak_township.get('district') or '—'}，日均 {_fmt(peak_township.get('daily_mean'))} {UNIT_LABEL}）。", "",
        *_image_lines(images, "township_daily_spatial_distribution",
                      f"图7 乡镇站{pollutant}日均空间分布"),
        _table(("乡镇站", "区县", "日均", "有效小时"), [
            (item.get("station_name"), item.get("district"),
             _fmt(item.get("daily_mean")), item.get("valid_hours"))
            for item in township_top[:10]
        ]) if township_top else "乡镇站数据不足，未形成日均排序。", "",
        str(agent_text.get("local_source_analysis") or "嫌疑企业为清单筛查排序，供现场核查参考。"), "",
        *_image_lines(images, "enterprise_screening_top10",
                      "图8 嫌疑企业Top10筛查得分（颜色=行业，标注距高值镇街距离）"),
    ]
    screening = evidence.get("enterprise_screening") or {}
    if screening.get("status") == "screened" and screening.get("enterprises"):
        lines.extend([
            _table(("排名", "企业名称", "行业", "区县", "筛查得分", "距高值镇街", "上风向扇区"), [
                (index + 1, item.get("enterprise_name"), item.get("industry_category"),
                 item.get("district") or "—", _fmt(item.get("screening_score")),
                 f"{_fmt(item.get('distance_to_high_value_km'), 2)} km"
                 if item.get("distance_to_high_value_km") is not None else "—",
                 "是" if item.get("in_upwind_sector") else "否")
                for index, item in enumerate(screening["enterprises"][:10])
            ]), "",
            "筛查得分为清单年排放量的距离衰减排序，仅表示现场核查顺序，"
            "不代表同期排放、贡献率或企业责任。", "",
        ])
    else:
        lines.extend([
            f"企业筛查未具备输出条件（{screening.get('reason') or screening.get('status') or '清单不可用'}），"
            "本次不列具体企业。", "",
        ])
    lines.extend([
        "## 七、结论与建议", "",
        str(agent_text.get("conclusion") or
            "结论需覆盖污染类型、本地与传输关系、源类型和高值区四个维度，并给出针对性管控建议。"), "",
    ])
    return "\n".join(lines)


def write_city_day_qmd_report(
    evidence_path: str, agent_text: dict[str, Any], output_path: str,
) -> dict[str, Any]:
    """Write the city-day QMD from the frozen daily evidence; return assets contract."""
    evidence = json.loads(resolve_agent_path(evidence_path).read_text(encoding="utf-8"))
    if evidence.get("schema_version") != DAILY_SCHEMA_VERSION:
        raise ValueError("city day exceedance evidence schema mismatch")
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = []
    for item in evidence.get("visualizations") or []:
        image = resolve_agent_path(item["path"]) if item.get("path") else None
        if image and image.is_file() and image.suffix.lower() == ".png":
            assets.append({"path": str(image), "type": "image", "name": image.name})
    if not assets:
        evidence = {**evidence, "visualizations": []}
    output.write_text(build_city_day_qmd_report(evidence, agent_text), encoding="utf-8")
    return {"report_id": f"{evidence.get('analysis_id') or evidence.get('target_date')}-report",
            "source_qmd_path": str(output), "source_qmd_name": output.name, "assets": assets}


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
    start = _local_stamp(window.get("start"))
    end = _local_stamp(window.get("last_trigger_hour")) or start
    field = {"PM2.5": "pm25", "PM10": "pm10", "O3": "o3", "AQI": "aqi"}.get(pollutant)
    concentrations = []
    if start and end and field:
        for row in evidence.get("station_hourly") or []:
            hour = _local_stamp(row.get("data_time"))
            if hour is None or not start <= hour <= end:
                continue
            try:
                concentrations.append((hour.isoformat(), float(row[field])))
            except (KeyError, TypeError, ValueError):
                continue
    peak = max(concentrations, key=lambda item: item[1]) if concentrations else None
    rule_labels = {
        "published_hourly_aqi": "连续小时发布AQI≥101",
        "pm25_business_high": "PM2.5业务高值≥75 μg/m³",
        "station_peer_deviation": "站点相对同期同类站偏高",
    }
    actual_rules = sorted({item.get("rule") for item in trigger.get("rules") or [] if item.get("rule")})
    trigger_basis = "；".join(rule_labels.get(rule, rule) for rule in actual_rules)
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
            ("判定依据", trigger_basis or trigger.get("standard")),
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
