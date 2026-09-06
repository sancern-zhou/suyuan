"""Export Chengdu hourly station observations with ERA5 supplements to Excel.

The Suncere endpoint returns nationwide rows, so each response is filtered by
``cityName == '成都市'`` before being merged with station-level Open-Meteo data.
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.path_config import format_agent_path, resolve_agent_path


OUTPUT = resolve_agent_path("backend/output/chengdu_weather_2026-06-01_07.xlsx")
SUNCERE_URL = "http://data.suncereltd.top:8080/api/WeatherData/GetWeatherStationHour"
SUNCERE_TOKEN = os.environ.get("SUNCERE_WEATHER_TOKEN", "")
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
START = datetime(2026, 6, 1)
END = datetime(2026, 6, 7, 23)


def fetch_suncere_half(day: datetime, start_hour: int) -> list[dict[str, Any]]:
    begin = day.replace(hour=start_hour, minute=0, second=0)
    end = begin + timedelta(hours=11)
    params = {
        "token": SUNCERE_TOKEN,
        "beginTime": begin.strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": end.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for attempt in range(4):
        try:
            response = requests.get(SUNCERE_URL, params=params, timeout=120)
            if response.status_code == 200:
                payload = response.json()
                return [
                    row for row in (payload.get("dataList") or [])
                    if row.get("cityName") == "成都市"
                ]
            if response.status_code not in {413, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"Suncere HTTP {response.status_code}: {response.text[:200]}")
        except (requests.RequestException, ValueError, RuntimeError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    return []


def fetch_open_meteo(station: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    params = {
        "latitude": float(station["stationLat"]),
        "longitude": float(station["stationLng"]),
        "start_date": START.strftime("%Y-%m-%d"),
        "end_date": END.strftime("%Y-%m-%d"),
        "hourly": "cloud_cover,boundary_layer_height",
        "timezone": "Asia/Shanghai",
    }
    for attempt in range(4):
        try:
            response = requests.get(OPEN_METEO_URL, params=params, timeout=120)
            response.raise_for_status()
            payload = response.json()
            hourly = payload.get("hourly") or {}
            times = hourly.get("time") or []
            rows = [
                {
                    "stationCode": station["stationCode"],
                    "timePoint": timestamp,
                    "cloud_cover": values,
                    "boundary_layer_height": pbl,
                }
                for timestamp, values, pbl in zip(
                    times,
                    hourly.get("cloud_cover") or [],
                    hourly.get("boundary_layer_height") or [],
                )
            ]
            return station["stationCode"], rows, response.url
        except (requests.RequestException, ValueError, KeyError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def main() -> None:
    if not SUNCERE_TOKEN:
        raise SystemExit("SUNCERE_WEATHER_TOKEN is required")

    jobs = [(START + timedelta(days=day), hour) for day in range(7) for hour in (0, 12)]
    suncere_rows: list[dict[str, Any]] = []
    # The nationwide Suncere response is large and the service throttles
    # concurrent range requests; keep these requests serial and deterministic.
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = [pool.submit(fetch_suncere_half, day, hour) for day, hour in jobs]
        for future in as_completed(futures):
            suncere_rows.extend(future.result())

    # Keep only the requested local-time window and one row per station/hour.
    observations: dict[tuple[str, str], dict[str, Any]] = {}
    for row in suncere_rows:
        timestamp = str(row.get("timePoint", ""))[:16]
        key = (str(row.get("stationCode", "")), timestamp)
        if key[0] and timestamp and START.strftime("%Y-%m-%dT%H:%M") <= timestamp <= END.strftime("%Y-%m-%dT%H:%M"):
            observations[key] = row

    stations = list({row["stationCode"]: row for row in observations.values()}.values())
    era5_rows: list[dict[str, Any]] = []
    era5_urls: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_open_meteo, station) for station in stations]
        for future in as_completed(futures):
            station_code, rows, source_url = future.result()
            era5_rows.extend(rows)
            era5_urls[station_code] = source_url

    era5_by_key = {(row["stationCode"], row["timePoint"]): row for row in era5_rows}
    output_rows: list[dict[str, Any]] = []
    for (station_code, timestamp), row in sorted(observations.items(), key=lambda item: item[0]):
        supplement = era5_by_key.get((station_code, timestamp), {})
        output_rows.append(
            {
                "观测时间(本地)": timestamp,
                "站点名称": row.get("stationName"),
                "站点编码": station_code,
                "行政区编码": row.get("areaCode"),
                "城市": row.get("cityName"),
                "纬度": pd.to_numeric(row.get("stationLat"), errors="coerce"),
                "经度": pd.to_numeric(row.get("stationLng"), errors="coerce"),
                "气温(°C)": pd.to_numeric(row.get("temperature"), errors="coerce"),
                "相对湿度(%)": pd.to_numeric(row.get("humidity"), errors="coerce"),
                "小时降雨量(mm)": pd.to_numeric(row.get("rain"), errors="coerce"),
                "风向(°)": pd.to_numeric(row.get("windDirection"), errors="coerce"),
                "风向名称": row.get("windDirectionName"),
                "风速(m/s)": pd.to_numeric(row.get("windSpeed"), errors="coerce"),
                "气压(hPa)": pd.to_numeric(row.get("pressure"), errors="coerce"),
                "风力等级": pd.to_numeric(row.get("windLevel"), errors="coerce"),
                "边界层高度(m, ERA5)": supplement.get("boundary_layer_height"),
                "云量(% , ERA5)": supplement.get("cloud_cover"),
            }
        )

    detail = pd.DataFrame(output_rows)
    expected_hours = 7 * 24
    summary = (
        detail.groupby(["站点编码", "站点名称"], dropna=False)
        .agg(
            记录数=("观测时间(本地)", "count"),
            起始时间=("观测时间(本地)", "min"),
            结束时间=("观测时间(本地)", "max"),
            边界层缺测数=("边界层高度(m, ERA5)", lambda s: int(s.isna().sum())),
            云量缺测数=("云量(% , ERA5)", lambda s: int(s.isna().sum())),
        )
        .reset_index()
    )
    summary["应有记录数"] = expected_hours
    summary["Suncere缺测数"] = summary["应有记录数"] - summary["记录数"]
    summary = summary[
        ["站点编码", "站点名称", "应有记录数", "记录数", "Suncere缺测数", "起始时间", "结束时间", "边界层缺测数", "云量缺测数"]
    ].sort_values("站点编码")

    fields = pd.DataFrame(
        [
            ["观测时间(本地)", "Suncere", "接口 timePoint，本次按成都本地时间整理", "ISO 本地时间"],
            ["站点名称/站点编码/行政区编码/城市", "Suncere", "全国站点接口返回后筛选 cityName=成都市", "文本"],
            ["气温、相对湿度、小时降雨量、风向、风速、气压、风力等级", "Suncere", "GetWeatherStationHour", "见列名"],
            ["边界层高度(m, ERA5)", "Open-Meteo ERA5 archive", "按各站点经纬度查询 boundary_layer_height；时区 Asia/Shanghai", "m"],
            ["云量(% , ERA5)", "Open-Meteo ERA5 archive", "按各站点经纬度查询 cloud_cover；总云量", "%"],
            ["年份选择", "处理说明", "文档未指定年份；2024/2025-06-01 00:00 成都无记录，2026 有 14 个站点，故采用 2026-06-01 至 2026-06-07", ""],
        ],
        columns=["字段/事项", "来源", "口径", "单位/备注"],
    )
    source = pd.DataFrame(
        [["Suncere", SUNCERE_URL, "2026-06-01 00:00:00 至 2026-06-07 23:00:00；12小时分段；筛选 cityName=成都市"],
         ["Open-Meteo ERA5", OPEN_METEO_URL, "每个站点一次；hourly=cloud_cover,boundary_layer_height；timezone=Asia/Shanghai"]],
        columns=["数据源", "接口", "请求说明"],
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        detail.to_excel(writer, index=False, sheet_name="逐小时数据")
        summary.to_excel(writer, index=False, sheet_name="站点汇总")
        fields.to_excel(writer, index=False, sheet_name="字段说明")
        source.to_excel(writer, index=False, sheet_name="数据来源")
        for sheet_name, frame in {"逐小时数据": detail, "站点汇总": summary, "字段说明": fields, "数据来源": source}.items():
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for column_cells in ws.columns:
                width = min(max(max(len(str(cell.value or "")) for cell in column_cells) + 2, 10), 32)
                ws.column_dimensions[column_cells[0].column_letter].width = width

    print(f"saved={format_agent_path(OUTPUT)}")
    print(f"rows={len(detail)} stations={detail['站点编码'].nunique() if not detail.empty else 0}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
