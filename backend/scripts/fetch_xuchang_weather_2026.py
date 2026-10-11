"""Download 2026 hourly Suncere weather records for Xuchang stations."""
from __future__ import annotations

import gzip
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import requests

BASE_URL = "http://data.suncereltd.top:8080/api/WeatherData/GetWeatherStationHour"
TOKEN = os.environ.get("SUNCERE_WEATHER_TOKEN", "")
STATIONS = {f"10118040{i}": name for i, name in enumerate(("鄢陵", "襄城", "长葛", "禹州", "魏都", "建安"), 2)}
OUT = Path(__file__).resolve().parents[1] / "backend_data_registry" / "datasets" / "xuchang_weather_2026.jsonl"
OUT_GZ = OUT.with_suffix(OUT.suffix + ".gz")


def fetch_half(day: date, start_hour: int) -> tuple[str, list[dict]]:
    begin = f"{day.isoformat()} {start_hour:02d}:00:00"
    end = f"{day.isoformat()} {start_hour + 11:02d}:00:00"
    for attempt in range(4):
        try:
            response = requests.get(
                BASE_URL,
                params={"token": TOKEN, "beginTime": begin, "endTime": end},
                timeout=90,
            )
            if response.status_code == 200:
                payload = response.json()
                rows = [r for r in (payload.get("dataList") or []) if r.get("stationCode") in STATIONS]
                return f"{day.isoformat()}T{start_hour:02d}", rows
            if response.status_code in {413, 429, 500, 502, 503, 504}:
                time.sleep(2**attempt)
                continue
            return f"{day.isoformat()}T{start_hour:02d}", []
        except requests.RequestException:
            time.sleep(2**attempt)
    return f"{day.isoformat()}T{start_hour:02d}", []


def main() -> None:
    if not TOKEN:
        raise SystemExit("SUNCERE_WEATHER_TOKEN is required")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    start = date(2026, 1, 1)
    end = min(date.today(), date(2026, 12, 31))
    jobs = [(start + timedelta(days=i), h) for i in range((end - start).days + 1) for h in (0, 12)]
    existing = set()
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            try:
                row = json.loads(line)
                existing.add((row.get("timePoint"), row.get("stationCode")))
            except Exception:
                pass
    total = 0
    with OUT.open("a", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(fetch_half, *job) for job in jobs]
            for n, future in enumerate(as_completed(futures), 1):
                _, rows = future.result()
                for row in rows:
                    key = (row.get("timePoint"), row.get("stationCode"))
                    if key not in existing:
                        out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        existing.add(key)
                        total += 1
                if n % 20 == 0 or n == len(futures):
                    out.flush()
                    print(f"progress={n}/{len(futures)} records_added={total} unique={len(existing)}", flush=True)
    with OUT.open("rb") as src, gzip.open(OUT_GZ, "wb") as dst:
        dst.writelines(src)
    print(f"saved={OUT} compressed={OUT_GZ} records={len(existing)}", flush=True)


if __name__ == "__main__":
    main()
