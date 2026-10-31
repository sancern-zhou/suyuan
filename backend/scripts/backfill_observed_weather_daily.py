"""Backfill observed_weather_daily from hourly observations.

用法（宿主机，conda backend_py311）：

    cd /root/suyuan/backend
    WEATHER_DATABASE_URL 可从 backend/.env 读取；也可直接环境变量传入。
    python scripts/backfill_observed_weather_daily.py --start 2025-01-01

幂等：重复执行按 (station_id, obs_date) upsert。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _load_weather_database_url_from_env_file() -> None:
    if os.getenv("WEATHER_DATABASE_URL"):
        return
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("WEATHER_DATABASE_URL="):
            os.environ["WEATHER_DATABASE_URL"] = line.split("=", 1)[1].strip()
            return


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="起始北京日历日 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="结束北京日历日（默认今天）")
    parser.add_argument(
        "--min-valid-hours",
        type=int,
        default=20,
        help="产出日值所需最少有效小时数（默认 20）",
    )
    args = parser.parse_args()

    _load_weather_database_url_from_env_file()

    from app.fetchers.weather.observed_daily_fetcher import (
        beijing_today,
        ensure_daily_table,
        upsert_observed_weather_daily,
    )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else beijing_today()
    await ensure_daily_table()
    # 分月重算，避免单条语句窗口过大
    current = start
    while current <= end:
        if current.month < 12:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        else:
            month_end = date(current.year, 12, 31)
        last = min(month_end, end)
        result = await upsert_observed_weather_daily(
            current, last, min_valid_hours=args.min_valid_hours
        )
        print(f"{result['start_date']} ~ {result['end_date']}: upsert {result['upserted_station_days']} station-days")
        current = last + timedelta(days=1)


if __name__ == "__main__":
    asyncio.run(main())
