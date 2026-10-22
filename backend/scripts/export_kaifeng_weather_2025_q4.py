"""Export Kaifeng hourly Suncere observations with Open-Meteo ERA5 supplements."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT / "backend" / "backend_data_registry" / "datasets" / "kaifeng_weather_2025-10-01_12-31.xlsx"
CHECKPOINT_ROWS = Path("/tmp/kaifeng_suncere_2025_q4_rows.jsonl")
CHECKPOINT_DONE = Path("/tmp/kaifeng_suncere_2025_q4_done.txt")
SUNCERE_URL = "http://data.suncereltd.top:8080/api/WeatherData/GetWeatherStationHour"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
TOKEN = os.environ.get("SUNCERE_WEATHER_TOKEN", "88e9fc972750a21c0017b2248af051e4")
START = datetime(2025, 10, 1)
END = datetime(2025, 12, 31, 23)


def fetch_half(day: datetime, hour: int) -> list[dict[str, Any]]:
    begin = day.replace(hour=hour, minute=0, second=0)
    end = begin + timedelta(hours=11)
    params = {"token": TOKEN, "beginTime": begin.strftime("%Y-%m-%d %H:%M:%S"), "endTime": end.strftime("%Y-%m-%d %H:%M:%S")}
    for attempt in range(5):
        try:
            response = requests.get(SUNCERE_URL, params=params, timeout=180)
            if response.status_code == 200:
                return [row for row in (response.json().get("dataList") or []) if row.get("cityName") == "开封市"]
            if response.status_code not in {413, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"Suncere HTTP {response.status_code}: {response.text[:200]}")
        except (requests.RequestException, ValueError, RuntimeError):
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    return []


def fetch_era5(station: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
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
            response = requests.get(OPEN_METEO_URL, params=params, timeout=180)
            response.raise_for_status()
            hourly = response.json().get("hourly") or {}
            rows = [
                {"stationCode": station["stationCode"], "timePoint": timestamp, "cloud_cover": cloud, "boundary_layer_height": pbl}
                for timestamp, cloud, pbl in zip(hourly.get("time") or [], hourly.get("cloud_cover") or [], hourly.get("boundary_layer_height") or [])
            ]
            return station["stationCode"], rows
        except (requests.RequestException, ValueError, KeyError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def main() -> None:
    if not TOKEN:
        raise SystemExit("SUNCERE_WEATHER_TOKEN is required")
    jobs = [(START + timedelta(days=i), hour) for i in range((END.date() - START.date()).days + 1) for hour in (0, 12)]
    observations: dict[tuple[str, str], dict[str, Any]] = {}
    completed: set[str] = set()
    if CHECKPOINT_ROWS.exists():
        with CHECKPOINT_ROWS.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = __import__("json").loads(line)
                    key = (str(row.get("stationCode", "")), str(row.get("timePoint", ""))[:16])
                    if key[0] and key[1]:
                        observations[key] = row
                except ValueError:
                    continue
    if CHECKPOINT_DONE.exists():
        completed = {line.strip() for line in CHECKPOINT_DONE.read_text(encoding="utf-8").splitlines() if line.strip()}
    pending_jobs = [(day, hour) for day, hour in jobs if f"{day:%Y-%m-%d}T{hour:02d}" not in completed]
    print(f"checkpoint_done={len(completed)} checkpoint_rows={len(observations)} pending={len(pending_jobs)}", flush=True)
    # Keep concurrency low: each nationwide response is several MB and the API throttles bursts.
    with CHECKPOINT_ROWS.open("a", encoding="utf-8") as rows_file, CHECKPOINT_DONE.open("a", encoding="utf-8") as done_file:
      with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch_half, day, hour): (day, hour) for day, hour in pending_jobs}
        for n, future in enumerate(as_completed(futures), 1):
            day, hour = futures[future]
            batch_rows = future.result()
            for row in batch_rows:
                timestamp = str(row.get("timePoint", ""))[:16]
                key = (str(row.get("stationCode", "")), timestamp)
                if key[0] and timestamp:
                    observations[key] = row
                    rows_file.write(__import__("json").dumps(row, ensure_ascii=False) + "\n")
            batch_key = f"{day:%Y-%m-%d}T{hour:02d}"
            done_file.write(batch_key + "\n")
            rows_file.flush()
            done_file.flush()
            completed.add(batch_key)
            if n % 10 == 0 or n == len(futures):
                print(f"suncere_progress={len(completed)}/{len(jobs)} pending_run={n}/{len(futures)} rows={len(observations)}", flush=True)

    stations = list({row["stationCode"]: row for row in observations.values()}.values())
    era5_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch_era5, station) for station in stations]
        for future in as_completed(futures):
            _, rows = future.result()
            era5_by_key.update({(row["stationCode"], row["timePoint"]): row for row in rows})

    output_rows = []
    for (station_code, timestamp), row in sorted(observations.items(), key=lambda item: item[0]):
        extra = era5_by_key.get((station_code, timestamp), {})
        output_rows.append({
            "观测时间(本地)": timestamp, "站点名称": row.get("stationName"), "站点编码": station_code,
            "行政区编码": row.get("areaCode"), "城市": row.get("cityName"),
            "纬度": pd.to_numeric(row.get("stationLat"), errors="coerce"), "经度": pd.to_numeric(row.get("stationLng"), errors="coerce"),
            "气温(°C)": pd.to_numeric(row.get("temperature"), errors="coerce"), "相对湿度(%)": pd.to_numeric(row.get("humidity"), errors="coerce"),
            "小时降雨量(mm)": pd.to_numeric(row.get("rain"), errors="coerce"), "风向(°)": pd.to_numeric(row.get("windDirection"), errors="coerce"),
            "风向名称": row.get("windDirectionName"), "风速(m/s)": pd.to_numeric(row.get("windSpeed"), errors="coerce"),
            "气压(hPa)": pd.to_numeric(row.get("pressure"), errors="coerce"), "风力等级": pd.to_numeric(row.get("windLevel"), errors="coerce"),
            "边界层高度(m, ERA5)": extra.get("boundary_layer_height"), "云量(% , ERA5)": extra.get("cloud_cover"),
        })
    detail = pd.DataFrame(output_rows)
    summary = detail.groupby(["站点编码", "站点名称"], dropna=False).agg(
        记录数=("观测时间(本地)", "count"), 起始时间=("观测时间(本地)", "min"), 结束时间=("观测时间(本地)", "max"),
        边界层缺测数=("边界层高度(m, ERA5)", lambda s: int(s.isna().sum())), 云量缺测数=("云量(% , ERA5)", lambda s: int(s.isna().sum())),
    ).reset_index()
    summary["应有记录数"] = ((END - START).total_seconds() / 3600 + 1)  # 2208 for a 92-day quarter
    summary["应有记录数"] = summary["应有记录数"].astype(int)
    summary["Suncere缺测数"] = summary["应有记录数"] - summary["记录数"]
    summary = summary[["站点编码", "站点名称", "应有记录数", "记录数", "Suncere缺测数", "起始时间", "结束时间", "边界层缺测数", "云量缺测数"]].sort_values("站点编码")
    fields = pd.DataFrame([
        ["Suncere观测字段", "Suncere", "全国接口筛选 cityName=开封市", "见逐小时数据列名"],
        ["边界层高度(m, ERA5)", "Open-Meteo ERA5 archive", "按各站点经纬度查询 boundary_layer_height；时区 Asia/Shanghai", "m"],
        ["云量(% , ERA5)", "Open-Meteo ERA5 archive", "按各站点经纬度查询 cloud_cover；总云量", "%"],
        ["时间范围", "处理说明", "2025-10-01 00:00 至 2025-12-31 23:00；接口按 12 小时分段", "去年（2025年）"],
    ], columns=["字段/事项", "来源", "口径", "单位/备注"])
    sources = pd.DataFrame([
        ["Suncere", SUNCERE_URL, "2025-10-01 00:00:00 至 2025-12-31 23:00:00；12小时分段；筛选 cityName=开封市"],
        ["Open-Meteo ERA5", OPEN_METEO_URL, "9个站点逐站查询；hourly=cloud_cover,boundary_layer_height；timezone=Asia/Shanghai"],
    ], columns=["数据源", "接口", "请求说明"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        for name, frame in [("逐小时数据", detail), ("站点汇总", summary), ("字段说明", fields), ("数据来源", sources)]:
            frame.to_excel(writer, index=False, sheet_name=name)
            ws = writer.sheets[name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cells in ws.columns:
                ws.column_dimensions[cells[0].column_letter].width = min(max(max(len(str(c.value or "")) for c in cells) + 2, 10), 32)
    print(f"saved={OUTPUT} rows={len(detail)} stations={detail['站点编码'].nunique() if not detail.empty else 0}", flush=True)
    print(summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
