"""Backfill tender information for an explicit publish-date range.

The scheduled fetcher only ever crawls yesterday's notices. This script replays
the same pipeline for an arbitrary date range so a month can be filled in.

To avoid re-crawling work that is already done, each date is skipped when its
latest fetch run succeeded *and* it has no pending candidates, and keywords
whose candidates for that date are already fully judged (no pending row) are
not searched again. Use --force to disable both shortcuts.

Examples:
    python scripts/backfill_tender_information.py --start 2026-08-01 --end 2026-08-31
    python scripts/backfill_tender_information.py --start 2026-08-01 --end 2026-08-01 \
        --keywords 大气监测,大气污染防控 --max-pages 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise SystemExit(f"Invalid date '{value}', expected YYYY-MM-DD") from exc


def _iter_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _connect():
    import pyodbc

    from config.settings import settings

    return pyodbc.connect(settings.sqlserver_connection_string, timeout=30)


def _load_skip_sets(conn) -> tuple[set[date], set[date]]:
    """Return (successful_dates, dates_with_pending_candidates)."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT r.target_date
        FROM tender_fetch_runs r
        JOIN (
            SELECT target_date, MAX(id) AS max_id
            FROM tender_fetch_runs
            GROUP BY target_date
        ) latest ON latest.max_id = r.id
        WHERE r.status = 'success'
        """
    )
    successful = {row[0] for row in cursor.fetchall() if row[0] is not None}
    cursor.execute(
        """
        SELECT DISTINCT publish_date
        FROM tender_candidates
        WHERE filter_status = 'pending' AND publish_date IS NOT NULL
        """
    )
    pending = {row[0] for row in cursor.fetchall() if row[0] is not None}
    return successful, pending


def _decided_keywords(
    cursor, target_date: date, keywords: list[str]
) -> set[str]:
    if not keywords:
        return set()
    placeholders = ", ".join("?" for _ in keywords)
    cursor.execute(
        f"""
        SELECT keyword
        FROM tender_candidates
        WHERE publish_date = ? AND keyword IN ({placeholders})
        GROUP BY keyword
        HAVING SUM(CASE WHEN filter_status = 'pending' THEN 1 ELSE 0 END) = 0
        """,
        (target_date, *keywords),
    )
    return {row[0] for row in cursor.fetchall() if row[0]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill tender information for a publish-date range."
    )
    parser.add_argument("--start", required=True, help="Start publish date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End publish date, YYYY-MM-DD")
    parser.add_argument(
        "--keywords",
        help="Comma-separated keywords. Defaults to TENDER_KEYWORDS from settings.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max search pages per keyword; 0 means complete target-date crawl.",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Pause between dates. Default: 0",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-crawl dates/keywords even when they are already completed.",
    )
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    start_date = _parse_date(args.start)
    end_date = _parse_date(args.end)
    if end_date < start_date:
        raise SystemExit("--end must be on or after --start")

    from app.fetchers.tenders.tender_information_fetcher import (
        TenderInformationFetcher,
    )
    from app.services.tenders.config import parse_keywords

    fetcher = TenderInformationFetcher()
    all_keywords = (
        parse_keywords(args.keywords)
        if args.keywords
        else list(fetcher.config.keywords)
    )
    if args.max_pages is not None:
        fetcher.config.max_pages = args.max_pages

    successful_dates: set[date] = set()
    pending_dates: set[date] = set()
    if not args.force:
        try:
            conn = _connect()
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"skip_check_disabled": repr(exc)}), flush=True)
        else:
            try:
                successful_dates, pending_dates = _load_skip_sets(conn)
            finally:
                conn.close()

    print(
        json.dumps(
            {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "keywords": all_keywords,
                "max_pages": fetcher.config.max_pages,
                "notice_types": [item.value for item in fetcher.config.notice_types],
                "force": args.force,
                "successful_dates": sorted(d.isoformat() for d in successful_dates),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    summary: list[dict] = []
    for target_date in _iter_dates(start_date, end_date):
        if target_date in successful_dates and target_date not in pending_dates:
            skipped = {
                "target_date": target_date.isoformat(),
                "skipped": True,
                "reason": "already_successful",
            }
            summary.append(skipped)
            print(json.dumps(skipped, ensure_ascii=False), flush=True)
            continue

        keywords = list(all_keywords)
        if not args.force:
            try:
                conn = _connect()
                try:
                    decided = _decided_keywords(
                        conn.cursor(), target_date, keywords
                    )
                finally:
                    conn.close()
            except Exception:  # noqa: BLE001
                decided = set()
            keywords = [item for item in keywords if item not in decided]

        if not keywords:
            skipped = {
                "target_date": target_date.isoformat(),
                "skipped": True,
                "reason": "all_keywords_decided",
            }
            summary.append(skipped)
            print(json.dumps(skipped, ensure_ascii=False), flush=True)
            continue

        fetcher.config.keywords = keywords
        fetcher.today_factory = (lambda d: (lambda: d + timedelta(days=1)))(
            target_date
        )
        try:
            result = await fetcher.fetch_and_store()
        except Exception as exc:  # keep going across dates
            result = {"target_date": target_date.isoformat(), "error": repr(exc)}
        result["target_date"] = target_date.isoformat()
        summary.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.pause_seconds:
            await asyncio.sleep(args.pause_seconds)

    processed = [item for item in summary if not item.get("skipped")]
    totals = {
        "days": len(summary),
        "processed_days": len(processed),
        "skipped_days": len(summary) - len(processed),
        "saved_notices": sum(int(item.get("saved_notices") or 0) for item in processed),
        "total_candidates": sum(
            int(item.get("total_candidates") or 0) for item in processed
        ),
        "errors": sum(int(item.get("errors") or 0) for item in processed),
        "failed_days": [
            item["target_date"] for item in processed if item.get("error")
        ],
    }
    print(json.dumps({"summary": totals}, ensure_ascii=False, default=str), flush=True)
    return 0 if not totals["failed_days"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
