from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tenders.cli import load_environment
from src.tenders.llm import OpenAICompatibleTenderLLMClient
from src.tenders.models import (
    NoticeType,
    PipelineRunResult,
    TenderCandidate,
    TenderFilterDecision,
)
from src.tenders.pipeline import maybe_close_client
from src.tenders.qianlima_client import QianlimaClient
from src.tenders.repository import SQLiteTenderRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resume pending tender LLM review and storage."
    )
    parser.add_argument("--sqlite-db", default="data/tenders_20260630_llm_full.db")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--batch-size", type=int, default=int(os.getenv("TENDER_LLM_BATCH_SIZE", "60"))
    )
    parser.add_argument(
        "--batch-delay-ms",
        type=int,
        default=int(os.getenv("TENDER_LLM_BATCH_DELAY_MS", "500")),
    )
    parser.add_argument(
        "--candidate-delay-ms",
        type=int,
        default=int(os.getenv("TENDER_CANDIDATE_DELAY_MS", "0")),
    )
    parser.add_argument(
        "--storage-state",
        default=os.getenv("QIANLIMA_STORAGE_STATE", "data/qianlima_storage_state.json"),
    )
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--screen-only", action="store_true")
    parser.add_argument("--accepted-missing", action="store_true")
    parser.add_argument("--skip-detail-review", action="store_true")
    parser.add_argument(
        "--workers", type=int, default=int(os.getenv("TENDER_DETAIL_WORKERS", "1"))
    )
    return parser.parse_args()


def load_pending_candidates(db_path: str, limit: int = 0) -> list[TenderCandidate]:
    query = """
        SELECT title, url, notice_type, keyword, source, publish_date, raw_list_text, metadata
        FROM tender_candidates
        WHERE filter_status = 'pending'
        ORDER BY id
    """
    params: tuple[int, ...] = ()
    if limit > 0:
        query += " LIMIT ?"
        params = (limit,)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [candidate_from_row(row) for row in rows]


def load_accepted_missing_candidates(
    db_path: str, limit: int = 0
) -> list[tuple[TenderCandidate, TenderFilterDecision]]:
    query = """
        SELECT
            c.title, c.url, c.notice_type, c.keyword, c.source, c.publish_date,
            c.raw_list_text, c.metadata, c.filter_reason, c.filter_confidence, c.decision_source
        FROM tender_candidates c
        LEFT JOIN tender_notices n ON c.url = n.url
        WHERE c.filter_status = 'accepted' AND n.url IS NULL
        ORDER BY c.id
    """
    params: tuple[int, ...] = ()
    if limit > 0:
        query += " LIMIT ?"
        params = (limit,)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [(candidate_from_row(row), decision_from_row(row)) for row in rows]


def candidate_from_row(row: sqlite3.Row) -> TenderCandidate:
    try:
        notice_type = NoticeType(row["notice_type"])
    except (TypeError, ValueError):
        notice_type = NoticeType.OTHER
    return TenderCandidate(
        title=row["title"],
        url=row["url"],
        notice_type=notice_type,
        keyword=row["keyword"] or "",
        source=row["source"] or "qianlima",
        publish_date=parse_date(row["publish_date"]),
        raw_list_text=row["raw_list_text"] or "",
        metadata=parse_json(row["metadata"]),
    )


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


def decision_from_row(row: sqlite3.Row) -> TenderFilterDecision:
    return TenderFilterDecision(
        is_relevant=True,
        reason=row["filter_reason"] or "LLM 初筛判定为相关项目",
        confidence=float(row["filter_confidence"] or 0.5),
        decision_source=row["decision_source"] or "llm",
    )


def chunked(items: list[TenderCandidate], size: int) -> Iterable[list[TenderCandidate]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def pending_llm_decision() -> TenderFilterDecision:
    return TenderFilterDecision(
        is_relevant=True,
        reason="等待 LLM 基于招投标语义判断",
        confidence=0.0,
        decision_source="pending_llm",
    )


def print_progress(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


async def review_batch(
    llm_client: OpenAICompatibleTenderLLMClient,
    candidates: list[TenderCandidate],
) -> dict[str, TenderFilterDecision]:
    try:
        return await llm_client.review_candidates(candidates, pending_llm_decision())
    except Exception as exc:
        print_progress({"event": "batch_review_failed", "error": str(exc)})
        return {}


async def ensure_decision(
    llm_client: OpenAICompatibleTenderLLMClient,
    candidate: TenderCandidate,
    batch_decisions: dict[str, TenderFilterDecision],
) -> TenderFilterDecision:
    decision = batch_decisions.get(candidate.normalized_url_key())
    if decision is not None:
        return decision
    return await llm_client.review_candidate(candidate, pending_llm_decision())


async def process_detail(
    client: QianlimaClient,
    repository: SQLiteTenderRepository,
    llm_client: OpenAICompatibleTenderLLMClient,
    candidate: TenderCandidate,
    initial_decision: TenderFilterDecision,
    skip_detail_review: bool = False,
) -> tuple[bool, bool, str | None]:
    try:
        detail_html = await client.fetch_detail(candidate)
    except Exception as exc:
        return False, False, f"detail fetch failed for {candidate.url}: {exc}"

    try:
        if skip_detail_review:
            detail_decision = initial_decision
        else:
            detail_decision = await llm_client.review_candidate(
                candidate, initial_decision, detail_text=detail_html
            )
        await repository.update_candidate_decision(candidate, detail_decision)
        if not detail_decision.is_relevant:
            return True, False, None
        notice = await llm_client.extract_notice(
            candidate, detail_html, detail_decision
        )
        await repository.save_notice(notice)
        return True, True, None
    except Exception as exc:
        return False, False, f"detail processing failed for {candidate.url}: {exc}"


async def run(args: argparse.Namespace) -> PipelineRunResult:
    load_environment()
    db_path = str(Path(args.sqlite_db))
    accepted_missing = (
        load_accepted_missing_candidates(db_path, args.limit)
        if args.accepted_missing
        else []
    )
    candidates = (
        [] if args.accepted_missing else load_pending_candidates(db_path, args.limit)
    )
    repository = SQLiteTenderRepository(db_path)
    llm_client = OpenAICompatibleTenderLLMClient()
    client = QianlimaClient(
        storage_state_path=args.storage_state, headless=not args.show_browser
    )
    result = PipelineRunResult(
        total_candidates=(
            len(accepted_missing) if args.accepted_missing else len(candidates)
        )
    )
    reviewed = 0

    print_progress(
        {
            "event": "start",
            "mode": (
                "accepted_missing"
                if args.accepted_missing
                else "screen_only" if args.screen_only else "full"
            ),
            "pending": len(candidates),
            "accepted_missing": len(accepted_missing),
            "db": db_path,
        }
    )
    try:
        if args.accepted_missing:
            semaphore = asyncio.Semaphore(max(1, args.workers))

            async def run_one(item: tuple[TenderCandidate, TenderFilterDecision]):
                candidate, decision = item
                async with semaphore:
                    outcome = await process_detail(
                        client,
                        repository,
                        llm_client,
                        candidate,
                        decision,
                        skip_detail_review=args.skip_detail_review,
                    )
                    if args.candidate_delay_ms > 0:
                        await asyncio.sleep(args.candidate_delay_ms / 1000)
                    return outcome

            tasks = [asyncio.create_task(run_one(item)) for item in accepted_missing]
            for task in asyncio.as_completed(tasks):
                detail_ok, saved, error = await task
                reviewed += 1
                if error:
                    result.errors.append(error)
                    print_progress({"event": "detail_error", "error": error})
                if not detail_ok:
                    result.detail_fetch_failures += 1
                    continue
                if saved:
                    result.saved_notices += 1
                else:
                    result.filtered_out += 1
                if reviewed % 10 == 0:
                    print_progress(
                        {
                            "event": "accepted_missing_progress",
                            "reviewed": reviewed,
                            "saved_in_run": result.saved_notices,
                            "filtered_in_run": result.filtered_out,
                            "errors_in_run": len(result.errors),
                        }
                    )
            print_progress(
                {
                    "event": "finished",
                    "reviewed": reviewed,
                    "saved_in_run": result.saved_notices,
                    "filtered_in_run": result.filtered_out,
                    "detail_failures": result.detail_fetch_failures,
                    "errors": len(result.errors),
                }
            )
            return result

        for batch_index, batch in enumerate(
            chunked(candidates, max(1, args.batch_size)), start=1
        ):
            batch_decisions = await review_batch(llm_client, batch)
            accepted_for_detail: list[tuple[TenderCandidate, TenderFilterDecision]] = []

            for candidate in batch:
                try:
                    decision = await ensure_decision(
                        llm_client, candidate, batch_decisions
                    )
                    await repository.update_candidate_decision(candidate, decision)
                    reviewed += 1
                    if decision.is_relevant:
                        accepted_for_detail.append((candidate, decision))
                    else:
                        result.filtered_out += 1
                except Exception as exc:
                    message = f"candidate review failed for {candidate.url}: {exc}"
                    result.errors.append(message)
                    print_progress({"event": "review_error", "error": message})

            if args.screen_only:
                print_progress(
                    {
                        "event": "batch_done",
                        "batch": batch_index,
                        "reviewed": reviewed,
                        "accepted_for_detail": len(accepted_for_detail),
                        "saved_in_run": result.saved_notices,
                        "filtered_in_run": result.filtered_out,
                        "errors_in_run": len(result.errors),
                    }
                )
                if args.batch_delay_ms > 0 and reviewed < len(candidates):
                    await asyncio.sleep(args.batch_delay_ms / 1000)
                continue

            for candidate, decision in accepted_for_detail:
                detail_ok, saved, error = await process_detail(
                    client,
                    repository,
                    llm_client,
                    candidate,
                    decision,
                    skip_detail_review=args.skip_detail_review,
                )
                if error:
                    result.errors.append(error)
                    print_progress({"event": "detail_error", "error": error})
                if not detail_ok:
                    result.detail_fetch_failures += 1
                    continue
                if saved:
                    result.saved_notices += 1
                else:
                    result.filtered_out += 1
                if args.candidate_delay_ms > 0:
                    await asyncio.sleep(args.candidate_delay_ms / 1000)

            print_progress(
                {
                    "event": "batch_done",
                    "batch": batch_index,
                    "reviewed": reviewed,
                    "accepted_for_detail": len(accepted_for_detail),
                    "saved_in_run": result.saved_notices,
                    "filtered_in_run": result.filtered_out,
                    "errors_in_run": len(result.errors),
                }
            )
            if args.batch_delay_ms > 0 and reviewed < len(candidates):
                await asyncio.sleep(args.batch_delay_ms / 1000)
    finally:
        await maybe_close_client(client)

    print_progress(
        {
            "event": "finished",
            "reviewed": reviewed,
            "saved_in_run": result.saved_notices,
            "filtered_in_run": result.filtered_out,
            "detail_failures": result.detail_fetch_failures,
            "errors": len(result.errors),
        }
    )
    return result


def main() -> None:
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
