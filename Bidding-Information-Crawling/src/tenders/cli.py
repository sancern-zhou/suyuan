from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date

from .models import NoticeType
from .pipeline import TenderPipeline, maybe_close_client
from .qianlima_client import QianlimaClient
from .repository import AsyncpgTenderRepository, SQLiteTenderRepository
from .llm import OpenAICompatibleTenderLLMClient


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for env_file in [".env", ".env.native_llm", ".env.hybrid"]:
        load_dotenv(env_file, override=False)


def parse_notice_types(value: str) -> list[NoticeType]:
    mapping = {
        "tender": NoticeType.TENDER,
        "winning_bid": NoticeType.WINNING_BID,
        "change": NoticeType.CHANGE,
        "other": NoticeType.OTHER,
    }
    return [mapping[item.strip()] for item in value.split(",") if item.strip()]


async def run(args) -> None:
    keywords = [item.strip() for item in args.keywords.split(",") if item.strip()]
    notice_types = parse_notice_types(args.notice_types)
    client = QianlimaClient(
        base_url=args.base_url,
        storage_state_path=args.storage_state,
        headless=not args.show_browser,
    )
    try:
        if args.login:
            await client.login(args.login_url)
            if args.login_only:
                print(f"login state saved to {args.storage_state}")
                return

        repository = (
            AsyncpgTenderRepository(args.dsn)
            if args.dsn
            else SQLiteTenderRepository(args.sqlite_db)
        )
        llm_enabled = args.enable_llm and not args.disable_llm
        llm_client = OpenAICompatibleTenderLLMClient() if llm_enabled else None
        pipeline = TenderPipeline(
            client=client,
            repository=repository,
            llm_client=llm_client,
            enable_vector_index=args.enable_vector_index,
        )
        result = await pipeline.run_daily(
            keywords=keywords,
            notice_types=notice_types,
            publish_date=(
                date.fromisoformat(args.publish_date) if args.publish_date else None
            ),
            max_pages=args.max_pages,
        )
        print(
            "finished "
            f"candidates={result.total_candidates} "
            f"saved={result.saved_notices} "
            f"filtered={result.filtered_out} "
            f"duplicates={result.duplicate_candidates} "
            f"errors={len(result.errors)}"
        )
        if result.errors:
            for error in result.errors[:10]:
                print(f"error: {error}")
    finally:
        await maybe_close_client(client)


def main() -> None:
    load_environment()
    parser = argparse.ArgumentParser(
        description="Run Qianlima tender collection pipeline"
    )
    parser.add_argument(
        "--keywords", default=os.getenv("TENDER_KEYWORDS", "生态环境局")
    )
    parser.add_argument("--notice-types", default="tender,winning_bid")
    parser.add_argument("--publish-date", default=os.getenv("TENDER_PUBLISH_DATE", ""))
    parser.add_argument(
        "--max-pages",
        type=int,
        default=int(os.getenv("TENDER_MAX_PAGES", "1")),
        help="分页数；与 --publish-date 一起传 0 时，按日期自动翻页直到早于目标日期。",
    )
    parser.add_argument(
        "--base-url", default=os.getenv("QIANLIMA_BASE_URL", "https://www.qianlima.com")
    )
    parser.add_argument(
        "--storage-state",
        default=os.getenv("QIANLIMA_STORAGE_STATE", "data/qianlima_storage_state.json"),
    )
    parser.add_argument(
        "--dsn", default=os.getenv("TENDER_DATABASE_DSN") or os.getenv("DATABASE_URL")
    )
    parser.add_argument(
        "--sqlite-db", default=os.getenv("TENDER_SQLITE_DB", "data/tenders.db")
    )
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--login-only", action="store_true")
    parser.add_argument("--login-url", default=os.getenv("QIANLIMA_LOGIN_URL", ""))
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("--enable-vector-index", action="store_true")
    parser.add_argument(
        "--enable-llm",
        action="store_true",
        default=True,
        help="默认已启用，保留该参数用于兼容旧命令。",
    )
    parser.add_argument(
        "--disable-llm", action="store_true", help="禁用 LLM，改用本地规则兜底筛选。"
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
