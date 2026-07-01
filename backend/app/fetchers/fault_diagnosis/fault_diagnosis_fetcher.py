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
            schedule="*/30 * * * *",
            version="1.0.0",
        )
        self.output_root = output_root
        self.limit = limit

    async def fetch_and_store(self):
        try:
            result = FaultDiagnosisService(output_root=self.output_root).run(limit=self.limit)
            logger.info(
                "fault_diagnosis_fetcher_completed",
                processed_count=result.get("processed_count", 0),
                output_root=result.get("output_root"),
            )
            return result
        except Exception as exc:
            logger.error("fault_diagnosis_fetcher_failed", error=str(exc), exc_info=True)
            raise
