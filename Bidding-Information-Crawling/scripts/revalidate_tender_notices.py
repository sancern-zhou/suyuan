from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tenders.cli import load_environment
from src.tenders.llm import OpenAICompatibleTenderLLMClient
from src.tenders.models import NoticeType, TenderCandidate, TenderFilterDecision
from src.tenders.repository import SQLiteTenderRepository


@dataclass(slots=True)
class NoticeReviewItem:
    candidate: TenderCandidate
    prior_decision: TenderFilterDecision
    raw_content: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Revalidate stored tender notices with detail text."
    )
    parser.add_argument("--sqlite-db", default="data/tenders_20260630_llm_full.db")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--workers", type=int, default=int(os.getenv("TENDER_REVALIDATE_WORKERS", "2"))
    )
    parser.add_argument("--keep-rejected-notices", action="store_true")
    return parser.parse_args()


def load_review_items(db_path: str, limit: int = 0) -> list[NoticeReviewItem]:
    query = """
        SELECT
            c.title, c.url, c.notice_type, c.keyword, c.source, c.publish_date,
            c.raw_list_text, c.metadata, c.filter_reason, c.filter_confidence,
            c.decision_source, n.raw_content
        FROM tender_notices n
        JOIN tender_candidates c ON c.url = n.url
        WHERE c.filter_status = 'accepted'
        ORDER BY n.id
    """
    params: tuple[int, ...] = ()
    if limit > 0:
        query += " LIMIT ?"
        params = (limit,)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [review_item_from_row(row) for row in rows]


def review_item_from_row(row: sqlite3.Row) -> NoticeReviewItem:
    candidate = TenderCandidate(
        title=row["title"],
        url=row["url"],
        notice_type=parse_notice_type(row["notice_type"]),
        keyword=row["keyword"] or "",
        source=row["source"] or "qianlima",
        publish_date=parse_date(row["publish_date"]),
        raw_list_text=row["raw_list_text"] or "",
        metadata=parse_json(row["metadata"]),
    )
    decision = TenderFilterDecision(
        is_relevant=True,
        reason=row["filter_reason"] or "LLM 初筛判定为相关项目",
        confidence=float(row["filter_confidence"] or 0.5),
        decision_source=row["decision_source"] or "llm",
    )
    return NoticeReviewItem(
        candidate=candidate,
        prior_decision=decision,
        raw_content=row["raw_content"] or "",
    )


def parse_notice_type(value: str | None) -> NoticeType:
    try:
        return NoticeType(value)
    except (TypeError, ValueError):
        return NoticeType.OTHER


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def delete_notice(db_path: str, url: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM tender_notices WHERE url = ?", (url,))


def print_progress(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


async def process_item(
    db_path: str,
    repository: SQLiteTenderRepository,
    llm_client: OpenAICompatibleTenderLLMClient,
    item: NoticeReviewItem,
    write_lock: asyncio.Lock,
    keep_rejected_notices: bool,
) -> tuple[bool, str | None]:
    try:
        decision = await llm_client.review_candidate(
            item.candidate,
            item.prior_decision,
            detail_text=item.raw_content,
        )
        async with write_lock:
            await repository.update_candidate_decision(item.candidate, decision)
            if not decision.is_relevant and not keep_rejected_notices:
                delete_notice(db_path, item.candidate.url)
        return decision.is_relevant, None
    except Exception as exc:
        return False, f"revalidate failed for {item.candidate.url}: {exc}"


async def run(args: argparse.Namespace) -> None:
    load_environment()
    db_path = str(Path(args.sqlite_db))
    items = load_review_items(db_path, args.limit)
    repository = SQLiteTenderRepository(db_path)
    llm_client = OpenAICompatibleTenderLLMClient()
    semaphore = asyncio.Semaphore(max(1, args.workers))
    write_lock = asyncio.Lock()
    reviewed = 0
    accepted = 0
    rejected = 0
    errors: list[str] = []

    print_progress(
        {
            "event": "start",
            "items": len(items),
            "workers": max(1, args.workers),
            "keep_rejected_notices": args.keep_rejected_notices,
            "db": db_path,
        }
    )

    async def run_one(item: NoticeReviewItem) -> tuple[bool, str | None]:
        async with semaphore:
            return await process_item(
                db_path,
                repository,
                llm_client,
                item,
                write_lock,
                args.keep_rejected_notices,
            )

    tasks = [asyncio.create_task(run_one(item)) for item in items]
    for task in asyncio.as_completed(tasks):
        is_relevant, error = await task
        reviewed += 1
        if error:
            errors.append(error)
            print_progress({"event": "error", "error": error})
        elif is_relevant:
            accepted += 1
        else:
            rejected += 1
        if reviewed % 10 == 0:
            print_progress(
                {
                    "event": "progress",
                    "reviewed": reviewed,
                    "accepted": accepted,
                    "rejected": rejected,
                    "errors": len(errors),
                }
            )

    print_progress(
        {
            "event": "finished",
            "reviewed": reviewed,
            "accepted": accepted,
            "rejected": rejected,
            "errors": len(errors),
        }
    )


def main() -> None:
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
