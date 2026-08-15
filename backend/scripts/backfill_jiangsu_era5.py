"""Backfill ERA5 hourly data for Jiangsu city-center targets.

Examples (run from ``backend/`` with the backend_py311 environment)::

    python scripts/backfill_jiangsu_era5.py \
        --start-date 2026-08-01 --end-date 2026-08-13
    python scripts/backfill_jiangsu_era5.py \
        --start-date 2026-01-01 --end-date 2026-08-13

The Open-Meteo archive rejects dates after its current availability boundary,
so the caller must use an available end date.  The script is idempotent: the
repository upserts on ``(time, lat, lon)``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env.jiangsu-ops", override=True)

from app.config.weather_targets import ERA5_MAIN_FETCHER, iter_era5_city_targets  # noqa: E402
from app.db.database import close_db  # noqa: E402
from app.db.repositories.weather_repo import WeatherRepository  # noqa: E402
from app.external_apis.openmeteo_client import OpenMeteoClient  # noqa: E402
from app.fetchers.weather.era5_fetcher import ERA5Fetcher  # noqa: E402


@dataclass(frozen=True)
class TargetPoint:
    city: str
    lat: float
    lon: float


def _targets() -> list[TargetPoint]:
    targets = []
    seen: set[tuple[float, float]] = set()
    for target in iter_era5_city_targets(ERA5_MAIN_FETCHER):
        if target.province != "江苏省" or target.era5_point is None:
            continue
        lat, lon = ERA5Fetcher._align_to_era5_grid(
            target.era5_lat,
            target.era5_lon,
        )
        if (lat, lon) in seen:
            continue
        seen.add((lat, lon))
        targets.append(TargetPoint(city=target.city, lat=lat, lon=lon))
    return targets


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"日期必须为 YYYY-MM-DD：{value}"
        ) from exc


def _chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


async def _fetch_chunk(
    *,
    client: OpenMeteoClient,
    repo: WeatherRepository,
    target: TargetPoint,
    start: date,
    end: date,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        try:
            payload = await client.fetch_era5_data(
                lat=target.lat,
                lon=target.lon,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
            saved = await repo.save_era5_data(target.lat, target.lon, payload)
            return {
                "city": target.city,
                "lat": target.lat,
                "lon": target.lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "records_saved": saved,
                "status": "success" if saved else "empty",
            }
        except Exception as exc:
            return {
                "city": target.city,
                "lat": target.lat,
                "lon": target.lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "records_saved": 0,
                "status": "failed",
                "error": str(exc),
            }


async def backfill(
    *,
    start: date,
    end: date,
    chunk_days: int = 31,
    concurrency: int = 3,
) -> dict[str, Any]:
    if start > end:
        raise ValueError("start-date 不能晚于 end-date")
    if chunk_days < 1 or chunk_days > 31:
        raise ValueError("chunk-days 必须在 1 至 31 之间")
    if concurrency < 1 or concurrency > 8:
        raise ValueError("concurrency 必须在 1 至 8 之间")

    targets = _targets()
    chunks = _chunks(start, end, chunk_days)
    if not targets:
        raise RuntimeError("未找到江苏 ERA5 城市目标")

    client = OpenMeteoClient()
    repo = WeatherRepository()
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []
    try:
        for chunk_start, chunk_end in chunks:
            chunk_results = await asyncio.gather(
                *(
                    _fetch_chunk(
                        client=client,
                        repo=repo,
                        target=target,
                        start=chunk_start,
                        end=chunk_end,
                        semaphore=semaphore,
                    )
                    for target in targets
                )
            )
            results.extend(chunk_results)
            saved = sum(item["records_saved"] for item in chunk_results)
            failed = sum(item["status"] == "failed" for item in chunk_results)
            print(
                f"chunk {chunk_start}..{chunk_end}: "
                f"saved={saved}, failed={failed}/{len(chunk_results)}",
                flush=True,
            )
    finally:
        await close_db()

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "target_count": len(targets),
        "chunk_count": len(chunks),
        "request_count": len(results),
        "successful_requests": sum(item["status"] == "success" for item in results),
        "failed_requests": sum(item["status"] == "failed" for item in results),
        "records_saved": sum(item["records_saved"] for item in results),
        "failures": [item for item in results if item["status"] == "failed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="回补江苏省 ERA5 城市中心点历史数据")
    parser.add_argument("--start-date", required=True, type=_parse_date)
    parser.add_argument("--end-date", required=True, type=_parse_date)
    parser.add_argument("--chunk-days", type=int, default=31)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    result = asyncio.run(
        backfill(
            start=args.start_date,
            end=args.end_date,
            chunk_days=args.chunk_days,
            concurrency=args.concurrency,
        )
    )
    print(result)
    if result["failed_requests"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
