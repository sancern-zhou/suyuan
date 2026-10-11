"""Migrate knowledge-base relational data between project databases.

This intentionally excludes knowledge QA conversation history. It copies:
- knowledge_bases
- documents
- document PostgreSQL/Kingbase Large Objects referenced by documents.original_file_oid

Set TARGET_DATABASE_URL explicitly. SOURCE_DATABASE_URL defaults to DATABASE_URL
from backend/.env.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.kingbase_dialect import register_kingbase_dialect


register_kingbase_dialect()


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

SOURCE_DATABASE_URL = os.getenv("SOURCE_DATABASE_URL") or os.getenv("DATABASE_URL")
TARGET_DATABASE_URL = os.getenv("TARGET_DATABASE_URL")

CONNECT_ARGS = {
    "command_timeout": 300,
    "server_settings": {
        "statement_timeout": "300000",
    },
}

KB_COLUMNS = [
    "id",
    "name",
    "description",
    "kb_type",
    "owner_id",
    "is_default",
    "embedding_model",
    "chunking_strategy",
    "chunk_size",
    "chunk_overlap",
    "qdrant_collection",
    "status",
    "document_count",
    "chunk_count",
    "total_size",
    "created_at",
    "updated_at",
]

DOCUMENT_COLUMNS = [
    "id",
    "knowledge_base_id",
    "filename",
    "file_path",
    "file_type",
    "file_size",
    "file_hash",
    "original_file_oid",
    "file_storage_type",
    "file_mime_type",
    "file_checksum",
    "storage_size",
    "file_preview_text",
    "status",
    "chunk_count",
    "error_message",
    "retry_count",
    "extra_metadata",
    "created_at",
    "processed_at",
    "updated_at",
]


def _insert_sql(table: str, columns: list[str]) -> str:
    column_sql = ", ".join(columns)
    value_sql = ", ".join(f":{column}" for column in columns)
    return f"insert into {table} ({column_sql}) values ({value_sql})"


async def _copy_large_object(source_conn, target_conn, loid: int | None) -> int | None:
    if not loid:
        return None

    data = (
        await source_conn.execute(
            text("select lo_get(:loid)"),
            {"loid": int(loid)},
        )
    ).scalar()
    if data is None:
        return None

    new_loid = (
        await target_conn.execute(text("select lo_create(0)"))
    ).scalar()
    await target_conn.execute(
        text("select lo_put(:loid, 0, :data)"),
        {"loid": int(new_loid), "data": data},
    )
    return int(new_loid)


def _as_mapping(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


async def migrate() -> None:
    if not SOURCE_DATABASE_URL:
        raise RuntimeError("SOURCE_DATABASE_URL or DATABASE_URL is required")
    if not TARGET_DATABASE_URL:
        raise RuntimeError("TARGET_DATABASE_URL is required")

    source_engine = create_async_engine(SOURCE_DATABASE_URL, connect_args=CONNECT_ARGS)
    target_engine = create_async_engine(TARGET_DATABASE_URL, connect_args=CONNECT_ARGS)

    try:
        async with source_engine.connect() as source_conn:
            async with target_engine.begin() as target_conn:
                await target_conn.execute(text("delete from documents"))
                await target_conn.execute(text("delete from knowledge_bases"))

                kb_rows = (
                    await source_conn.execute(
                        text(f"select {', '.join(KB_COLUMNS)} from knowledge_bases order by created_at")
                    )
                ).all()
                for row in kb_rows:
                    await target_conn.execute(
                        text(_insert_sql("knowledge_bases", KB_COLUMNS)),
                        _as_mapping(row),
                    )

                document_rows = (
                    await source_conn.execute(
                        text(f"select {', '.join(DOCUMENT_COLUMNS)} from documents order by created_at")
                    )
                ).all()
                copied_lobs = 0
                for row in document_rows:
                    document = _as_mapping(row)
                    document["extra_metadata"] = _normalize_json(
                        document.get("extra_metadata")
                    )
                    new_loid = await _copy_large_object(
                        source_conn,
                        target_conn,
                        document.get("original_file_oid"),
                    )
                    if new_loid:
                        copied_lobs += 1
                        document["original_file_oid"] = new_loid
                    await target_conn.execute(
                        text(_insert_sql("documents", DOCUMENT_COLUMNS)),
                        document,
                    )

                print(f"knowledge_bases={len(kb_rows)}")
                print(f"documents={len(document_rows)}")
                print(f"large_objects={copied_lobs}")
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
