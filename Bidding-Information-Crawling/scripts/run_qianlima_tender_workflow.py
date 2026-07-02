from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import resume_pending_tenders, revalidate_tender_notices
from src.tenders.cli import load_environment, parse_notice_types
from src.tenders.models import NoticeType, TenderCandidate
from src.tenders.pipeline import maybe_close_client
from src.tenders.qianlima_client import QianlimaClient
from src.tenders.repository import SQLiteTenderRepository


@dataclass(slots=True)
class CollectResult:
    total_found: int = 0
    saved: int = 0
    duplicates: int = 0
    errors: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run staged Qianlima tender workflow.")
    parser.add_argument(
        "--keywords", default=os.getenv("TENDER_KEYWORDS", "生态环境局")
    )
    parser.add_argument(
        "--notice-types", default=os.getenv("TENDER_NOTICE_TYPES", "tender")
    )
    parser.add_argument("--publish-date", default=os.getenv("TENDER_PUBLISH_DATE", ""))
    parser.add_argument(
        "--max-pages", type=int, default=int(os.getenv("TENDER_MAX_PAGES", "0"))
    )
    parser.add_argument(
        "--sqlite-db", default=os.getenv("TENDER_SQLITE_DB", "data/tenders.db")
    )
    parser.add_argument(
        "--storage-state",
        default=os.getenv("QIANLIMA_STORAGE_STATE", "data/qianlima_storage_state.json"),
    )
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--login-url", default=os.getenv("QIANLIMA_LOGIN_URL", ""))
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument("--skip-screen", action="store_true")
    parser.add_argument("--skip-detail", action="store_true")
    parser.add_argument("--skip-revalidate", action="store_true")
    parser.add_argument("--stats-only", action="store_true")
    parser.add_argument(
        "--batch-size", type=int, default=int(os.getenv("TENDER_LLM_BATCH_SIZE", "40"))
    )
    parser.add_argument(
        "--batch-delay-ms",
        type=int,
        default=int(os.getenv("TENDER_LLM_BATCH_DELAY_MS", "500")),
    )
    parser.add_argument(
        "--candidate-delay-ms",
        type=int,
        default=int(os.getenv("TENDER_CANDIDATE_DELAY_MS", "500")),
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=int(os.getenv("TENDER_DETAIL_WORKERS", "3")),
    )
    parser.add_argument(
        "--revalidate-workers",
        type=int,
        default=int(os.getenv("TENDER_REVALIDATE_WORKERS", "3")),
    )
    parser.add_argument("--keep-rejected-notices", action="store_true")
    parser.add_argument(
        "--detail-review-before-extract",
        action="store_true",
        help="结构化抽取前先做详情复核；默认由最后的 revalidate 阶段统一复核。",
    )
    return parser.parse_args()


def split_keywords(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def print_progress(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def workflow_stats(db_path: str) -> dict:
    path = Path(db_path)
    if not path.exists():
        return {
            "db": db_path,
            "exists": False,
            "candidates": 0,
            "status": {},
            "notices": 0,
            "accepted_missing": 0,
            "rejected_notice_remaining": 0,
            "publish_dates": {},
        }
    with sqlite3.connect(db_path) as conn:
        status = dict(
            conn.execute(
                "SELECT filter_status, COUNT(*) FROM tender_candidates GROUP BY filter_status"
            )
        )
        publish_dates = dict(
            conn.execute(
                "SELECT publish_date, COUNT(*) FROM tender_notices GROUP BY publish_date"
            )
        )
        return {
            "db": db_path,
            "exists": True,
            "candidates": conn.execute(
                "SELECT COUNT(*) FROM tender_candidates"
            ).fetchone()[0],
            "status": status,
            "notices": conn.execute("SELECT COUNT(*) FROM tender_notices").fetchone()[
                0
            ],
            "accepted_missing": conn.execute("""
                SELECT COUNT(*)
                FROM tender_candidates c
                LEFT JOIN tender_notices n ON c.url = n.url
                WHERE c.filter_status = 'accepted' AND n.url IS NULL
                """).fetchone()[0],
            "rejected_notice_remaining": conn.execute("""
                SELECT COUNT(*)
                FROM tender_notices n
                JOIN tender_candidates c ON c.url = n.url
                WHERE c.filter_status = 'rejected'
                """).fetchone()[0],
            "publish_dates": publish_dates,
        }


async def collect_candidates(
    client: QianlimaClient,
    repository: SQLiteTenderRepository,
    keywords: list[str],
    notice_types: list[NoticeType],
    publish_date: date | None,
    max_pages: int,
) -> CollectResult:
    result = CollectResult()
    for keyword in keywords:
        for notice_type in notice_types:
            try:
                candidates = await client.search(
                    keyword=keyword,
                    notice_type=notice_type,
                    publish_date=publish_date,
                    max_pages=max_pages,
                )
            except Exception as exc:
                result.errors += 1
                print_progress(
                    {
                        "event": "collect_error",
                        "keyword": keyword,
                        "notice_type": notice_type.value,
                        "error": str(exc),
                    }
                )
                continue
            await save_candidates(repository, candidates, result)
            print_progress(
                {
                    "event": "collect_group_done",
                    "keyword": keyword,
                    "notice_type": notice_type.value,
                    "found": len(candidates),
                    "saved_total": result.saved,
                    "duplicates_total": result.duplicates,
                }
            )
    return result


async def save_candidates(
    repository: SQLiteTenderRepository,
    candidates: list[TenderCandidate],
    result: CollectResult,
) -> None:
    result.total_found += len(candidates)
    for candidate in candidates:
        if await repository.save_candidate(candidate):
            result.saved += 1
        else:
            result.duplicates += 1


async def run_screen_stage(args: argparse.Namespace) -> None:
    await resume_pending_tenders.run(
        argparse.Namespace(
            sqlite_db=args.sqlite_db,
            limit=0,
            batch_size=args.batch_size,
            batch_delay_ms=args.batch_delay_ms,
            candidate_delay_ms=args.candidate_delay_ms,
            storage_state=args.storage_state,
            show_browser=args.show_browser,
            screen_only=True,
            accepted_missing=False,
            skip_detail_review=True,
            workers=args.detail_workers,
        )
    )


async def run_detail_stage(args: argparse.Namespace) -> None:
    await resume_pending_tenders.run(
        argparse.Namespace(
            sqlite_db=args.sqlite_db,
            limit=0,
            batch_size=args.batch_size,
            batch_delay_ms=args.batch_delay_ms,
            candidate_delay_ms=args.candidate_delay_ms,
            storage_state=args.storage_state,
            show_browser=args.show_browser,
            screen_only=False,
            accepted_missing=True,
            skip_detail_review=not args.detail_review_before_extract,
            workers=args.detail_workers,
        )
    )


async def run_revalidate_stage(args: argparse.Namespace) -> None:
    await revalidate_tender_notices.run(
        argparse.Namespace(
            sqlite_db=args.sqlite_db,
            limit=0,
            workers=args.revalidate_workers,
            keep_rejected_notices=args.keep_rejected_notices,
        )
    )


async def run_workflow(args: argparse.Namespace) -> None:
    load_environment()
    if args.stats_only:
        print_progress({"event": "stats", **workflow_stats(args.sqlite_db)})
        return

    keywords = split_keywords(args.keywords)
    notice_types = parse_notice_types(args.notice_types)
    publish_date = date.fromisoformat(args.publish_date) if args.publish_date else None

    print_progress({"event": "workflow_start", "db": args.sqlite_db})
    if not args.skip_collect:
        client = QianlimaClient(
            storage_state_path=args.storage_state,
            headless=not args.show_browser,
        )
        try:
            if args.login:
                await client.login(args.login_url)
            result = await collect_candidates(
                client=client,
                repository=SQLiteTenderRepository(args.sqlite_db),
                keywords=keywords,
                notice_types=notice_types,
                publish_date=publish_date,
                max_pages=args.max_pages,
            )
            print_progress({"event": "collect_done", **asdict(result)})
        finally:
            await maybe_close_client(client)

    if not args.skip_screen:
        print_progress({"event": "screen_start"})
        await run_screen_stage(args)

    if not args.skip_detail:
        print_progress({"event": "detail_start"})
        await run_detail_stage(args)

    if not args.skip_revalidate:
        print_progress({"event": "revalidate_start"})
        await run_revalidate_stage(args)

    print_progress({"event": "workflow_finished", **workflow_stats(args.sqlite_db)})


def main() -> None:
    asyncio.run(run_workflow(parse_args()))


if __name__ == "__main__":
    main()
