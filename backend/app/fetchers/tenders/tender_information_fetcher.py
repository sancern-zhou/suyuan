from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.services.tenders.config import (
    TenderFetcherConfig,
    default_target_date,
    parse_keywords,
    parse_notice_types,
)
from app.services.tenders.llm import OpenAICompatibleTenderLLMClient, TenderLLMClientPool
from app.services.tenders.pipeline import TenderPipeline, maybe_close_client
from app.services.tenders.qianlima_client import QianlimaClient
from app.services.tenders.repository import SQLServerTenderRepository
from config.settings import settings

logger = structlog.get_logger()


class TenderInformationFetcher(DataFetcher):
    """每天抓取、筛选并入库招投标公告。"""

    def __init__(
        self,
        config: TenderFetcherConfig | None = None,
        enabled: bool | None = None,
        repository_factory: Callable[[], Any] | None = None,
        client_factory: Callable[[], Any] | None = None,
        llm_factory: Callable[[], Any] | None = None,
        pipeline_factory: Callable[..., Any] | None = None,
        today_factory: Callable[[], date] = date.today,
    ):
        self.config = config or self._config_from_settings()
        if enabled is not None:
            self.config.enabled = enabled
        super().__init__(
            name="tender_information_fetcher",
            description="招投标信息每日抓取、筛选和结构化入库",
            schedule=self.config.schedule,
            version="1.0.0",
        )
        self.enabled = self.config.enabled
        self.repository_factory = repository_factory or SQLServerTenderRepository
        self.client_factory = client_factory or self._default_client
        self.llm_factory = llm_factory or self._default_llm
        self.pipeline_factory = pipeline_factory or TenderPipeline
        self.today_factory = today_factory

    @staticmethod
    def compute_target_date(today: date | None = None) -> date:
        return default_target_date(today)

    async def fetch_and_store(self):
        if not self.config.enabled:
            logger.info("tender_information_fetcher_skipped", reason="disabled")
            return {"skipped": True}

        target_date = self.compute_target_date(self.today_factory())
        repository = self.repository_factory()
        run_id = await repository.create_run(
            target_date=target_date,
            keywords=self.config.keywords,
            notice_types=self.config.notice_types,
        )
        client = self.client_factory()
        llm_client = self.llm_factory() if self.config.enable_llm else None
        pipeline = self.pipeline_factory(
            client=client,
            repository=repository,
            llm_client=llm_client,
        )

        try:
            result = await pipeline.run_daily(
                keywords=self.config.keywords,
                notice_types=self.config.notice_types,
                publish_date=target_date,
                max_pages=self.config.max_pages,
            )
            await repository.finish_run(run_id, result)
            logger.info(
                "tender_information_fetcher_completed",
                target_date=target_date.isoformat(),
                total_candidates=result.total_candidates,
                saved_notices=result.saved_notices,
                errors=len(result.errors),
            )
            return {
                "skipped": False,
                "target_date": target_date.isoformat(),
                "total_candidates": result.total_candidates,
                "duplicate_candidates": result.duplicate_candidates,
                "filtered_out": result.filtered_out,
                "detail_fetch_failures": result.detail_fetch_failures,
                "saved_notices": result.saved_notices,
                "errors": len(result.errors),
            }
        finally:
            await maybe_close_client(client)

    def _default_client(self) -> QianlimaClient:
        return QianlimaClient(
            base_url=settings.qianlima_base_url,
            username=settings.qianlima_username,
            password=settings.qianlima_password,
            storage_state_path=settings.qianlima_storage_state,
            headless=self.config.qianlima_headless,
        )

    def _default_llm(self):
        primary = OpenAICompatibleTenderLLMClient(
            api_key=settings.tender_llm_api_key,
            base_url=settings.tender_llm_base_url,
            model=settings.tender_llm_model,
        )
        if not settings.tender_secondary_llm_api_key:
            return primary

        secondary = OpenAICompatibleTenderLLMClient(
            api_key=settings.tender_secondary_llm_api_key,
            base_url=settings.tender_secondary_llm_base_url,
            model=settings.tender_secondary_llm_model,
        )
        return TenderLLMClientPool(
            [
                (primary, settings.tender_llm_concurrency),
                (secondary, settings.tender_secondary_llm_concurrency),
            ],
            screening_client_index=1,
        )

    def _config_from_settings(self) -> TenderFetcherConfig:
        return TenderFetcherConfig(
            enabled=settings.tender_fetcher_enabled,
            schedule=settings.tender_fetcher_schedule,
            keywords=parse_keywords(settings.tender_keywords),
            notice_types=parse_notice_types(settings.tender_notice_types),
            max_pages=settings.tender_max_pages,
            qianlima_storage_state=settings.qianlima_storage_state,
            qianlima_base_url=settings.qianlima_base_url,
        )
