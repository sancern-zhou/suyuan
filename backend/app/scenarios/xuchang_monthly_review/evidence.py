"""①月度特征分析证据包组装的纯函数（可单测，不做 IO）。

月度口径说明（2026-11 定版）：
- 当月（上月）城市对比：优先官方 ProvinceMonthReport（Level=city,
  Scope=month，含 *_YoY 官方同比变化率）；官方未发布时回退 SsfbCityDay
  日值算术平均（实时参考口径，报告必须注明非官方定版）。
- 去年同期：官方 YoY 列（当ProvinceMonth 可用时）；去年同期绝对值仅当
  官方月报覆盖该期才有（目前 2025-12 起），未覆盖如实说明。
- 排名：省内排名由浓度值直接排序（确定性）；168 城全国排名只引用
  Rank168CityMonthly 官方逐月发布（有滞后，未发布则注明待发布）。
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from typing import Any

from app.scenarios.xuchang_monthly_review.constants import MONTH_FACTORS


def previous_month(today: date) -> tuple[int, int]:
    """上月的 (年, 月)。"""
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """[月初, 下月初) 边界。"""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def same_month_last_year(year: int, month: int) -> tuple[int, int]:
    return year - 1, month


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def aggregate_city_month(
    daily_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """SsfbCityDay 月内日值 → 18 城六参数月均（算术平均，实时参考口径）。

    daily_rows: [{city, pm25, pm10, so2, no2, co, o3}, ...]
    返回按 PM2.5 降序的行列表：{city, factors: {PM25: {...}}, valid_days}
    """
    per_city: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily_rows:
        city = str(row.get("city") or "").strip()
        if not city:
            continue
        per_city[city].append(row)

    field_map = {
        "PM25": "pm25", "PM10": "pm10", "O3": "o3",
        "NO2": "no2", "SO2": "so2", "CO": "co",
    }
    results: list[dict[str, Any]] = []
    for city, rows in per_city.items():
        factors: dict[str, Any] = {}
        for factor, field in field_map.items():
            values = [v for r in rows if (v := _number(r.get(field))) is not None]
            factors[factor] = {
                "mean": round(sum(values) / len(values), 1) if values else None,
                "valid_days": len(values),
            }
        results.append({
            "city": city,
            "factors": factors,
            "valid_days": len(rows),
        })
    results.sort(
        key=lambda item: (
            item["factors"]["PM25"]["mean"] if item["factors"]["PM25"]["mean"] is not None else -1
        ),
        reverse=True,
    )
    for index, item in enumerate(results, start=1):
        item["pm25_rank"] = index
    return results


def normalize_province_month_rows(
    records: list[dict[str, Any]], data_month: str
) -> dict[str, Any]:
    """ProvinceMonthReport 官方行（Level=city, Scope=month）→ 对比结构。

    返回 {status, data_month, caliber, rows: [{city, factors, yoy, composite_index,
    good_days, heavy_days}], xuchang: {...}}
    """
    rows: list[dict[str, Any]] = []
    for record in records:
        level = str(record.get("Level") or record.get("level") or "").strip()
        scope = str(record.get("Scope") or record.get("scope") or "").strip()
        if level != "city" or scope != "month":
            continue
        month_value = str(record.get("DataMonth") or record.get("dataMonth") or "")[:10]
        if month_value[:7] != data_month[:7]:
            continue
        city = str(record.get("City") or record.get("city") or "").strip()
        if not city:
            continue
        factors: dict[str, Any] = {}
        yoy: dict[str, Any] = {}
        for factor in MONTH_FACTORS:
            factors[factor] = _number(record.get(factor))
            yoy[factor] = _signed_number(record.get(f"{factor}_YoY"))
        entry: dict[str, Any] = {
            "city": city,
            "factors": factors,
            "yoy": yoy,
            "composite_index": _number(record.get("CompositeIndex")),
            "composite_index_yoy": _signed_number(record.get("CompositeIndex_YoY")),
            "good_days": _number(record.get("GoodDays")),
            "heavy_days": _number(record.get("HeavyDays")),
        }
        rows.append(entry)

    rows.sort(key=lambda item: item["factors"]["PM25"] if item["factors"]["PM25"] is not None else -1,
              reverse=True)
    for index, item in enumerate(rows, start=1):
        item["pm25_rank"] = index
    xuchang = next(
        (item for item in rows if "许昌" in item["city"]),
        None,
    )
    return {
        "status": "available" if rows else "not_published",
        "data_month": data_month,
        "caliber": "official_month_report",
        "city_count": len(rows),
        "rows": rows,
        "xuchang": xuchang,
    }


def _signed_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_rank168_section(
    records: list[dict[str, Any]], data_month: str
) -> dict[str, Any]:
    """Rank168CityMonthly（PeriodType=monthly）→ 当月行 + 最新可得月份。"""
    target_rows: list[dict[str, Any]] = []
    latest_rows: list[dict[str, Any]] = []
    latest_month = ""
    for record in records:
        period_type = str(record.get("PeriodType") or "").strip()
        if period_type != "monthly":
            continue
        month_value = str(record.get("DataMonth") or "")[:10]
        city = str(record.get("City") or "").strip()
        if not city:
            continue
        entry = {
            "city": city,
            "data_month": month_value,
            "composite_index_rank": _int_or_none(record.get("CompositeIndexRank")),
            "pm25_rank": _int_or_none(record.get("Pm25Rank")),
            "pm25": _number(record.get("Pm25")),
            "composite_index": _number(record.get("CompositeIndex")),
        }
        if month_value[:7] == data_month[:7]:
            target_rows.append(entry)
        if month_value >= latest_month:
            if month_value > latest_month:
                latest_month = month_value
                latest_rows = []
            latest_rows.append(entry)

    def _find(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        return next((item for item in rows if "许昌" in item["city"]), None)

    xuchang_target = _find(target_rows)
    xuchang_latest = _find(latest_rows)
    return {
        "status": "available" if target_rows else ("latest_only" if latest_rows else "unavailable"),
        "data_month": data_month,
        "target_month_rows": len(target_rows),
        "latest_available_month": latest_month[:7] or None,
        "xuchang_target": xuchang_target,
        "xuchang_latest": xuchang_latest,
        "note": (
            "168城排名为生态环境部逐月定版数据，有发布滞后"
            if not target_rows and latest_rows
            else ""
        ),
    }


def _int_or_none(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def aggregate_weather_month(
    observed_rows: list[dict[str, Any]], era5_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """月内逐小时观测 → 描述性气象统计（区分观测事实与扩散条件参考）。"""
    def _stats(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
        values = []
        for row in rows:
            try:
                value = float(row.get(field))
            except (TypeError, ValueError):
                continue
            values.append(value)
        if not values:
            return None
        return {
            "valid_hours": len(values),
            "mean": round(sum(values) / len(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }

    def _sum(rows: list[dict[str, Any]], field: str) -> float | None:
        values = []
        for row in rows:
            try:
                value = float(row.get(field))
            except (TypeError, ValueError):
                continue
            values.append(value)
        return round(sum(values), 1) if values else None

    summary: dict[str, Any] = {
        "observed_hours": len(observed_rows),
        "temperature": _stats(observed_rows, "temperature_2m"),
        "relative_humidity": _stats(observed_rows, "relative_humidity_2m"),
        "wind_speed": _stats(observed_rows, "wind_speed_10m_ms"),
        "precipitation_sum": _sum(observed_rows, "precipitation"),
        "boundary_layer_height": _stats(era5_rows, "boundary_layer_height"),
        "caliber": "描述性统计，不构成污染成因判断",
    }
    return summary


def summarize_month_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """月内站点告警 episode → 频率分布（按站点/污染物/规则类型/日期）。"""
    by_station: dict[str, int] = defaultdict(int)
    by_pollutant: dict[str, int] = defaultdict(int)
    by_rule: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    peak_value = None
    peak_episode: dict[str, Any] | None = None
    for episode in episodes:
        station = str(episode.get("station_name") or episode.get("station_id") or "未知站点")
        pollutant = str(episode.get("target_pollutant") or "未知因子")
        rule = str(episode.get("alert_type") or episode.get("rule") or "未知规则")
        by_station[station] += 1
        by_pollutant[pollutant] += 1
        by_rule[rule] += 1
        started = str(episode.get("started_at") or "")[:10]
        if started:
            by_day[started] += 1
        value = _number(episode.get("peak_station_value"))
        if value is not None and (peak_value is None or value > peak_value):
            peak_value = value
            peak_episode = {
                "station": station,
                "pollutant": pollutant,
                "peak_value": value,
                "started_at": str(episode.get("started_at") or ""),
            }

    def _top(counter: dict[str, int], limit: int = 8) -> list[dict[str, Any]]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        ]

    return {
        "episode_count": len(episodes),
        "by_station": _top(by_station),
        "by_pollutant": _top(by_pollutant),
        "by_rule": _top(by_rule),
        "by_day": [{"date": day, "count": count} for day, count in sorted(by_day.items())],
        "peak_episode": peak_episode,
        "station_count": len(by_station),
    }


def summarize_inventory(dataset: list[dict[str, Any]]) -> dict[str, Any]:
    """企业排放源静态清单背景（年度静态数据，非当月实际排放）。

    dataset 行结构来自 xuchang_upwind_permit_sources/inventory_asset.py：
    inventory_sectors 为扇区名列表，inventory_emissions 为
    emission_<factor> → 年排放量（吨）。
    """
    by_district: dict[str, int] = defaultdict(int)
    by_sector: dict[str, int] = defaultdict(int)
    emission_totals: dict[str, float] = defaultdict(float)
    enterprise_count = 0
    for row in dataset:
        name = str(row.get("enterprise_name") or "").strip()
        if not name:
            continue
        enterprise_count += 1
        district = str(row.get("district") or "").strip()
        if district:
            by_district[district] += 1
        sectors = row.get("inventory_sectors") or []
        if isinstance(sectors, (list, tuple, set)):
            for sector_name in sectors:
                text = str(sector_name).strip()
                if text:
                    by_sector[text] += 1
        emissions = row.get("inventory_emissions") or {}
        if isinstance(emissions, dict):
            for field, value in emissions.items():
                number = _number(value)
                if number:
                    emission_totals[str(field)] += number

    def _top(counter: dict[str, int], limit: int) -> list[dict[str, Any]]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        ]

    return {
        "status": "available" if enterprise_count else "unavailable",
        "enterprise_count": enterprise_count,
        "caliber": "年度静态排放清单（背景参考），不代表当月实际排放，不认定当月污染责任",
        "top_districts": _top(by_district, 6),
        "top_sectors": _top(by_sector, 6),
        "annual_emission_totals": {
            key: round(value, 1)
            for key, value in emission_totals.items()
            if key in ("emission_pm25", "emission_pm10", "emission_so2", "emission_nox", "emission_vocs")
        },
    }


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def format_month_label(year: int, month: int) -> str:
    return f"{year}年{month}月"
