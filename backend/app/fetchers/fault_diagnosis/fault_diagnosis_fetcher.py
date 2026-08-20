from __future__ import annotations

from pathlib import Path

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.fault_diagnosis import FaultDiagnosisService


logger = structlog.get_logger()


class FaultDiagnosisFetcher(DataFetcher):
    """Consume suspicious pollution event conclusions and write fault diagnosis packages."""

    def __init__(self, output_root: Path | None = None, limit: int = 20):
        super().__init__(
            name="fault_diagnosis_fetcher",
            description="疑似设备或数据故障污染告警原因诊断",
            schedule="10 * * * *",
            version="1.0.0",
        )
        self.output_root = output_root
        self.limit = limit

    async def fetch_and_store(self):
        try:
            # The graph is an optional, bounded hint source. If the binding or
            # snapshot is unavailable, retain the service's explicit fallback
            # metadata and continue with the evidence-pack diagnosis.
            from app.knowledge_base.graph_guidance import build_graph_guidance_provider
            from app.knowledge_base.project_bindings import resolve_project_knowledge_base_ids

            knowledge_base_ids = await resolve_project_knowledge_base_ids(
                "station_fault_diagnosis"
            )
            provider = await build_graph_guidance_provider(knowledge_base_ids)
            result = FaultDiagnosisService(
                output_root=self.output_root,
                knowledge_graph_guidance_provider=provider,
            ).run(limit=self.limit)
            logger.info(
                "fault_diagnosis_fetcher_completed",
                processed_count=result.get("processed_count", 0),
                output_root=result.get("output_root"),
                knowledge_graph_enabled=provider is not None,
            )
            return result
        except Exception as exc:
            logger.error("fault_diagnosis_fetcher_failed", error=str(exc), exc_info=True)
            raise
