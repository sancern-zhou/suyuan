"""Back up and re-fetch one historical weather point; dry-run unless --apply."""

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta, timezone

from app.utils.path_config import format_agent_path, resolve_agent_path
from app.utils.weather_time import OPEN_METEO_SOURCE


def validate_records(records, start, end):
    expected = {start + timedelta(hours=i) for i in range(int((end - start).total_seconds() / 3600))}
    actual = {record["time"] for record in records}
    if len(records) != len(expected) or actual != expected:
        raise ValueError("Upstream response does not contain the complete requested UTC hours")
    if any(record["boundary_layer_height"] is None for record in records):
        raise ValueError("Upstream boundary layer heights are incomplete; database left unchanged")


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(resolve_agent_path(args.env_file), override=True)
    from sqlalchemy import delete, select
    from sqlalchemy.dialects.postgresql import insert
    from app.db.models import ERA5ReanalysisData
    from app.db.repositories import weather_repo
    from app.external_apis.openmeteo_client import OpenMeteoClient

    session_factory = getattr(weather_repo, "weather_async_session", None) or weather_repo.async_session
    start = datetime.combine(date.fromisoformat(args.start_date), datetime.min.time(), timezone.utc)
    end = datetime.combine(date.fromisoformat(args.end_date) + timedelta(days=1), datetime.min.time(), timezone.utc)
    if end <= start or not 0 <= args.legacy_shift_hours <= 14:
        raise ValueError("Invalid date range or legacy shift")
    backup_dir = resolve_agent_path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=False, mode=0o700)

    def save(name, data):
        with (backup_dir / name).open("x", encoding="utf-8") as handle:
            json.dump(data, handle, default=str, ensure_ascii=False, indent=2, allow_nan=False)

    criteria = (
        ERA5ReanalysisData.lat == args.lat,
        ERA5ReanalysisData.lon == args.lon,
        ERA5ReanalysisData.time >= start - timedelta(hours=args.legacy_shift_hours),
        ERA5ReanalysisData.time < end,
    )
    query = select(ERA5ReanalysisData.__table__).where(*criteria).order_by(ERA5ReanalysisData.time)
    async with session_factory() as session:
        before = [dict(row) for row in (await session.execute(query)).mappings()]
    if any(row["data_source"] not in {"ERA5", OPEN_METEO_SOURCE} for row in before):
        raise ValueError("Unexpected data source in replacement range")
    save("before.json", before)

    client = OpenMeteoClient()
    records = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=7), end)
        response = await client.fetch_era5_data(args.lat, args.lon, cursor.date().isoformat(), (chunk_end - timedelta(days=1)).date().isoformat())
        save(f"upstream-{cursor.date()}.json", response)
        chunk = weather_repo.WeatherRepository.build_era5_records(args.lat, args.lon, response)
        validate_records(chunk, cursor, chunk_end)
        records.extend(chunk)
        print(f"Fetched {cursor.date()} through {(chunk_end - timedelta(days=1)).date()}: {len(chunk)} hours", flush=True)
        cursor = chunk_end
    validate_records(records, start, end)
    save("replacement.json", records)
    manifest = {
        "lat": args.lat, "lon": args.lon,
        "utc_start": start.isoformat(), "utc_end_exclusive": end.isoformat(),
        "legacy_shift_hours": args.legacy_shift_hours,
        "before_count": len(before), "replacement_count": len(records),
        "data_source": OPEN_METEO_SOURCE, "applied": False,
    }
    save("plan.json", manifest)
    print(json.dumps(manifest), flush=True)
    if args.apply:
        async with session_factory() as session:
            async with session.begin():
                current = [dict(row) for row in (await session.execute(query.with_for_update())).mappings()]
                if current != before:
                    raise RuntimeError("Weather records changed during staging; retry with a fresh backup")
                await session.execute(delete(ERA5ReanalysisData).where(*criteria))
                for offset in range(0, len(records), 168):
                    await session.execute(insert(ERA5ReanalysisData).values(records[offset:offset + 168]))
        save("applied.json", {**manifest, "applied": True, "applied_at": datetime.now(timezone.utc).isoformat()})
    print("Backup: " + format_agent_path(backup_dir), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default="backend/.env")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--start-date", required=True, help="First upstream UTC date")
    parser.add_argument("--end-date", required=True, help="Last upstream UTC date (inclusive)")
    parser.add_argument("--legacy-shift-hours", type=int, default=0)
    parser.add_argument("--backup-dir", required=True, help="New project-relative or absolute backup directory")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))
