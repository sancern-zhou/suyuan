"""Fact-driven expert deliberation API."""

from fastapi import APIRouter, HTTPException
import structlog

from app.services.expert_deliberation import ExpertDeliberationEngine
from app.services.expert_deliberation.schemas import DeliberationRequest, DeliberationResult

logger = structlog.get_logger()

router = APIRouter(prefix="/expert-deliberation", tags=["expert-deliberation"])


@router.post("/run", response_model=DeliberationResult)
async def run_deliberation(request: DeliberationRequest) -> DeliberationResult:
    """Run a fact-driven expert deliberation."""
    try:
        logger.info(
            "expert_deliberation_started",
            topic=request.topic,
            region=request.region,
            tables=len(request.consultation_tables),
            data_ids=len(request.data_ids),
        )
        result = ExpertDeliberationEngine().run(request)
        logger.info(
            "expert_deliberation_completed",
            facts=len(result.facts),
            analyses=len(result.analyses),
            conclusions=len(result.conclusions),
        )
        return result
    except Exception as exc:
        logger.error("expert_deliberation_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "expert-deliberation",
        "version": "0.1.0",
    }

