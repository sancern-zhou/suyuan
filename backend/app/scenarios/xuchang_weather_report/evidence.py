"""Build a reproducible weather-report snapshot from the three approved sources."""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pyodbc

from app.tools.query.query_xcai_city_history.sql_client import get_sql_server_client
from app.tools.visualization.create_business_chart.domain.weather_timeseries import render_weather_timeseries
from app.utils.path_config import format_agent_path, get_data_registry
from .constants import EVENT_TYPE, SCHEMA, WEEKDAYS

TZ = ZoneInfo("Asia/Shanghai")
GRADES = ("好", "一般", "较差", "差")


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _rows(cursor: Any) -> list[dict[str, Any]]:
    names = [item[0] for item in cursor.description]
    return [{name: _iso(value) if isinstance(value, (date, datetime)) else value
             for name, value in zip(names, row, strict=True)} for row in cursor.fetchall()]


def load_source_rows(start: date) -> dict[str, list[dict[str, Any]]]:
    """Query only the prescribed source fields and never mix publication batches."""
    d0 = datetime.combine(start, time.min)
    d7, d15 = d0 + timedelta(days=7), d0 + timedelta(days=15)
    connection = pyodbc.connect(get_sql_server_client().connection_string, timeout=30)
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT forecast_time, weather_text, temperature, humidity, pressure,
                   wind_direction, wind_direction_degrees, wind_speed,
                   precipitation_probability, precipitation_text, publish_time, fetched_at
            FROM dbo.XuchangNmcHourlyWeatherForecast
            WHERE city_name=N'许昌市' AND forecast_time >= ? AND forecast_time < ?
              AND publish_time=(SELECT MAX(publish_time) FROM dbo.XuchangNmcHourlyWeatherForecast
                                WHERE city_name=N'许昌市' AND forecast_time >= ? AND forecast_time < ?)
            ORDER BY forecast_time
        """, d0, d7, d0, d7)
        nmc = _rows(cursor)
        cursor.execute("""
            SELECT TimePoint, MinAqi, MaxAqi, MaxPollution, UpdateDate, UpdateTime
            FROM dbo.WeatherForecast7Day
            WHERE cityname=N'许昌市' AND TimePoint >= ? AND TimePoint < ?
              AND UpdateDate=(SELECT MAX(UpdateDate) FROM dbo.WeatherForecast7Day
                              WHERE cityname=N'许昌市' AND TimePoint >= ? AND TimePoint < ?)
            ORDER BY TimePoint
        """, d0, d7, d0, d7)
        aq = _rows(cursor)
        cursor.execute("""
            SELECT forecast_date, weather_text, temp_max, temp_min,
                   wind_direction_day, wind_direction_night, wind_force, fetched_at
            FROM dbo.XuchangWeatherComDailyForecast
            WHERE city_code='101180401' AND forecast_date >= ? AND forecast_date < ?
            ORDER BY forecast_date
        """, d7.date(), d15.date())
        outlook = _rows(cursor)
        return {"nmc": nmc, "aq": aq, "outlook": outlook}
    finally:
        connection.close()


def wind_grade(speed: Any) -> str | None:
    value = _number(speed)
    if value is None or value < 0:
        return None
    return "好" if value >= 5 else "一般" if value >= 2 else "较差" if value >= 1.5 else "差"


def _changes(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and (not result or value != result[-1]):
            result.append(value)
    return result


def aqi_grade(low: Any, high: Any) -> str:
    lower, upper = _number(low), _number(high)
    if lower is None or upper is None or lower < 0 or upper < lower:
        return "未提供"
    bands = ((0, 50, "优"), (51, 100, "良"), (101, 150, "轻度污染"),
             (151, 200, "中度污染"), (201, 300, "重度污染"),
             (301, float("inf"), "严重污染"))
    grades = [label for minimum, maximum, label in bands if lower <= maximum and upper >= minimum]
    return "～".join(grades) if grades else "未提供"


def _dt(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(row["forecast_time"]))


def _window(rows: list[dict[str, Any]], start: datetime, end: datetime, phase: int | None) -> dict[str, Any]:
    selected = [row for row in rows if start <= _dt(row) < end]
    speeds = [_number(row.get("wind_speed")) for row in selected]
    speeds = [value for value in speeds if value is not None and value >= 0]
    grades = [wind_grade(row.get("wind_speed")) for row in selected]
    ordered = _changes(grades)
    expected = []
    if phase is not None:
        cursor = start.replace(minute=0, second=0, microsecond=0)
        while cursor < end:
            if cursor.hour % 3 == phase:
                expected.append(cursor)
            cursor += timedelta(hours=1)
    observed = {_dt(row) for row in selected if wind_grade(row.get("wind_speed"))}
    complete = bool(expected) and all(point in observed for point in expected)
    return {
        "grade": "→".join(ordered) if ordered else "证据不足",
        "worst_grade": max(ordered, key=GRADES.index) if ordered else None,
        "complete": complete, "sample_count": len(selected),
        "wind_min": min(speeds) if speeds else None,
        "wind_max": max(speeds) if speeds else None,
        "directions": list(dict.fromkeys(str(row["wind_direction"]) for row in selected if row.get("wind_direction"))),
    }


def _risk_periods(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only adjacent weak-wind forecast points support a shaded interval."""
    points = [(row, wind_grade(row.get("wind_speed"))) for row in rows]
    periods: list[dict[str, Any]] = []
    run: list[dict[str, Any]] = []
    def flush() -> None:
        if len(run) < 2:
            return
        worst = max((wind_grade(item.get("wind_speed")) for item in run), key=GRADES.index)
        level = "high" if worst == "差" else "medium"
        periods.append({
            "start": _dt(run[0]).strftime("%Y-%m-%d %H:%M:%S"),
            "end": _dt(run[-1]).strftime("%Y-%m-%d %H:%M:%S"),
            "name": "弱风扩散关注", "level": level,
            "color": "#FFC7CE" if level == "high" else "#FCE4D6", "alpha": 0.2,
        })
    for row, grade in points:
        if grade in {"差", "较差"} and (not run or _dt(row) - _dt(run[-1]) == timedelta(hours=3)):
            run.append(row)
        else:
            flush(); run = [row] if grade in {"差", "较差"} else []
    flush()
    return periods


def build_evidence(start: date, sources: dict[str, list[dict[str, Any]]], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(TZ)
    nmc = sorted((row for row in sources.get("nmc", []) if row.get("forecast_time")), key=_dt)
    phase = _dt(nmc[0]).hour % 3 if nmc else None
    aq_rows = sources.get("aq", [])
    aq_batch = max((str(row.get("UpdateDate") or "") for row in aq_rows), default="")
    aq = {str(row["TimePoint"])[:10]: row for row in aq_rows if str(row.get("UpdateDate") or "") == aq_batch}
    outlook_rows = sources.get("outlook", [])
    outlook = {str(row["forecast_date"])[:10]: row for row in outlook_rows
               if str(row.get("fetched_at") or "")[:10] == start.isoformat()}
    days: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    keypoints: list[dict[str, Any]] = []
    spans = ((2, 8, "02~08时"), (8, 14, "08~14时"), (14, 20, "14~20时"), (20, 26, "20~02时"))
    for offset in range(7):
        day = start + timedelta(days=offset)
        begin = datetime.combine(day, time.min)
        end = begin + timedelta(days=1)
        daily = [row for row in nmc if begin <= _dt(row) < end]
        slots = {label: _window(nmc, begin + timedelta(hours=low), begin + timedelta(hours=high), phase)
                 for low, high, label in spans}
        matrix.append({"date": day.isoformat(), "slots": slots})
        morning = _window(nmc, begin + timedelta(hours=8), begin + timedelta(hours=14), phase)
        afternoon = _window(nmc, begin + timedelta(hours=14), begin + timedelta(hours=20), phase)
        night_rows = [row for row in nmc if begin + timedelta(hours=20) <= _dt(row) < begin + timedelta(hours=32)]
        night = _window(nmc, begin + timedelta(hours=20), begin + timedelta(hours=32), phase)
        humidity = [(row, _number(row.get("humidity"))) for row in night_rows]
        humidity = [(row, value) for row, value in humidity if value is not None]
        peak = max(humidity, key=lambda item: item[1]) if humidity else None
        speeds = [_number(row.get("wind_speed")) for row in daily]
        speeds = [value for value in speeds if value is not None and value >= 0]
        wind_directions = list(dict.fromkeys(str(row["wind_direction"]) for row in daily if row.get("wind_direction")))
        expected = {begin + timedelta(hours=hour) for hour in range(24) if phase is not None and hour % 3 == phase}
        observed = {_dt(row) for row in daily if wind_grade(row.get("wind_speed"))}
        grade_sequence = _changes([wind_grade(row.get("wind_speed")) for row in daily])
        aq_row = aq.get(day.isoformat(), {})
        temperatures = [_number(row.get("temperature")) for row in daily]
        temperatures = [value for value in temperatures if value is not None]
        highlight = []
        for key in ("wind_speed", "humidity"):
            candidates = [(row, _number(row.get(key))) for row in daily]
            candidates = [(row, value) for row, value in candidates if value is not None]
            if candidates:
                row, _ = (min if key == "wind_speed" else max)(candidates, key=lambda item: item[1])
                if row not in highlight:
                    highlight.append(row)
        keypoints.extend({**row, "diffusion_grade": wind_grade(row.get("wind_speed")) or "证据不足"}
                         for row in sorted(highlight[:3], key=_dt))
        days.append({
            "date": day.isoformat(), "label": f"{day.month}/{day.day} 周{WEEKDAYS[day.weekday()]}",
            "weather": "、".join(dict.fromkeys(str(row["weather_text"]) for row in daily if row.get("weather_text"))) or "未提供",
            "temperature_min": min(temperatures) if temperatures else None,
            "temperature_max": max(temperatures) if temperatures else None,
            "wind_mean": round(sum(speeds)/len(speeds), 2) if speeds else None,
            "wind_min": min(speeds) if speeds else None,
            "wind_max": max(speeds) if speeds else None,
            "wind_directions": wind_directions,
            "wind_mean_complete": bool(expected) and expected <= observed,
            "sample_count": len(daily), "wind_sample_count": len(speeds),
            "diffusion_sequence": "→".join(grade_sequence) if grade_sequence else "证据不足",
            "worst_grade": max(grade_sequence, key=GRADES.index) if grade_sequence else None,
            "morning": morning, "afternoon": afternoon, "night": night,
            "highest_night_humidity": {"value": peak[1], "time": peak[0]["forecast_time"]} if peak else None,
            "aqi_min": aq_row.get("MinAqi"), "aqi_max": aq_row.get("MaxAqi"),
            "aqi_grade": aqi_grade(aq_row.get("MinAqi"), aq_row.get("MaxAqi")),
            "primary_pollutant": aq_row.get("MaxPollution") or "未提供",
            "weak_wind_times": [row["forecast_time"] for row in daily if wind_grade(row.get("wind_speed")) in {"较差", "差"}],
        })
    outlook_days = [{"date": (start+timedelta(days=i)).isoformat(),
                     "label": f"{(start+timedelta(days=i)).month}/{(start+timedelta(days=i)).day}",
                     **outlook.get((start+timedelta(days=i)).isoformat(), {})} for i in range(7, 15)]
    warnings = []
    if not nmc: warnings.append("前7天NMC气象预报缺失")
    elif str(nmc[0].get("publish_time") or "")[:10] < start.isoformat(): warnings.append("NMC气象预报发布批次早于执行日")
    if nmc and len({_dt(row).date() for row in nmc}) < 7:
        warnings.append(f"NMC气象预报仅覆盖{len({_dt(row).date() for row in nmc})}/7天")
    if not aq_batch: warnings.append("空气质量预报无可用批次，AQI字段留空")
    elif aq_batch != start.isoformat(): warnings.append(f"空气质量预报无执行日发布批次，使用最近批次（{aq_batch}）")
    if len(aq) < 7: warnings.append(f"空气质量预报仅覆盖{len(aq)}/7天")
    if len(outlook) < 8: warnings.append(f"第8—15天当日更新预报仅覆盖{len(outlook)}/8天")
    return {"schema_version": SCHEMA, "start_date": start.isoformat(), "generated_at": now.isoformat(),
            "source_batches": {"nmc_publish_time": nmc[0].get("publish_time") if nmc else None,
                               "aq_update_date": aq_batch or None,
                               "outlook_dates_current": len(outlook)},
            "warnings": warnings, "days": days, "matrix": matrix, "keypoints": keypoints,
            "outlook": outlook_days, "risk_periods": _risk_periods(nmc), "nmc_records": nmc}


def write_evidence_package(start: date, sources: dict[str, list[dict[str, Any]]] | None = None,
                           *, now: datetime | None = None, registry: Path | None = None) -> dict[str, Any]:
    now = now or datetime.now(TZ)
    facts = build_evidence(start, sources if sources is not None else load_source_rows(start), now=now)
    folder = (registry or get_data_registry()) / "xuchang_weather_situation" / f"{start:%Y%m%d}_{uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=False)
    chart_path = folder / "weather_timeseries.png"
    chart_metadata = None
    if facts["nmc_records"]:
        encoded, chart_metadata, _ = render_weather_timeseries(
            title="许昌市未来7天气象小时变化", data={"records": facts["nmc_records"]},
            options={"expected_interval_hours": 3, "line_width": 1.0, "risk_periods": facts["risk_periods"]},
            output_context="word", style_profile="government",
        )
        if chart_metadata.get("valid_point_count") != len(facts["nmc_records"]):
            raise ValueError("气象图有效时次与证据快照不一致")
        chart_path.write_bytes(base64.b64decode(encoded))
    facts["chart_metadata"] = chart_metadata
    facts_path = folder / "facts.json"
    facts_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    brief = {key: facts[key] for key in ("schema_version", "start_date", "source_batches", "warnings", "days", "outlook", "risk_periods")}
    brief["chart_metadata"] = chart_metadata
    brief_path = folder / "report_brief.json"
    brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {"schema_version": SCHEMA, "start_date": start.isoformat(),
                "report_brief_path": format_agent_path(brief_path),
                "facts_path": format_agent_path(facts_path),
                "chart_path": format_agent_path(chart_path) if chart_metadata else None}
    path = folder / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest_path": format_agent_path(path), "start_date": start.isoformat(),
            "nmc_count": len(facts["nmc_records"]), "aq_day_count": sum(day["aqi_grade"] != "未提供" for day in facts["days"]),
            "outlook_day_count": sum(bool(day.get("fetched_at")) for day in facts["outlook"]),
            "warnings": facts["warnings"]}
