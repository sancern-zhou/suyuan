"""Operate city history jobs using the deployment's normal environment."""

import argparse
import asyncio
from datetime import date
import json


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["collect", "backfill", "run", "status"])
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--cities", nargs="+")
    parser.add_argument("--job-id")
    parser.add_argument("--max-chunks", type=int, default=60)
    args = parser.parse_args()
    from app.services.weather_history import configured_history_service
    from app.db.database import close_db
    history = configured_history_service()
    if history is None:
        parser.error("The active project has no weather_history configuration")
    try:
        if args.action == "collect":
            history.schedule_collection()
            print(json.dumps(history.jobs.pending(), ensure_ascii=False))
        elif args.action == "backfill":
            if not args.start_date or not args.end_date:
                parser.error("backfill requires --start-date and --end-date (UTC dates)")
            points = history.points()
            if args.cities:
                wanted = {city.removesuffix("市") for city in args.cities}
                points = [p for p in points if p["city"].removesuffix("市") in wanted]
                if len(points) != len(wanted):
                    parser.error("Unknown city in project weather_history points")
            from datetime import datetime, timezone
            if args.end_date >= datetime.now(timezone.utc).date():
                parser.error("Archive jobs must end before today UTC")
            print(json.dumps(history.jobs.submit(points, args.start_date, args.end_date), ensure_ascii=False))
        elif args.action == "run":
            if not 1 <= args.max_chunks <= 1000:
                parser.error("--max-chunks must be between 1 and 1000")
            await history.run_pending(max_chunks=args.max_chunks)
            print(json.dumps(history.jobs.pending(), ensure_ascii=False))
        else:
            if not args.job_id:
                parser.error("status requires --job-id")
            print(json.dumps(history.jobs.get(args.job_id), ensure_ascii=False))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
