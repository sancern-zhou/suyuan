"""Generate model-reviewed draft exam questions from one knowledge-base document."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.db.database import async_session
from app.exam.bank_generation import ExamBankGenerationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--user-id", help="私有知识库所有者ID；公共知识库可省略")
    parser.add_argument("--max-chars-per-batch", type=int, default=12000)
    return parser


async def run(args: argparse.Namespace) -> dict:
    async with async_session() as session:
        async with session.begin():
            return await ExamBankGenerationService(session).generate_document(
                knowledge_base_id=args.knowledge_base_id,
                document_id=args.document_id,
                user_id=args.user_id,
                max_chars_per_batch=args.max_chars_per_batch,
            )


def main() -> None:
    result = asyncio.run(run(build_parser().parse_args()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
