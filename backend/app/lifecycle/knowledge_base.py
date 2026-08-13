"""Knowledge base lifecycle extracted from app/main.py.

Dependency note:
- The processing queue uses database sessions, so start it only after database
  initialization and stop it before closing the database.
- Model warmup is best-effort and should not block application startup on error.
"""

import asyncio
import os
import time

import structlog

logger = structlog.get_logger()


def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def start_document_processing_queue() -> None:
    """Start the upload-processing queue for API workers."""
    from app.knowledge_base.tasks import start_processing_queue

    await start_processing_queue()
    logger.info("knowledge_base_processing_queue_started")


async def stop_document_processing_queue() -> None:
    """Stop the upload-processing queue before database shutdown."""
    from app.knowledge_base.tasks import stop_processing_queue

    await stop_processing_queue()
    logger.info("knowledge_base_processing_queue_stopped")
    await asyncio.sleep(1.0)


async def start_knowledge_base_services() -> None:
    """Start knowledge base processing queue and warm up retrieval models."""
    try:
        await start_document_processing_queue()
    except Exception as e:
        logger.warning("knowledge_base_queue_start_failed", error=str(e))

    if _env_flag("KNOWLEDGE_BASE_INDEX_OUTBOX_ON_STARTUP"):
        try:
            from app.knowledge_base.index_outbox import start_index_outbox_worker

            await start_index_outbox_worker()
        except Exception as e:
            logger.warning("knowledge_index_outbox_start_failed", error=str(e))
    else:
        logger.info("knowledge_index_outbox_worker_skipped", reason="disabled_on_startup")

    await warmup_knowledge_base_models_if_enabled()


async def warmup_knowledge_base_models_if_enabled() -> None:
    if not _env_flag("KNOWLEDGE_BASE_WARMUP_ON_STARTUP"):
        logger.info("knowledge_base_warmup_skipped", reason="disabled_on_startup")
        return

    try:
        await warmup_knowledge_base_models()
    except Exception as e:
        logger.warning("knowledge_base_warmup_failed", error=str(e))


async def warmup_knowledge_base_models() -> None:
    """Warm up shared retrieval models without enabling reranking by default."""
    start = time.time()
    logger.info("knowledge_base_models_warmup_starting")

    try:
        from app.knowledge_base import get_vector_store

        vector_store = get_vector_store()
        # The runtime object is a router. Warm only the shared model because
        # it is used by every branch; local Qdrant stays lazy until a local
        # knowledge base is actually queried or indexed.
        resolver = getattr(vector_store, "for_scope", None)
        vector_store = resolver("shared") if resolver is not None else vector_store
        _ = vector_store.embedding_model.encode(["预热测试"], show_progress_bar=False)
        logger.info("embedding_model_warmed_up", storage_scope="shared")
    except Exception as e:
        logger.warning("embedding_warmup_failed", error=str(e))

    if _env_flag("KNOWLEDGE_BASE_RERANKER_WARMUP_ON_STARTUP", default=False):
        try:
            from app.knowledge_base.service import get_reranker

            reranker = get_reranker()
            if reranker:
                await asyncio.to_thread(reranker.predict, [("预热", "测试")])
                logger.info("reranker_model_warmed_up")
            else:
                logger.info("reranker_warmup_skipped", reason="reranker_not_available")
        except Exception as e:
            logger.warning("reranker_warmup_failed", error=str(e))
    else:
        logger.info("reranker_warmup_skipped", reason="disabled_on_startup")

    elapsed = time.time() - start
    logger.info("knowledge_base_models_warmup_completed", elapsed_seconds=round(elapsed, 2))


async def stop_knowledge_base_services() -> None:
    """Stop knowledge base processing queue before database shutdown."""
    try:
        from app.knowledge_base.index_outbox import stop_index_outbox_worker

        await stop_index_outbox_worker()
    except Exception as e:
        logger.warning("knowledge_index_outbox_stop_failed", error=str(e))

    try:
        await stop_document_processing_queue()
    except Exception as e:
        logger.warning("knowledge_base_queue_stop_failed", error=str(e))
