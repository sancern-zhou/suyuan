"""Backfill 2026 hourly Suncere weather for Xuchang and neighboring cities."""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import requests

BASE_URL = "http://data.suncereltd.top:8080/api/WeatherData/GetWeatherStationHour"
TOKEN = os.environ.get("SUNCERE_WEATHER_TOKEN", "88e9fc972750a21c0017b2248af051e4")
CITIES = ["许昌市", "郑州市", "开封市", "平顶山市", "漯河市", "周口市"]
SLUGS = {"许昌市": "xuchang", "郑州市": "zhengzhou", "开封市": "kaifeng", "平顶山市": "pingdingshan", "漯河市": "luohe", "周口市": "zhoukou"}
OUT_DIR = Path("/root/suyuan/backend/backend_data_registry/datasets")
CHECKPOINT_ROWS = Path("/tmp/weather_backfill_2026_rows.jsonl")
CHECKPOINT_DONE = Path("/tmp/weather_backfill_2026_done.txt")

START = date(2026, 1, 1)
END = min(date.today(), date(2026, 12, 31))


def fetch_half(day: date, start_hour: int) -> list[dict]:
    begin = f"{day.isoformat()} {start_hour:02d}:00:00"
    end = f"{day.isoformat()} {start_hour + 11:02d}:00:00"
    for attempt in range(5):
        try:
            response = requests.get(BASE_URL, params={"token": TOKEN, "beginTime": begin, "endTime": end}, timeout=180)
            if response.status_code == 200:
                return [r for r in (response.json().get("dataList") or []) if r.get("cityName") in CITIES]
            if response.status_code not in {413, 429, 500, 502, 503, 504}:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            if attempt == 4:
                print(f"give_up {day.isoformat()}T{start_hour:02d}: {exc}", flush=True)
                return []
            time.sleep(2**attempt)
    return []


def probe() -> None:
    rows = fetch_half(START, 0)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.get("cityName") or "?"] = counts.get(row.get("cityName") or "?", 0) + 1
    print(f"probe_rows={len(rows)} cities={sorted(counts.items())}", flush=True)
    if rows:
        print(f"sample={json.dumps(rows[0], ensure_ascii=False)[:300]}", flush=True)


def main() -> None:
    jobs = [(START + timedelta(days=i), h) for i in range((END - START).days + 1) for h in (0, 12)]
    completed = set()
    if CHECKPOINT_DONE.exists():
        completed = {line.strip() for line in CHECKPOINT_DONE.read_text(encoding="utf-8").splitlines() if line.strip()}
    outputs: dict[str, dict[tuple[str, str], dict]] = {c: {} for c in CITIES}
    if CHECKPOINT_ROWS.exists():
        for line in CHECKPOINT_ROWS.open(encoding="utf-8"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            city = row.get("cityName") or ""
            ts = str(row.get("timePoint", ""))[:16]
            code = str(row.get("stationCode", ""))
            if city in outputs and code and ts:
                outputs[city][(ts, code)] = row
    pending = [(d, h) for d, h in jobs if f"{d.isoformat()}T{h:02d}" not in completed]
    print(f"jobs={len(jobs)} done={len(completed)} pending={len(pending)} cities={CITIES}", flush=True)
    if not pending:
        sys.exit(0)

    with CHECKPOINT_ROWS.open("a", encoding="utf-8") as rows_file, CHECKPOINT_DONE.open("a", encoding="utf-8") as done_file:
        with ThreadPoolExecutor(max_workers=int(os.environ.get("WEATHER_BACKFILL_WORKERS", "3"))) as pool:
            futures = {pool.submit(fetch_half, d, h): (d, h) for d, h in pending}
            for n, future in enumerate(as_completed(futures), 1):
                day, hour = futures[future]
                for row in future.result():
                    city = row.get("cityName") or ""
                    ts = str(row.get("timePoint", ""))[:16]
                    code = str(row.get("stationCode", ""))
                    if city in outputs and code and ts:
                        outputs[city][(ts, code)] = row
                        rows_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                done_file.write(f"{day.isoformat()}T{hour:02d}\n")
                rows_file.flush()
                done_file.flush()
                completed.add(f"{day.isoformat()}T{hour:02d}")
                if n % 20 == 0 or n == len(futures):
                    counts = {c: len(outputs[c]) for c in CITIES}
                    print(f"progress={n}/{len(futures)} rows={counts}", flush=True)

    for city in CITIES:
        rows = outputs[city]
        path = OUT_DIR / f"{SLUGS[city]}_weather_2026.jsonl"
        ordered = [row for _, row in sorted(rows.items(), key=lambda kv: kv[0])]
        if city == "许昌市":
            existing: set[tuple[str, str]] = set()
            if path.exists():
                for line in path.open(encoding="utf-8"):
                    try:
                        old = json.loads(line)
                        existing.add((str(old.get("timePoint", ""))[:16], str(old.get("stationCode", ""))))
                    except ValueError:
                        pass
            fresh = [r for r in ordered if (str(r.get("timePoint", ""))[:16], str(r.get("stationCode", ""))) not in existing]
            if not fresh:
                print(f"xuchang: no new rows, skip", flush=True)
                continue
            with path.open("a", encoding="utf-8") as out:
                for row in fresh:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"xuchang: appended={len(fresh)} total_keys={len(existing) + len(fresh)} path={path}", flush=True)
        else:
            with path.open("w", encoding="utf-8") as out:
                for row in ordered:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
            with path.open("rb") as src, gzip.open(path.with_suffix(path.suffix + ".gz"), "wb") as dst:
                dst.writelines(src)
            print(f"saved={path} rows={len(ordered)}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        probe()
    else:
        main()
