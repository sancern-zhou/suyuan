"""Persistence for raw graph-extraction responses and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.scene_models import KnowledgeGraphExtractionRun


@dataclass(frozen=True)
class ExtractionRunContext:
    kb_id: str
    document_id: str
    chunk_id: str
    content_generation: int
    scene_profile_version: int
    schema_version: int
    prompt_version: str
    model_name: str
    model_params: dict = field(default_factory=dict)


class ExtractionRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def start(self, context: ExtractionRunContext) -> str:
        run = KnowledgeGraphExtractionRun(
            **context.__dict__,
            status="running",
        )
        self.session.add(run)
        await self.session.commit()
        return run.id

    async def complete(
        self,
        run_id: str,
        *,
        raw_response: dict,
        parsed_response: dict,
        token_usage: dict,
        latency_ms: int,
    ) -> None:
        await self._terminal_update(
            run_id,
            status="completed",
            raw_response=raw_response,
            parsed_response=parsed_response,
            token_usage=token_usage,
            latency_ms=latency_ms,
            validation_errors=[],
        )

    async def fail(
        self,
        run_id: str,
        *,
        raw_response: dict,
        validation_errors: list[str],
        latency_ms: int,
    ) -> None:
        await self._terminal_update(
            run_id,
            status="failed",
            raw_response=raw_response,
            parsed_response={},
            token_usage={},
            latency_ms=latency_ms,
            validation_errors=validation_errors,
        )

    async def get(self, run_id: str) -> KnowledgeGraphExtractionRun | None:
        return await self.session.get(KnowledgeGraphExtractionRun, run_id)

    async def _terminal_update(self, run_id: str, **values) -> None:
        result = await self.session.execute(
            update(KnowledgeGraphExtractionRun)
            .where(
                KnowledgeGraphExtractionRun.id == run_id,
                KnowledgeGraphExtractionRun.status == "running",
            )
            .values(**values)
        )
        if not result.rowcount:
            raise ValueError("extraction_run_not_running")
        await self.session.commit()
