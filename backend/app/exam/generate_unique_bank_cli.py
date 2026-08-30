"""Plan, run, resume, and inspect unique-chunk exam-bank generation jobs."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.db.database import async_session
from app.exam.batch_generation import (
    create_generation_job,
    generation_job_summary,
    load_generation_job,
    run_generation_job,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Create a read-only source plan and checkpoint")
    plan.add_argument("--target-count", type=int, default=200)
    plan.add_argument("--primary-count", type=int, default=320)
    plan.add_argument("--reserve-count", type=int, default=80)
    plan.add_argument("--model-tier", choices=("auto", "flash", "pro"), default="auto")
    plan.add_argument("--min-chunk-chars", type=int, default=100)
    plan.add_argument("--chunk-similarity-threshold", type=float, default=0.90)
    plan.add_argument("--question-similarity-threshold", type=float, default=0.90)

    run = subparsers.add_parser("run", help="Run or resume committed generation batches")
    run.add_argument("--job-id", required=True)
    run.add_argument("--batch-size", type=int, default=8)
    run.add_argument("--max-batches", type=int)

    status = subparsers.add_parser("status", help="Show a saved job checkpoint")
    status.add_argument("--job-id", required=True)
    return parser


async def _run(args: argparse.Namespace) -> dict:
    if args.command == "status":
        return generation_job_summary(load_generation_job(args.job_id))
    if args.command == "run":
        return await run_generation_job(
            async_session,
            job_id=args.job_id,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )
    async with async_session() as session:
        job = await create_generation_job(
            session,
            target_count=args.target_count,
            primary_count=args.primary_count,
            reserve_count=args.reserve_count,
            model_tier=args.model_tier,
            min_chunk_chars=args.min_chunk_chars,
            chunk_similarity_threshold=args.chunk_similarity_threshold,
            question_similarity_threshold=args.question_similarity_threshold,
        )
    return generation_job_summary(job)


def main() -> None:
    result = asyncio.run(_run(build_parser().parse_args()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

