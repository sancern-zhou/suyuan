"""Shared knowledge metadata database routing.

Project deployments may keep their operational data in an isolated database
while reading centrally published knowledge bases.  Qdrant routing alone is
not sufficient: collection names, documents, and chunks live in PostgreSQL.
This module provides a read-only route to that central metadata database.
"""

from contextlib import asynccontextmanager
from functools import lru_cache
import os
from typing import AsyncIterator, Iterable, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import DATABASE_URL, async_session, _normalize_async_database_url

from .models import KnowledgeBase, KnowledgeBaseStatus, KnowledgeBaseStorageScope

logger = structlog.get_logger()


def _build_shared_database_url() -> Optional[str]:
    """Return the configured central metadata URL without logging credentials."""
    explicit_url = os.getenv("SHARED_KNOWLEDGE_DATABASE_URL", "").strip()
    if explicit_url:
        return _normalize_async_database_url(explicit_url)

    database_name = os.getenv("SHARED_KNOWLEDGE_DATABASE_NAME", "").strip()
    if not database_name:
        return None

    return make_url(DATABASE_URL).set(database=database_name).render_as_string(
        hide_password=False
    )


@lru_cache(maxsize=1)
def get_shared_knowledge_session_factory():
    """Return a lazy session factory when central metadata is separately stored."""
    shared_url = _build_shared_database_url()
    if not shared_url or make_url(shared_url) == make_url(DATABASE_URL):
        return None

    engine = create_async_engine(
        shared_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_timeout=120,
        connect_args={
            "command_timeout": 300,
            "server_settings": {"statement_timeout": "300000"},
        },
    )
    logger.info(
        "shared_knowledge_metadata_route_configured",
        database=make_url(shared_url).database,
    )
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def list_central_shared_knowledge_bases(
    *, status: Optional[KnowledgeBaseStatus] = None
) -> list[KnowledgeBase]:
    """List centrally published shared knowledge bases, if configured."""
    factory = get_shared_knowledge_session_factory()
    if factory is None:
        return []

    query = select(KnowledgeBase).where(
        KnowledgeBase.vector_store_scope == KnowledgeBaseStorageScope.SHARED
    )
    if status is not None:
        query = query.where(KnowledgeBase.status == status)
    query = query.order_by(
        KnowledgeBase.is_default.desc(), KnowledgeBase.created_at.desc()
    )
    async with factory() as db:
        result = await db.execute(query)
        return list(result.scalars().all())


async def get_central_shared_knowledge_base_ids(
    knowledge_base_ids: Iterable[str],
) -> set[str]:
    """Return IDs that belong to the central shared metadata database."""
    requested_ids = list(dict.fromkeys(knowledge_base_ids))
    factory = get_shared_knowledge_session_factory()
    if factory is None or not requested_ids:
        return set()

    async with factory() as db:
        result = await db.execute(
            select(KnowledgeBase.id).where(
                KnowledgeBase.id.in_(requested_ids),
                KnowledgeBase.vector_store_scope == KnowledgeBaseStorageScope.SHARED,
                KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
            )
        )
        return set(result.scalars().all())


@asynccontextmanager
async def knowledge_base_read_session(kb_id: str) -> AsyncIterator[AsyncSession]:
    """Open the database that owns a knowledge base's readable metadata."""
    factory = get_shared_knowledge_session_factory()
    if factory is not None:
        async with factory() as central_db:
            result = await central_db.execute(
                select(KnowledgeBase.id).where(
                    KnowledgeBase.id == kb_id,
                    KnowledgeBase.vector_store_scope == KnowledgeBaseStorageScope.SHARED,
                )
            )
            if result.scalar_one_or_none() is not None:
                yield central_db
                return

    async with async_session() as local_db:
        yield local_db
