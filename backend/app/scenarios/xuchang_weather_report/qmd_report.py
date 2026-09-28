"""Assemble and validate the fixed weather-report template from evidence."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.utils.path_config import resolve_agent_path
from .constants import SCHEMA, WEEKDAYS

TITLE = "许昌市未来7天-15天 污染扩散条件与空气质量分析报告"
HEADINGS = (
    "一、未来7天空气质量预报总览",
    "二、未来7天逐日污染扩散条件分析",
    "2.1逐日各时段扩散条件汇总",
    "2.2逐日气象要素详情",
    "2.3气象小时变化趋势分析",
    "2.4逐日气象扩散条件分析",
    "三、逐小时关键时点数据",
    "四、未来8-15天的气象扩散条件分析",
)
HEADERS = (
    ("日期", "AQI范围", "等级", "首要污染物", "扩散条件", "气象特点"),
    ("时段",),
    ("日期", "天气/温度", "上午风", "午后风", "夜间风", "最高湿", "扩散条件", "PM2.5", "O3", "不利时段"),
    ("日期", "天气", "温度", "风向", "风速", "湿度", "气压", "扩散提示"),
    ("日期", "天气", "最高温", "最低温", "主导风向", "风力", "午后风速", "扩散条件与风险"),
)
COLORS = {
    "好": ("diff-good", "#C6EFCE", "#375623"),
    "一般": ("diff-normal", "#FFEB9C", "#9C6500"),
    "较差": ("diff-poor", "#FCE4D6", "#974706"),
    "差": ("diff-bad", "#FFC7CE", "#9C0006"),
}
RISK_COLORS = {"高": ("risk-high", "#FFC7CE"), "中": ("risk-medium", "#FCE4D6"),
               "低": ("risk-low", "#FFEB9C")}
LEGEND = "绿=好，黄=一般，橙=较差，红=差；风险颜色表示气象条件支持的风险等级，不代表污染物实测等级。"
CSS = """<style>
.weekly-weather-report table { width: 100%; border-collapse: collapse; }
.weekly-weather-report th { background: #1F4E79; color: #FFFFFF; text-align: center; }
.weekly-weather-report th, .weekly-weather-report td { border: 1px solid #D9E2F3; padding: 6px 8px; vertical-align: middle; }
.diff-good { background: #C6EFCE; color: #375623; }
.diff-normal { background: #FFEB9C; color: #9C6500; }
.diff-poor { background: #FCE4D6; color: #974706; }
.diff-bad { background: #FFC7CE; color: #9C0006; }
.risk-high { background: #FFC7CE; color: #9C0006; font-weight: 700; }
.risk-medium { background: #FCE4D6; color: #974706; font-weight: 700; }
.risk-low { background: #FFEB9C; color: #9C6500; font-weight: 700; }
.value-high { background: #FFC7CE; color: #9C0006; font-weight: 700; }
.value-watch { background: #FFEB9C; color: #9C6500; }
.value-normal { background: #C6EFCE; color: #375623; }
</style>"""


def _text(value: Any, fallback: str = "未提供") -> str:
    return str(value).strip() if value is not None and str(value).strip() else fallback


def _num(value: Any, unit: str = "") -> str:
    return f"{float(value):g}{unit}" if value is not None else "未提供"


def _td(value: Any, grade: str | None = None, risk: str | None = None) -> str:
    style = "border:1px solid #D9E2F3;padding:6px 8px;vertical-align:middle"
    cls = ""
    if grade in COLORS:
        cls, bg, fg = COLORS[grade]
        style += f";background:{bg};color:{fg}"
    elif risk in RISK_COLORS:
        cls, bg = RISK_COLORS[risk]
        style += f";background:{bg};font-weight:700"
    attr = f' class="{cls}"' if cls else ""
    return f'<td{attr} style="{style}">{escape(_text(value)).replace(chr(10), "<br/>")}</td>'


def _table(headers: tuple[str, ...], rows: list[list[str]]) -> str:
    header = "".join(f'<th style="background:#1F4E79;color:#FFFFFF;text-align:center;border:1px solid #D9E2F3;padding:6px 8px">{escape(label)}</th>' for label in headers)
    return '<div class="weekly-weather-report"><table><thead><tr>' + header + '</tr></thead><tbody>' + "".join('<tr>' + "".join(row) + '</tr>' for row in rows) + '</tbody></table></div>'


def _card_table(rows: list[list[str]]) -> str:
    return '<div class="weekly-weather-report"><table><tbody>' + "".join('<tr>' + "".join(row) + '</tr>' for row in rows) + '</tbody></table></div>'


def _wind(window: dict[str, Any]) -> str:
    if window["wind_min"] is None:
        return "证据不足"
    direction = "转".join(window["directions"]) or "风向未提供"
    lo, hi = _num(window["wind_min"]), _num(window["wind_max"])
    suffix = "（部分覆盖）" if not window["complete"] else ""
    return f"{direction} {lo}{('～'+hi) if lo != hi else ''}m/s{suffix}"


def _risk(day: dict[str, Any], periods: list[dict[str, Any]]) -> tuple[str, str | None]:
    start = datetime.combine(date.fromisoformat(day["date"]), time.min)
    end = start + timedelta(days=1)
    supported = [item for item in periods if datetime.fromisoformat(item["start"]) < end
                 and datetime.fromisoformat(item["end"]) >= start]
    if any(item["level"] == "high" for item in supported): return "连续弱风扩散风险：高", "高"
    if supported: return "连续弱风扩散关注：中", "中"
    if day["weak_wind_times"]: return "单时次弱风关注（持续风险证据不足）", None
    if day["worst_grade"] is None: return "证据不足", None
    return "暂未识别明显气象风险", None


def _short(value: Any, limit: int = 120) -> str:
    result = _text(value, "")
    if not result or len(result) > limit or "\n" in result:
        raise ValueError(f"Agent分析须为1—{limit}字短句")
    return result


def validate_agent_text(facts: dict[str, Any], agent_text: dict[str, Any]) -> None:
    _short(agent_text.get("overview"), 80)
    _short(agent_text.get("outlook_trend"), 80)
    daily = agent_text.get("daily")
    if not isinstance(daily, dict) or set(daily) != {day["date"] for day in facts["days"]}:
        raise ValueError("Agent逐日分析必须准确覆盖7个日期")
    for fields in daily.values():
        if not isinstance(fields, dict): raise ValueError("逐日分析格式错误")
        for field in ("situation", "pm25", "o3"):
            _short(fields.get(field), 60)
    outlook = agent_text.get("outlook")
    if not isinstance(outlook, dict) or set(outlook) != {day["date"] for day in facts["outlook"]}:
        raise ValueError("Agent中期展望必须准确覆盖8个日期")
    for value in outlook.values(): _short(value, 60)
    phases = agent_text.get("phases", [])
    if not isinstance(phases, list) or len(phases) > 3:
        raise ValueError("天气阶段须为不超过3条的列表")
    for phase in phases: _short(phase, 60)


def build_qmd(facts: dict[str, Any], agent_text: dict[str, Any], chart_name: str | None) -> str:
    validate_agent_text(facts, agent_text)
    d = date.fromisoformat(facts["start_date"])
    lines = ["---", "preserve-template-structure: true", "lang: zh-CN",
             "format:", "  html:", "    toc: false", "    number-sections: false",
             "  docx:", "    toc: false", "    number-sections: false", "---", "",
             CSS, "", "# 许昌市未来7天-15天", "# 污染扩散条件与空气质量分析报告",
             f"({d.year}年{d.month}月{d.day}日)", "", f"## {HEADINGS[0]}", "",
             _short(agent_text["overview"], 80), ""]
    aq_rows = []
    for day in facts["days"]:
        aqi = f"{_num(day['aqi_min'])}～{_num(day['aqi_max'])}" if day["aqi_min"] is not None and day["aqi_max"] is not None else "未提供"
        temp = f"{_num(day['temperature_min'])}～{_num(day['temperature_max'])}℃" if day["temperature_min"] is not None else "温度未提供"
        aq_rows.append([_td(day["label"]), _td(aqi), _td(day["aqi_grade"]), _td(day["primary_pollutant"]),
                        _td(day["diffusion_sequence"], day["worst_grade"]), _td(f"{day['weather']}，{temp}")])
    aq_notes = [note for note in facts["warnings"] if "空气质量预报" in note]
    aq_note = "空气质量预报数据来源于中国环境监测总站的“空气质量发布”App" + ("；" + "；".join(aq_notes) if aq_notes else "") + "。"
    lines.extend([_table(HEADERS[0], aq_rows), "", aq_note, "",
                  f"## {HEADINGS[1]}", "", f"### {HEADINGS[2]}", ""])
    dates = [f"{date.fromisoformat(day['date']).month}/{date.fromisoformat(day['date']).day}" for day in facts["days"]]
    slots = ("02~08时", "08~14时", "14~20时", "20~02时")
    matrix_rows = []
    for slot in slots:
        cells = [_td(slot.replace("~", "～"))]
        for day in facts["matrix"]:
            data = day["slots"][slot]
            suffix = "（部分覆盖）" if data["sample_count"] and not data["complete"] else ""
            cells.append(_td(data["grade"]+suffix, data["worst_grade"]))
        matrix_rows.append(cells)
    lines.extend([_table(("时段", *dates), matrix_rows), "", LEGEND, "", f"### {HEADINGS[3]}", ""])
    detail_rows = []
    for day in facts["days"]:
        content = agent_text["daily"][day["date"]]
        temp = f"{day['weather']} / {_num(day['temperature_min'])}～{_num(day['temperature_max'])}℃" if day["temperature_min"] is not None else f"{day['weather']} / 温度未提供"
        highest = day["highest_night_humidity"]
        highest_text = f"{_num(highest['value'])}%（{str(highest['time'])[5:16]}）" if highest else "证据不足"
        weak = [str(value)[5:16] for value in day["weak_wind_times"]]
        weak_text = "、".join(weak[:4]) + ("等时次弱风" if len(weak) > 4 else "弱风") if weak else "暂未识别"
        detail_rows.append([_td(day["label"]), _td(temp), _td(_wind(day["morning"])), _td(_wind(day["afternoon"])),
                            _td(_wind(day["night"])), _td(highest_text), _td(day["diffusion_sequence"], day["worst_grade"]),
                            _td(content["pm25"]), _td(content["o3"]), _td(weak_text)])
    lines.extend([_table(HEADERS[2], detail_rows), "",
                  "上午08—14时、午后14—20时、夜间20时—次日08时；最高湿取同一夜间窗口。",
                  "温度范围为3小时采样点范围，并非官方最高/最低温；末日夜间可能部分覆盖" +
                  ("；" + "；".join(note for note in facts["warnings"] if "NMC" in note) if any("NMC" in note for note in facts["warnings"]) else "") + "。", "",
                  f"### {HEADINGS[4]}", ""])
    if chart_name:
        chart_caption = "图：3小时预报时次；缺测处断线"
        if facts["risk_periods"]:
            chart_caption += "，底色标识有连续时次支持的弱风扩散关注"
        chart_caption += "。"
        lines.extend([f"![未来7天气象小时变化](assets/charts/{chart_name})", "",
                      chart_caption, ""])
    else:
        lines.extend(["NMC气象预报缺失，无法生成七日连续气象图。", ""])
    lines.extend([*agent_text.get("phases", []), "", f"### {HEADINGS[5]}", ""])
    cards = []
    for day in facts["days"]:
        parsed = date.fromisoformat(day["date"])
        content = agent_text["daily"][day["date"]]
        mean = _num(day["wind_mean"], "m/s") if day["wind_mean_complete"] else "证据不足" + (f"（已覆盖时次均值{_num(day['wind_mean'], 'm/s')}）" if day["wind_mean"] is not None else "")
        grade_text, risk = _risk(day, facts["risk_periods"])
        direction = "转".join(day["wind_directions"]) or "风向未提供"
        wind_range = f"{_num(day['wind_min'])}～{_num(day['wind_max'])}m/s" if day["wind_min"] is not None else "风速未提供"
        header = f"{parsed.month}月{parsed.day}日（周{WEEKDAYS[parsed.weekday()]}） {day['weather']} | {_num(day['temperature_min'])}～{_num(day['temperature_max'])}℃ | {direction} {wind_range}"
        body = (f"{header}\n扩散条件：{day['diffusion_sequence']}；日均风速：{mean}\n"
                f"形势分析：{content['situation']}\nPM2.5：{content['pm25']}\nO₃：{content['o3']}\n风险评级：{grade_text}")
        cards.append([_td(body, risk=risk)])
    lines.extend([_card_table(cards), "", LEGEND, "", f"## {HEADINGS[6]}", ""])
    key_rows = []
    for row in facts["keypoints"]:
        when = str(row["forecast_time"])[5:16]
        key_rows.append([_td(when), _td(row.get("weather_text")), _td(_num(row.get("temperature"), "℃")),
                         _td(row.get("wind_direction")), _td(_num(row.get("wind_speed"), "m/s")),
                         _td(_num(row.get("humidity"), "%")), _td(_num(row.get("pressure"), "hPa")),
                         _td(row["diffusion_grade"], row["diffusion_grade"])])
    lines.extend([_table(HEADERS[3], key_rows), "", LEGEND, "", f"## {HEADINGS[7]}", ""])
    outlook_rows = []
    for row in facts["outlook"]:
        direction = "转".join(dict.fromkeys(filter(None, (row.get("wind_direction_day"), row.get("wind_direction_night"))))) or "未提供"
        note = agent_text["outlook"][row["date"]] if row.get("fetched_at") else "当日预报未提供"
        outlook_rows.append([_td(row["label"]), _td(row.get("weather_text")), _td(_num(row.get("temp_max"), "℃")),
                             _td(_num(row.get("temp_min"), "℃")), _td(direction), _td(row.get("wind_force")),
                             _td("未提供"), _td(note)])
    outlook_notes = [note for note in facts["warnings"] if "第8—15天" in note]
    trend = _short(agent_text["outlook_trend"], 80).rstrip("。")
    lines.extend([_table(HEADERS[4], outlook_rows), "", trend + "；午后定量风速未提供，日尺度展望需滚动更新" +
                  ("；" + "；".join(outlook_notes) if outlook_notes else "") + "。", ""])
    return "\n".join(lines)


class _TableReader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.tables: list[list[list[str]]] = []; self.row: list[str] | None = None; self.cell: list[str] | None = None
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table": self.tables.append([])
        elif tag == "tr" and self.tables: self.row = []
        elif tag in {"td", "th"} and self.row is not None: self.cell = []
    def handle_data(self, data: str) -> None:
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell)); self.cell = None
        elif tag == "tr" and self.row is not None and self.tables:
            self.tables[-1].append(self.row); self.row = None


def validate_qmd_structure(qmd: str, *, has_chart: bool) -> dict[str, Any]:
    headings = re.findall(r"^#{2,3} (.+)$", qmd, re.MULTILINE)
    if tuple(headings) != HEADINGS: raise ValueError("报告章节或小节与Skill模板不一致")
    reader = _TableReader(); reader.feed(qmd)
    if len(reader.tables) != 6: raise ValueError("报告必须包含6张固定表格")
    expected_headers = (HEADERS[0], None, HEADERS[2], None, HEADERS[3], HEADERS[4])
    expected_rows = (7, 4, 7, 7, None, 8)
    for index, (table, headers, count) in enumerate(zip(reader.tables, expected_headers, expected_rows, strict=True)):
        if headers is not None and tuple(table[0]) != headers: raise ValueError(f"第{index+1}张表表头不符合模板")
        if count is not None and len(table)-(0 if index == 3 else 1) != count: raise ValueError(f"第{index+1}张表行数不符合模板")
    if reader.tables[1][0][0] != "时段" or len(reader.tables[1][0]) != 8:
        raise ValueError("扩散矩阵表头不符合模板")
    if [row[0] for row in reader.tables[1][1:]] != ["02～08时", "08～14时", "14～20时", "20～02时"]:
        raise ValueError("扩散矩阵时段不符合模板")
    if qmd.count("![未来7天气象小时变化]") != (1 if has_chart else 0):
        raise ValueError("七日连续气象图数量错误")
    for card in reader.tables[3]:
        if not all(label in card[0] for label in ("扩散条件：", "日均风速：", "形势分析：", "PM2.5：", "O₃：", "风险评级：")):
            raise ValueError("逐日卡片缺少固定字段")
    return {"headings": len(headings), "tables": len(reader.tables), "chart_count": int(has_chart),
            "day_rows": 7, "outlook_rows": 8}


def write_qmd_report_from_evidence(manifest_path: str, agent_text: dict[str, Any], output_path: str, execution_id: str) -> dict[str, Any]:
    manifest = json.loads(resolve_agent_path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA: raise ValueError("天气证据包版本不匹配")
    facts = json.loads(resolve_agent_path(manifest["facts_path"]).read_text(encoding="utf-8"))
    if facts.get("start_date") != manifest.get("start_date") or len(facts.get("days", [])) != 7:
        raise ValueError("天气证据包日期或覆盖结构错误")
    chart = resolve_agent_path(manifest["chart_path"]) if manifest.get("chart_path") else None
    if chart and not chart.is_file(): raise FileNotFoundError(chart)
    qmd = build_qmd(facts, agent_text, chart.name if chart else None)
    validation = validate_qmd_structure(qmd, has_chart=chart is not None)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(qmd, encoding="utf-8")
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", execution_id)
    if not safe_id: raise ValueError("execution_id不能为空")
    return {"report_id": f"xuchang_weather_{safe_id}", "source_qmd_path": str(output),
            "source_qmd_name": output.name,
            "assets": [{"path": manifest["chart_path"], "type": "image", "name": chart.name}] if chart else [],
            "validation": validation, "warnings": facts["warnings"]}
