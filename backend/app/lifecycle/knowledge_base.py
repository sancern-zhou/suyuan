"""Knowledge base lifecycle extracted from app/main.py.

Dependency note:
- The processing queue uses database sessions, so start it only after database
  initialization and stop it before closing the database.
- Model warmup is best-effort and should not block application startup on error.
"""

import asyncio
import time

import structlog

logger = structlog.get_logger()


async def start_knowledge_base_services() -> None:
    """Start knowledge base processing queue and warm up retrieval models."""
    try:
        from app.knowledge_base.tasks import start_processing_queue

        await start_processing_queue()
        logger.info("knowledge_base_processing_queue_started")
    except Exception as e:
        logger.warning("knowledge_base_queue_start_failed", error=str(e))

    try:
        await warmup_knowledge_base_models()
    except Exception as e:
        logger.warning("knowledge_base_warmup_failed", error=str(e))


async def warmup_knowledge_base_models() -> None:
    """Warm up embedding and reranker models to avoid first-query latency."""
    start = time.time()
    logger.info("knowledge_base_models_warmup_starting")

    try:
        from app.knowledge_base import get_vector_store

        vector_store = get_vector_store()
        _ = vector_store.embedding_model.encode(["预热测试"], show_progress_bar=False)
        logger.info("embedding_model_warmed_up")
    except Exception as e:
        logger.warning("embedding_warmup_failed", error=str(e))

    try:
        from app.knowledge_base.service import get_reranker

        reranker = get_reranker()
        if reranker:
            _ = reranker.predict([("预热", "测试")])
            logger.info("reranker_model_warmed_up")
        else:
            logger.info("reranker_warmup_skipped", reason="reranker_not_available")
    except Exception as e:
        logger.warning("reranker_warmup_failed", error=str(e))

    elapsed = time.time() - start
    logger.info("knowledge_base_models_warmup_completed", elapsed_seconds=round(elapsed, 2))


async def stop_knowledge_base_services() -> None:
    """Stop knowledge base processing queue before database shutdown."""
    try:
        from app.knowledge_base.tasks import stop_processing_queue

        await stop_processing_queue()
        logger.info("knowledge_base_processing_queue_stopped")
        await asyncio.sleep(1.0)
    except Exception as e:
        logger.warning("knowledge_base_queue_stop_failed", error=str(e))

