"""Fill missing hourly weather rows with Open-Meteo ERA5 archive, Suncere-compatible schema."""
from __future__ import annotations

import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OUT_DIR = Path("/root/suyuan/backend/backend_data_registry/datasets")
CITY_FILES = {
    "许昌市": "xuchang_weather_2026.jsonl",
    "郑州市": "zhengzhou_weather_2026.jsonl",
    "开封市": "kaifeng_weather_2026.jsonl",
    "平顶山市": "pingdingshan_weather_2026.jsonl",
    "漯河市": "luohe_weather_2026.jsonl",
    "周口市": "zhoukou_weather_2026.jsonl",
}
START = date(2026, 1, 1)
END = min(date.today(), date(2026, 12, 31))
HOURLY = "temperature_2m,relative_humidity_2m,precipitation,surface_pressure,wind_speed_10m,wind_direction_10m"
WIND_NAMES = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
LEVEL_BOUNDS = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]


def wind_level(speed: float) -> int:
    for i, bound in enumerate(LEVEL_BOUNDS):
        if speed < bound:
            return i
    return 12


def wind_name(deg: float) -> str:
    return WIND_NAMES[int(((deg + 22.5) % 360) // 45)]


def fmt(value, digits: int = 1) -> str:
    if value is None:
        return ""
    return f"{round(float(value), digits):.{digits}f}" if digits else str(int(round(float(value))))


def load_city(path: Path) -> tuple[dict[str, dict], dict[tuple[str, str], dict]]:
    stations: dict[str, dict] = {}
    rows: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return stations, rows
    for line in path.open(encoding="utf-8"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        code = str(row.get("stationCode", ""))
        ts = str(row.get("timePoint", ""))[:13]
        if not code or not ts:
            continue
        rows[(code, ts)] = row
        if code not in stations and row.get("stationLat") and row.get("stationLng"):
            stations[code] = {
                "stationName": row.get("stationName", ""),
                "areaCode": row.get("areaCode", ""),
                "stationLat": row.get("stationLat"),
                "stationLng": row.get("stationLng"),
            }
    return stations, rows


def fetch_era5(station: dict) -> dict[str, dict]:
    params = {
        "latitude": float(station["stationLat"]),
        "longitude": float(station["stationLng"]),
        "start_date": START.isoformat(),
        "end_date": END.isoformat(),
        "hourly": HOURLY,
        "wind_speed_unit": "ms",
        "timezone": "Asia/Shanghai",
    }
    for attempt in range(5):
        try:
            response = requests.get(ARCHIVE_URL, params=params, timeout=180)
            if response.status_code == 200:
                hourly = response.json().get("hourly") or {}
                out: dict[str, dict] = {}
                times = hourly.get("time") or []
                cols = list(zip(
                    times,
                    hourly.get("temperature_2m") or [],
                    hourly.get("relative_humidity_2m") or [],
                    hourly.get("precipitation") or [],
                    hourly.get("wind_direction_10m") or [],
                    hourly.get("wind_speed_10m") or [],
                    hourly.get("surface_pressure") or [],
                ))
                for ts, temp, rh, rain, wdir, wspd, pres in cols:
                    if temp is None and wspd is None:
                        continue
                    deg = float(wdir) if wdir is not None else 0.0
                    speed = float(wspd) if wspd is not None else 0.0
                    out[ts[:13]] = {
                        "temperature": fmt(temp),
                        "humidity": fmt(rh, 0),
                        "rain": fmt(rain),
                        "windDirection": int(deg) % 360,
                        "windDirectionName": wind_name(deg),
                        "windSpeed": fmt(speed),
                        "windLevel": wind_level(speed),
                        "pressure": fmt(pres),
                    }
                return out
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"Open-Meteo HTTP {response.status_code}: {response.text[:200]}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            if attempt == 4:
                print(f"era5_give_up {station['stationCode']}: {exc}", flush=True)
                return {}
            time.sleep(2**attempt)
    return {}


def main() -> None:
    all_hours = [f"{START + timedelta(days=i):%Y-%m-%d}T{h:02d}" for i in range((END - START).days + 1) for h in range(24)]
    report: dict[str, dict] = {}
    for city, name in CITY_FILES.items():
        path = OUT_DIR / name
        stations, existing = load_city(path)
        if not stations:
            print(f"{city}: no suncere rows, skip", flush=True)
            continue
        missing_by_station: dict[str, list[str]] = {}
        for (code, ts) in {(code, ts) for code in stations for ts in all_hours}:
            if (code, ts) not in existing:
                missing_by_station.setdefault(code, []).append(ts)
        total_missing = sum(len(v) for v in missing_by_station.values())
        print(f"{city}: stations={len(stations)} existing={len(existing)} missing={total_missing}", flush=True)
        if not total_missing:
            report[city] = {"stations": len(stations), "existing": len(existing), "era5_filled": 0, "still_missing": 0}
            continue

        filled: dict[tuple[str, str], dict] = {}
        still_missing = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch_era5, stations[code]): code for code in missing_by_station}
            for future in as_completed(futures):
                code = futures[future]
                era5 = future.result()
                for ts in missing_by_station[code]:
                    values = era5.get(ts)
                    if values is None:
                        still_missing += 1
                        continue
                    meta = stations[code]
                    hour = int(ts[11:13])
                    filled[(code, ts)] = {
                        "stationName": meta["stationName"],
                        "stationCode": code,
                        "areaCode": meta["areaCode"],
                        "cityName": city,
                        "timePoint": f"{ts}:00:00",
                        "temperature": values["temperature"],
                        "humidity": values["humidity"],
                        "rain": values["rain"],
                        "windDirection": values["windDirection"],
                        "windSpeed": values["windSpeed"],
                        "pressure": values["pressure"],
                        "windLevel": values["windLevel"],
                        "windDirectionName": values["windDirectionName"],
                        "stationLat": meta["stationLat"],
                        "stationLng": meta["stationLng"],
                        "dataSource": "era5_open_meteo",
                    }

        merged = list(existing.values()) + list(filled.values())
        merged.sort(key=lambda r: (str(r.get("timePoint", "")), str(r.get("stationCode", ""))))
        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as out:
            for row in merged:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(path)
        with path.open("rb") as src, gzip.open(path.with_suffix(path.suffix + ".gz"), "wb") as dst:
            dst.writelines(src)
        audit = {
            "city": city,
            "suncere_rows": len(existing),
            "era5_filled": len(filled),
            "still_missing": still_missing,
            "era5_keys": sorted(f"{k[1]}|{k[0]}" for k in filled),
        }
        (OUT_DIR / name.replace(".jsonl", "_era5_gapfill_audit.json")).write_text(
            json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        report[city] = {"stations": len(stations), "existing": len(existing), "era5_filled": len(filled), "still_missing": still_missing}
        print(f"{city}: merged={len(merged)} era5_filled={len(filled)} still_missing={still_missing} saved={path}", flush=True)
    print("SUMMARY " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
