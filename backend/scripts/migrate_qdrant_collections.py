"""Copy Qdrant collections from the configured remote service to local storage."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

TARGET_QDRANT_PATH = Path(os.getenv("TARGET_QDRANT_PATH", "/opt/qdrant/storage"))


def source_client() -> QdrantClient:
    host = os.getenv("SOURCE_QDRANT_HOST") or os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("SOURCE_QDRANT_PORT") or os.getenv("QDRANT_PORT", "6333"))
    api_key = os.getenv("SOURCE_QDRANT_API_KEY")
    if api_key is None:
        api_key = os.getenv("QDRANT_API_KEY") or None
    use_https = (os.getenv("SOURCE_QDRANT_HTTPS") or os.getenv("QDRANT_HTTPS", "false")).lower() == "true"
    protocol = "https" if use_https else "http"
    return QdrantClient(
        url=f"{protocol}://{host}:{port}",
        api_key=api_key,
        timeout=int(os.getenv("QDRANT_TIMEOUT", "300")),
    )


def target_client() -> QdrantClient:
    TARGET_QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(TARGET_QDRANT_PATH))


def collection_names() -> list[str]:
    explicit = os.getenv("QDRANT_COLLECTIONS")
    if explicit:
        return [name.strip() for name in explicit.split(",") if name.strip()]

    import asyncio
    from app.db.database import engine
    from sqlalchemy import text

    async def load_names() -> list[str]:
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text("select qdrant_collection from knowledge_bases order by created_at")
                    )
                ).all()
                return [row[0] for row in rows if row[0]]
        finally:
            await engine.dispose()

    return asyncio.run(load_names())


def migrate_collection(source: QdrantClient, target: QdrantClient, collection: str) -> int:
    info = source.get_collection(collection)
    params = info.config.params

    existing = {item.name for item in target.get_collections().collections}
    if collection in existing:
        target.delete_collection(collection)

    target.create_collection(
        collection_name=collection,
        vectors_config=params.vectors,
        sparse_vectors_config=getattr(params, "sparse_vectors", None),
    )

    copied = 0
    offset = None
    while True:
        records, offset = source.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if records:
            target.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=record.id,
                        vector=record.vector,
                        payload=record.payload,
                    )
                    for record in records
                ],
            )
            copied += len(records)
        if offset is None:
            return copied


def main() -> None:
    source = source_client()
    target = target_client()
    for collection in collection_names():
        copied = migrate_collection(source, target, collection)
        print(f"{collection}: {copied}")


if __name__ == "__main__":
    main()
