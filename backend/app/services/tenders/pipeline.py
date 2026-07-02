from __future__ import annotations

import asyncio
import inspect
import logging
import os
from datetime import date
from typing import Iterable, Protocol, Sequence

from .extractor import TenderStructuredExtractor
from .filters import TenderRelevanceFilter
from .models import (
    NoticeType,
    PipelineRunResult,
    TenderCandidate,
    TenderFilterDecision,
    TenderNotice,
)

logger = logging.getLogger(__name__)


class TenderClientProtocol(Protocol):
    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: date | None = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]: ...

    async def fetch_detail(self, candidate: TenderCandidate) -> str: ...


class TenderRepositoryProtocol(Protocol):
    async def candidate_exists(self, url: str) -> bool: ...
    async def save_candidate(
        self, candidate: TenderCandidate, decision: TenderFilterDecision | None = None
    ) -> bool: ...
    async def update_candidate_decision(
        self, candidate: TenderCandidate, decision: TenderFilterDecision
    ) -> None: ...
    async def save_notice(self, notice: TenderNotice) -> None: ...


class TenderLLMProtocol(Protocol):
    async def review_candidate(
        self,
        candidate: TenderCandidate,
        rule_decision: TenderFilterDecision,
        detail_text: str = "",
    ) -> TenderFilterDecision: ...

    async def extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice: ...


class VectorIndexerProtocol(Protocol):
    async def index_notice(self, notice: TenderNotice) -> None: ...


class TenderPipeline:
    def __init__(
        self,
        client: TenderClientProtocol,
        repository: TenderRepositoryProtocol,
        relevance_filter: TenderRelevanceFilter | None = None,
        extractor: TenderStructuredExtractor | None = None,
        llm_client: TenderLLMProtocol | None = None,
        vector_indexer: VectorIndexerProtocol | None = None,
        enable_vector_index: bool = False,
    ):
        self.client = client
        self.repository = repository
        self.relevance_filter = relevance_filter or TenderRelevanceFilter()
        self.extractor = extractor or TenderStructuredExtractor()
        self.llm_client = llm_client
        self.vector_indexer = vector_indexer
        self.enable_vector_index = enable_vector_index

    async def run_daily(
        self,
        keywords: Sequence[str],
        notice_types: Sequence[NoticeType] = (
            NoticeType.TENDER,
            NoticeType.WINNING_BID,
        ),
        publish_date: date | None = None,
        max_pages: int = 1,
    ) -> PipelineRunResult:
        result = PipelineRunResult()
        for keyword in keywords:
            for notice_type in notice_types:
                try:
                    candidates = await self.client.search(
                        keyword=keyword,
                        notice_type=notice_type,
                        publish_date=publish_date,
                        max_pages=max_pages,
                    )
                except Exception as exc:
                    message = f"search failed for keyword={keyword}, notice_type={notice_type.value}: {exc}"
                    logger.exception(message)
                    result.errors.append(message)
                    continue

                result.total_candidates += len(candidates)
                await self._process_candidates(candidates, result)
        return result

    async def _process_candidates(
        self, candidates: Iterable[TenderCandidate], result: PipelineRunResult
    ) -> None:
        new_candidates: list[TenderCandidate] = []
        for candidate in candidates:
            try:
                is_new = await self.repository.save_candidate(candidate)
                if not is_new:
                    result.duplicate_candidates += 1
                    continue
                new_candidates.append(candidate)
            except Exception as exc:
                logger.exception("candidate saving failed")
                result.errors.append(
                    f"candidate saving failed for {candidate.url}: {exc}"
                )

        initial_decisions = await self._initial_decisions(new_candidates, result)
        detail_concurrency = max(1, int(os.getenv("TENDER_DETAIL_CONCURRENCY", "5")))
        semaphore = asyncio.Semaphore(detail_concurrency)

        async def process_with_limit(candidate: TenderCandidate) -> None:
            async with semaphore:
                await self._process_candidate(candidate, initial_decisions, result)

        await asyncio.gather(
            *[process_with_limit(candidate) for candidate in new_candidates]
        )

    async def _process_candidate(
        self,
        candidate: TenderCandidate,
        initial_decisions: dict[str, TenderFilterDecision],
        result: PipelineRunResult,
    ) -> None:
        candidate_delay_ms = int(os.getenv("TENDER_CANDIDATE_DELAY_MS", "0"))
        try:
            decision = initial_decisions.get(candidate.normalized_url_key())
            if decision is None:
                decision = await self._initial_decision(candidate)

            await self.repository.update_candidate_decision(candidate, decision)

            if not decision.is_relevant:
                result.filtered_out += 1
                return

            try:
                detail_html = await self.client.fetch_detail(candidate)
            except Exception as exc:
                result.detail_fetch_failures += 1
                result.errors.append(
                    f"detail fetch failed for {candidate.url}: {exc}"
                )
                return

            if self.llm_client is not None:
                detail_decision = await self.llm_client.review_candidate(
                    candidate,
                    decision,
                    detail_text=detail_html,
                )
            else:
                detail_decision = self.relevance_filter.decide(
                    candidate, detail_html
                )
            if not detail_decision.is_relevant:
                await self.repository.update_candidate_decision(
                    candidate, detail_decision
                )
                result.filtered_out += 1
                return

            if self.llm_client is not None:
                notice = await self.llm_client.extract_notice(
                    candidate,
                    detail_html,
                    detail_decision,
                )
            else:
                notice = self.extractor.extract(
                    candidate, detail_html, detail_decision
                )
            await self.repository.save_notice(notice)
            result.saved_notices += 1

            if self.enable_vector_index and self.vector_indexer is not None:
                await self.vector_indexer.index_notice(notice)
                result.vector_indexed += 1
            if candidate_delay_ms > 0:
                await asyncio.sleep(candidate_delay_ms / 1000)
        except Exception as exc:
            logger.exception("candidate processing failed")
            result.errors.append(
                f"candidate processing failed for {candidate.url}: {exc}"
            )

    async def _initial_decisions(
        self,
        candidates: Sequence[TenderCandidate],
        result: PipelineRunResult,
    ) -> dict[str, TenderFilterDecision]:
        if self.llm_client is None or not candidates:
            return {}
        review_candidates = getattr(self.llm_client, "review_candidates", None)
        if review_candidates is None:
            return {}
        batch_size = max(1, int(os.getenv("TENDER_LLM_BATCH_SIZE", "50")))
        batch_delay_ms = int(os.getenv("TENDER_LLM_BATCH_DELAY_MS", "0"))
        decisions: dict[str, TenderFilterDecision] = {}
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start : start + batch_size]
            try:
                batch_decisions = await review_candidates(
                    batch, self._pending_llm_decision()
                )
                decisions.update(batch_decisions)
                for candidate in batch:
                    key = candidate.normalized_url_key()
                    if key not in batch_decisions:
                        decisions[key] = TenderFilterDecision(
                            is_relevant=False,
                            reason="LLM初筛未命中环境业务公告",
                            confidence=0.8,
                            decision_source="llm",
                        )
            except Exception as exc:
                logger.exception("candidate batch review failed")
                result.errors.append(
                    f"candidate batch review failed at offset {start}: {exc}"
                )
            if batch_delay_ms > 0 and start + batch_size < len(candidates):
                await asyncio.sleep(batch_delay_ms / 1000)
        return decisions

    async def _initial_decision(
        self, candidate: TenderCandidate
    ) -> TenderFilterDecision:
        if self.llm_client is not None:
            return await self.llm_client.review_candidate(
                candidate,
                self._pending_llm_decision(),
            )
        return self.relevance_filter.decide(candidate)

    def _pending_llm_decision(self) -> TenderFilterDecision:
        return TenderFilterDecision(
            is_relevant=True,
            reason="等待 LLM 基于招投标语义判断",
            confidence=0.0,
            decision_source="pending_llm",
        )


async def maybe_close_client(client) -> None:
    close = getattr(client, "close", None)
    if close is None:
        return
    value = close()
    if inspect.isawaitable(value):
        await value
