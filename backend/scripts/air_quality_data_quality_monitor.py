"""
CLI entrypoint for hourly air quality data quality monitoring.

Example:
    python scripts/air_quality_data_quality_monitor.py --city 广州 --hours 24
    python scripts/air_quality_data_quality_monitor.py --cities 广州,佛山 --hours 24
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _parse_cities(city: Optional[str], cities: Optional[str]) -> List[str]:
    raw: List[str] = []
    if cities:
        raw.extend([item.strip() for item in cities.split(",") if item.strip()])
    if city:
        raw.append(city.strip())
    result = []
    seen = set()
    for item in raw:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    if not result:
        raise SystemExit("At least one city is required. Use --city or --cities.")
    return result


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid --end-time format: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect suspected air quality monitoring data quality issues.")
    parser.add_argument("--city", help="Single city name, e.g. 广州")
    parser.add_argument("--cities", help="Comma-separated city names, e.g. 广州,佛山")
    parser.add_argument("--hours", type=int, default=24, help="Lookback hours. Default: 24")
    parser.add_argument("--station-type", default="国控", help="Station type. Default: 国控")
    parser.add_argument("--output-root", help="Output folder. Default: backend_data_registry/data_quality_issues")
    parser.add_argument("--end-time", help="End time, e.g. '2026-05-08 18:00:00'. Defaults to current completed hour.")
    return parser


async def main() -> int:
    args = build_parser().parse_args()

    from app.services.air_quality_data_quality_monitor import (
        DataQualityMonitorConfig,
        run_air_quality_data_quality_monitor,
    )

    config = DataQualityMonitorConfig(
        cities=_parse_cities(args.city, args.cities),
        hours=args.hours,
        station_type=args.station_type,
        output_root=Path(args.output_root) if args.output_root else None,
        end_time=_parse_time(args.end_time),
    )
    result = await run_air_quality_data_quality_monitor(config)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
