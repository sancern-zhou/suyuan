from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional, Sequence

import structlog

from ..models import NoticeType, TenderCandidate
from ..qianlima_client import _dedupe_candidates
from .base import TenderSource

logger = structlog.get_logger()


class MultiSourceTenderClient:
    """Query several tender sources and merge the candidates.

    ``fetch_detail`` is routed back to the source that produced a candidate,
    which is recorded in ``candidate.source``.
    """

    search_ignores_notice_type = True

    def __init__(
        self,
        sources: Sequence[TenderSource],
        detail_enrichers: Sequence[TenderSource] | None = None,
    ):
        if not sources:
            raise ValueError("MultiSourceTenderClient requires at least one source")
        self._sources: dict[str, TenderSource] = {
            source.name: source for source in sources
        }
        self._enrichers = [
            item
            for item in (detail_enrichers or [])
            if callable(getattr(item, "enrich_detail", None))
        ]

    @staticmethod
    def _needs_enrichment(detail: str) -> bool:
        text = detail or ""
        if len(text) < 400:
            return True
        return any(
            marker in text
            for marker in ("登录即可免费查看", "会员专享", "会员可见", "隐藏内容", "开通会员")
        )

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(self._sources)

    async def search_plan(self, keywords, notice_types, publish_date, max_pages=0):
        merged = []
        for source in self._sources.values():
            plan = getattr(source, "search_plan", None)
            if callable(plan):
                merged.extend(await plan(keywords, notice_types, publish_date, max_pages))
                continue
            types = (NoticeType.OTHER,) if getattr(source, "search_ignores_notice_type", False) else notice_types
            for keyword in keywords:
                for notice_type in types:
                    merged.extend(await source.search(keyword, notice_type, publish_date, max_pages))
        return _dedupe_candidates(merged)

    @property
    def request_audit(self):
        return [entry for source in self._sources.values() for entry in getattr(source, "request_audit", [])]

    @property
    def search_errors(self):
        return [entry for source in self._sources.values() for entry in getattr(source, "search_errors", [])]

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]:
        results = await asyncio.gather(
            *(
                self._search_one(name, source, keyword, notice_type, publish_date, max_pages)
                for name, source in self._sources.items()
            )
        )
        merged = [candidate for items in results for candidate in items]
        return _dedupe_candidates(merged)

    async def _search_one(
        self,
        name: str,
        source: TenderSource,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date],
        max_pages: int,
    ) -> list[TenderCandidate]:
        try:
            candidates = await source.search(
                keyword, notice_type, publish_date, max_pages
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "tender_source_search_failed", source=name, keyword=keyword
            )
            return []
        for candidate in candidates:
            candidate.source = name
        return candidates

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        source = self._sources.get(candidate.source)
        if source is None:
            raise RuntimeError(
                f"no tender source registered for '{candidate.source}'"
            )
        detail = await source.fetch_detail(candidate)
        if not self._enrichers or not self._needs_enrichment(detail):
            return detail
        for enricher in self._enrichers:
            if enricher.name == candidate.source:
                continue
            try:
                better = await enricher.enrich_detail(candidate)
            except Exception:  # noqa: BLE001
                logger.exception("tender_detail_enrich_failed", enricher=enricher.name)
                continue
            if better and not self._needs_enrichment(better):
                logger.info(
                    "tender_detail_enriched",
                    source=candidate.source,
                    enricher=enricher.name,
                    url=candidate.url,
                )
                return better
        return detail

    async def close(self) -> None:
        await asyncio.gather(
            *(self._close_one(source) for source in self._sources.values()),
            return_exceptions=True,
        )

    async def _close_one(self, source: TenderSource) -> None:
        try:
            await source.close()
        except Exception:  # noqa: BLE001
            logger.exception("tender_source_close_failed", source=source.name)
