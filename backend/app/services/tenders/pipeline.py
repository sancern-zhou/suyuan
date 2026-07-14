from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
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
    async def save_candidates(
        self, candidates: Sequence[TenderCandidate]
    ) -> dict[str, bool]: ...
    async def update_candidate_decision(
        self, candidate: TenderCandidate, decision: TenderFilterDecision
    ) -> None: ...
    async def update_candidate_decisions(
        self, decisions: Sequence[tuple[TenderCandidate, TenderFilterDecision]]
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

    async def review_and_extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice | TenderFilterDecision: ...


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
        search_notice_types = self._search_notice_types(notice_types)
        for keyword in keywords:
            for notice_type in search_notice_types:
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

    def _search_notice_types(
        self, notice_types: Sequence[NoticeType]
    ) -> Sequence[NoticeType]:
        if getattr(self.client, "search_ignores_notice_type", False):
            return (NoticeType.OTHER,)
        return notice_types

    async def _process_candidates(
        self, candidates: Iterable[TenderCandidate], result: PipelineRunResult
    ) -> None:
        deduped_candidates: list[TenderCandidate] = []
        seen_titles: set[str] = set()
        for candidate in candidates:
            title_key = self._normalized_title_key(candidate)
            if title_key and title_key in seen_titles:
                result.duplicate_candidates += 1
                continue
            if title_key:
                seen_titles.add(title_key)
            deduped_candidates.append(candidate)

        new_candidates = await self._save_new_candidates(deduped_candidates, result)

        prefilter_decisions: dict[str, TenderFilterDecision] = {}
        llm_candidates: list[TenderCandidate] = []
        for candidate in new_candidates:
            decision = self.relevance_filter.prefilter_decision(candidate)
            if decision is not None:
                prefilter_decisions[candidate.normalized_url_key()] = decision
            else:
                llm_candidates.append(candidate)

        initial_decisions = dict(prefilter_decisions)
        initial_decisions.update(await self._initial_decisions(llm_candidates, result))
        await self._persist_initial_decisions(new_candidates, initial_decisions, result)

        accepted_candidates: list[TenderCandidate] = []
        for candidate in new_candidates:
            decision = initial_decisions.get(candidate.normalized_url_key())
            if decision is None:
                decision = TenderFilterDecision(
                    is_relevant=False,
                    reason="初筛未给出决策，跳过详情页抓取",
                    confidence=0.0,
                    decision_source="system",
                )
                initial_decisions[candidate.normalized_url_key()] = decision
                await self.repository.update_candidate_decision(candidate, decision)
            if decision.is_relevant:
                accepted_candidates.append(candidate)
            else:
                result.filtered_out += 1

        detail_concurrency = self._detail_concurrency()
        semaphore = asyncio.Semaphore(detail_concurrency)
        detail_stop_event = asyncio.Event()

        async def process_with_limit(candidate: TenderCandidate) -> None:
            async with semaphore:
                if detail_stop_event.is_set():
                    return
                try:
                    await self._process_candidate(candidate, initial_decisions, result)
                except Exception as exc:
                    if self._is_detail_access_exhausted_error(exc):
                        if not detail_stop_event.is_set():
                            detail_stop_event.set()
                            result.detail_fetch_failures += 1
                            result.errors.append(f"detail processing stopped: {exc}")
                        return
                    raise

        await asyncio.gather(
            *[process_with_limit(candidate) for candidate in accepted_candidates]
        )

    def _detail_concurrency(self) -> int:
        configured = os.getenv("TENDER_DETAIL_CONCURRENCY")
        if configured:
            return max(1, int(configured))
        if self.llm_client is not None:
            pool_concurrency = getattr(self.llm_client, "detail_concurrency", None)
            if pool_concurrency is not None:
                return max(1, int(pool_concurrency))
        return 5

    async def _save_new_candidates(
        self, candidates: Sequence[TenderCandidate], result: PipelineRunResult
    ) -> list[TenderCandidate]:
        if not candidates:
            return []
        save_candidates = getattr(self.repository, "save_candidates", None)
        if save_candidates is not None:
            try:
                inserted = await save_candidates(candidates)
                new_candidates = [
                    candidate
                    for candidate in candidates
                    if inserted.get(candidate.url, False)
                ]
                result.duplicate_candidates += len(candidates) - len(new_candidates)
                return new_candidates
            except Exception as exc:
                logger.exception("candidate batch saving failed")
                result.errors.append(f"candidate batch saving failed: {exc}")
                return []

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
        return new_candidates

    async def _persist_initial_decisions(
        self,
        candidates: Sequence[TenderCandidate],
        decisions: dict[str, TenderFilterDecision],
        result: PipelineRunResult,
    ) -> None:
        decision_rows = [
            (candidate, decisions[candidate.normalized_url_key()])
            for candidate in candidates
            if candidate.normalized_url_key() in decisions
        ]
        if not decision_rows:
            return
        update_many = getattr(self.repository, "update_candidate_decisions", None)
        try:
            if update_many is not None:
                await update_many(decision_rows)
                return
            for candidate, decision in decision_rows:
                await self.repository.update_candidate_decision(candidate, decision)
        except Exception as exc:
            logger.exception("candidate decision batch update failed")
            result.errors.append(f"candidate decision batch update failed: {exc}")

    def _normalized_title_key(self, candidate: TenderCandidate) -> str:
        value = candidate.title or ""
        value = re.sub(r"\[[^\]]+\]|\【[^】]+\】|\([^)]*\)|（[^）]*）", "", value)
        value = re.sub(r"\s+", "", value).lower()
        return value

    async def _process_candidate(
        self,
        candidate: TenderCandidate,
        initial_decisions: dict[str, TenderFilterDecision],
        result: PipelineRunResult,
    ) -> None:
        timeout_seconds = float(os.getenv("TENDER_DETAIL_TASK_TIMEOUT_SECONDS", "240"))
        try:
            await asyncio.wait_for(
                self._process_candidate_inner(candidate, initial_decisions, result),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            result.detail_fetch_failures += 1
            result.errors.append(
                f"candidate processing timed out for {candidate.url} after {timeout_seconds:g}s"
            )

    def _is_detail_access_exhausted_error(self, exc: Exception) -> bool:
        return bool(getattr(exc, "stop_tender_detail_processing", False))

    async def _process_candidate_inner(
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

            if not decision.is_relevant:
                return

            try:
                detail_html = await self.client.fetch_detail(candidate)
            except Exception as exc:
                if self._is_detail_access_exhausted_error(exc):
                    raise
                result.detail_fetch_failures += 1
                result.errors.append(
                    f"detail fetch failed for {candidate.url}: {exc}"
                )
                return

            if self.llm_client is None:
                detail_decision = self.relevance_filter.decide(
                    candidate, detail_html
                )
                if not detail_decision.is_relevant:
                    await self.repository.update_candidate_decision(
                        candidate, detail_decision
                    )
                    result.filtered_out += 1
                    return
                notice = self.extractor.extract(
                    candidate, detail_html, detail_decision
                )
            else:
                try:
                    combined = await self._review_and_extract_notice(
                        candidate,
                        detail_html,
                        decision,
                    )
                except Exception as exc:
                    notice = self.extractor.extract(
                        candidate, detail_html, decision
                    )
                    result.errors.append(
                        f"LLM review/extract failed for {candidate.url}; saved fallback notice: {exc}"
                    )
                else:
                    if isinstance(combined, TenderFilterDecision):
                        if not combined.is_relevant:
                            await self.repository.update_candidate_decision(
                                candidate, combined
                            )
                            result.filtered_out += 1
                            return
                        notice = self.extractor.extract(
                            candidate, detail_html, combined
                        )
                    else:
                        notice = combined
            await self.repository.save_notice(notice)
            result.saved_notices += 1

            if self.enable_vector_index and self.vector_indexer is not None:
                await self.vector_indexer.index_notice(notice)
                result.vector_indexed += 1
            if candidate_delay_ms > 0:
                await asyncio.sleep(candidate_delay_ms / 1000)
        except Exception as exc:
            if self._is_detail_access_exhausted_error(exc):
                raise
            logger.exception("candidate processing failed")
            result.errors.append(
                f"candidate processing failed for {candidate.url}: {exc}"
            )

    async def _review_and_extract_notice(
        self,
        candidate: TenderCandidate,
        detail_html: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice | TenderFilterDecision:
        combined = getattr(self.llm_client, "review_and_extract_notice", None)
        if combined is not None:
            return await combined(candidate, detail_html, decision)

        detail_decision = await self.llm_client.review_candidate(
            candidate,
            decision,
            detail_text=detail_html,
        )
        if not detail_decision.is_relevant:
            return detail_decision
        return await self.llm_client.extract_notice(
            candidate,
            detail_html,
            detail_decision,
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
        batch_size = max(1, int(os.getenv("TENDER_LLM_BATCH_SIZE", "20")))
        batch_delay_ms = int(os.getenv("TENDER_LLM_BATCH_DELAY_MS", "0"))
        screening_concurrency = max(
            1, int(os.getenv("TENDER_LLM_SCREENING_CONCURRENCY", "5"))
        )
        screening_timeout_seconds = float(
            os.getenv("TENDER_LLM_SCREENING_TIMEOUT_SECONDS", "75")
        )
        screening_timeout_budget_seconds = self._screening_timeout_budget_seconds(
            screening_timeout_seconds
        )
        decisions: dict[str, TenderFilterDecision] = {}
        semaphore = asyncio.Semaphore(screening_concurrency)

        async def review_batch(
            start: int, batch: Sequence[TenderCandidate]
        ) -> dict[str, TenderFilterDecision]:
            if batch_delay_ms > 0 and start > 0:
                await asyncio.sleep((batch_delay_ms / 1000) * (start // batch_size))
            try:
                async with semaphore:
                    review_task = asyncio.create_task(
                        review_candidates(batch, self._pending_llm_decision())
                    )
                    if screening_timeout_budget_seconds > 0:
                        done, pending = await asyncio.wait(
                            {review_task}, timeout=screening_timeout_budget_seconds
                        )
                        if pending:
                            review_task.cancel()
                            review_task.add_done_callback(_consume_task_exception)
                            raise asyncio.TimeoutError(
                                f"LLM batch screening timed out after {screening_timeout_budget_seconds:g}s"
                            )
                        batch_decisions = next(iter(done)).result()
                    else:
                        batch_decisions = await review_task
                batch_result = dict(batch_decisions)
                for candidate in batch:
                    key = candidate.normalized_url_key()
                    if key not in batch_result:
                        batch_result[key] = TenderFilterDecision(
                            is_relevant=False,
                            reason="LLM初筛未命中环境业务公告",
                            confidence=0.8,
                            decision_source="llm",
                        )
                return batch_result
            except Exception as exc:
                logger.exception("candidate batch review failed")
                result.errors.append(
                    f"candidate batch review failed at offset {start}: {exc}"
                )
                batch_result = {}
                for candidate in batch:
                    batch_result[candidate.normalized_url_key()] = TenderFilterDecision(
                        is_relevant=False,
                        reason="LLM批量初筛失败，跳过详情页抓取",
                        confidence=0.0,
                        decision_source="llm_error",
                    )
                return batch_result

        tasks = {
            asyncio.create_task(
                review_batch(start, candidates[start : start + batch_size])
            ): (start, candidates[start : start + batch_size])
            for start in range(0, len(candidates), batch_size)
        }
        pending = set(tasks)
        no_progress_timeout = (
            screening_timeout_budget_seconds
            if screening_timeout_budget_seconds > 0
            else None
        )
        while pending:
            done, pending = await asyncio.wait(
                pending,
                timeout=no_progress_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                for task in pending:
                    start, batch = tasks[task]
                    task.cancel()
                    task.add_done_callback(_consume_task_exception)
                    result.errors.append(
                        f"candidate batch review timed out waiting for progress at offset {start}"
                    )
                    decisions.update(self._llm_error_decisions(batch))
                break
            for task in done:
                decisions.update(await task)
        return decisions

    def _screening_timeout_budget_seconds(self, timeout_seconds: float) -> float:
        if timeout_seconds <= 0:
            return timeout_seconds
        if not getattr(self.llm_client, "handles_screening_timeouts", False):
            return timeout_seconds
        entry_count = int(getattr(self.llm_client, "screening_entry_count", 1))
        return timeout_seconds * max(1, entry_count)

    def _llm_error_decisions(
        self, candidates: Sequence[TenderCandidate]
    ) -> dict[str, TenderFilterDecision]:
        return {
            candidate.normalized_url_key(): TenderFilterDecision(
                is_relevant=False,
                reason="LLM批量初筛失败，跳过详情页抓取",
                confidence=0.0,
                decision_source="llm_error",
            )
            for candidate in candidates
        }

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


def _consume_task_exception(task: asyncio.Task) -> None:
    try:
        task.result()
    except BaseException:
        pass
