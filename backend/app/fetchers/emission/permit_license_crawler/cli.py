from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .client import PermitPlatformClient, PlatformBlockedError
from .crawler import XuchangPermitCrawler
from .repository import PermitRepository
from .storage import FileStorage


def validate_args(args: argparse.Namespace) -> None:
    if args.phase == "list" and (args.max_pages is None or args.max_pages < 1):
        raise ValueError("list phase requires a positive --max-pages")
    if args.phase == "detail" and (args.max_licenses is None or args.max_licenses < 1):
        raise ValueError("detail phase requires a positive --max-licenses")
    if args.min_delay_seconds < 0 or args.max_delay_seconds < args.min_delay_seconds:
        raise ValueError("invalid delay range")


def build_parser() -> argparse.ArgumentParser:
    backend_root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="低速分批采集许昌市排污许可证公开数据")
    parser.add_argument("--phase", choices=("list", "detail"), required=True)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--max-licenses", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--min-delay-seconds", type=float, default=2.0)
    parser.add_argument("--max-delay-seconds", type=float, default=5.0)
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=backend_root / "backend_data_registry" / "permit_licenses" / "河南省" / "许昌市",
    )
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    from app.db.database import async_session

    validate_args(args)
    async with async_session() as session:
        repository = PermitRepository(session)
        effective_start_page = args.start_page
        if args.phase == "list" and args.resume:
            effective_start_page = await repository.next_list_page(start_page=args.start_page)
        run_row = await repository.create_run(
            phase=args.phase,
            start_page=effective_start_page if args.phase == "list" else None,
            max_pages=args.max_pages,
            max_licenses=args.max_licenses,
        )
        await session.commit()
        run_id = run_row.id
        status = "completed"
        reason = None
        try:
            async with PermitPlatformClient(
                min_delay_seconds=args.min_delay_seconds,
                max_delay_seconds=args.max_delay_seconds,
            ) as client:
                crawler = XuchangPermitCrawler(
                    client=client,
                    repository=repository,
                    storage=FileStorage(args.storage_root),
                )
                if args.phase == "list":
                    await crawler.crawl_list(
                        start_page=effective_start_page,
                        max_pages=args.max_pages,
                        run=run_row,
                    )
                else:
                    run_row = await crawler.crawl_details(
                        max_licenses=args.max_licenses,
                        resume=args.resume,
                        run=run_row,
                    )
        except PlatformBlockedError as exc:
            await session.rollback()
            run_row = await session.get(type(run_row), run_id)
            status = "blocked"
            reason = str(exc)
        except Exception as exc:
            await session.rollback()
            run_row = await session.get(type(run_row), run_id)
            status = "failed"
            reason = str(exc)
            await repository.record_failure(run_row, stage=args.phase, error=exc)
            run_row.failure_count += 1
        await repository.finish_run(run_row, status=status, reason=reason)
        await session.commit()
        return {
            "run_id": run_row.id,
            "phase": run_row.phase,
            "status": run_row.status,
            "success_count": run_row.success_count,
            "failure_count": run_row.failure_count,
            "skipped_count": run_row.skipped_count,
            "stop_reason": run_row.stop_reason,
            "storage_root": str(args.storage_root),
        }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    summary = asyncio.run(run(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
