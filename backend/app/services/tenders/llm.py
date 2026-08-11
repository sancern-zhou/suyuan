from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
import json
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Sequence

from .categories import (
    normalize_project_category,
    project_category_options,
    project_category_schema,
)
from .extractor import amount_to_wan_yuan, clean_detail_content, extract_attachment_urls
from .models import NoticeType, TenderCandidate, TenderFilterDecision, TenderNotice


@dataclass(slots=True)
class TenderLLMPoolEntry:
    client: Any
    concurrency: int
    semaphore: asyncio.Semaphore


class TenderLLMClientPool:
    def __init__(
        self,
        clients: Sequence[tuple[Any, int]],
        screening_client_index: int = 0,
    ):
        if not clients:
            raise ValueError("TenderLLMClientPool requires at least one client")
        self.entries = [
            TenderLLMPoolEntry(
                client=client,
                concurrency=max(1, int(concurrency)),
                semaphore=asyncio.Semaphore(max(1, int(concurrency))),
            )
            for client, concurrency in clients
        ]
        if len(self.entries) > 1:
            for entry in self.entries:
                if hasattr(entry.client, "retry_rate_limits"):
                    entry.client.retry_rate_limits = False
                if hasattr(entry.client, "retry_transient_errors"):
                    entry.client.retry_transient_errors = False
        if screening_client_index < 0 or screening_client_index >= len(self.entries):
            raise ValueError("screening_client_index is out of range")
        self.screening_client_index = screening_client_index
        self._next_index = 0
        self._selection_lock = asyncio.Lock()

    @property
    def detail_concurrency(self) -> int:
        return sum(entry.concurrency for entry in self.entries)

    @property
    def handles_screening_timeouts(self) -> bool:
        return True

    @property
    def screening_entry_count(self) -> int:
        return self._screening_max_attempts()

    async def review_candidates(
        self,
        candidates: Sequence[TenderCandidate],
        rule_decision: TenderFilterDecision,
    ) -> dict[str, TenderFilterDecision]:
        timeout_seconds = float(
            os.getenv("TENDER_LLM_SCREENING_TIMEOUT_SECONDS", "75")
        )
        return await self._call_screening_client(
            "review_candidates",
            candidates,
            rule_decision,
            timeout_seconds=timeout_seconds if timeout_seconds > 0 else None,
        )

    async def _call_screening_client(
        self,
        method_name: str,
        *args,
        timeout_seconds: float | None = None,
        **kwargs,
    ):
        max_attempts = self._screening_max_attempts()
        for attempt in range(1, max_attempts + 1):
            entry_index = (self.screening_client_index + attempt - 1) % len(
                self.entries
            )
            entry = self.entries[entry_index]
            try:
                async with entry.semaphore:
                    method = getattr(entry.client, method_name)
                    call = method(*args, **kwargs)
                    if timeout_seconds is not None:
                        return await asyncio.wait_for(call, timeout=timeout_seconds)
                    return await call
            except Exception as exc:
                if not _is_retryable_failover_error(exc) or attempt >= max_attempts:
                    raise
                await asyncio.sleep(_llm_rate_limit_delay_seconds(exc, attempt))
        raise RuntimeError("初筛 LLM 没有可用模型")

    @staticmethod
    def _screening_max_attempts() -> int:
        return max(1, int(os.getenv("TENDER_LLM_SCREENING_MAX_ATTEMPTS", "3")))

    async def review_candidate(
        self,
        candidate: TenderCandidate,
        rule_decision: TenderFilterDecision,
        detail_text: str = "",
    ) -> TenderFilterDecision:
        start_index = await self._select_entry_index()
        return await self._call_with_rate_limit_failover(
            start_index,
            "review_candidate",
            candidate,
            rule_decision,
            detail_text=detail_text,
        )

    async def extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice:
        start_index = await self._select_entry_index()
        return await self._call_with_rate_limit_failover(
            start_index,
            "extract_notice",
            candidate,
            detail_text,
            decision,
        )

    async def review_and_extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice | TenderFilterDecision:
        start_index = await self._select_entry_index()
        return await self._call_with_rate_limit_failover(
            start_index,
            "review_and_extract_notice",
            candidate,
            detail_text,
            decision,
        )

    async def _call_with_rate_limit_failover(
        self,
        start_index: int,
        method_name: str,
        *args,
        timeout_seconds: float | None = None,
        **kwargs,
    ):
        last_failover_error: Exception | None = None
        for offset in range(len(self.entries)):
            entry_index = (start_index + offset) % len(self.entries)
            entry = self.entries[entry_index]
            try:
                async with entry.semaphore:
                    method = getattr(entry.client, method_name)
                    call = method(*args, **kwargs)
                    if timeout_seconds is not None:
                        return await asyncio.wait_for(call, timeout=timeout_seconds)
                    return await call
            except asyncio.TimeoutError as exc:
                last_failover_error = exc
                if offset >= len(self.entries) - 1:
                    break
                await asyncio.sleep(_llm_rate_limit_delay_seconds(exc, offset + 1))
            except Exception as exc:
                if not _is_retryable_failover_error(exc):
                    raise
                last_failover_error = exc
                if offset >= len(self.entries) - 1:
                    break
                await asyncio.sleep(_llm_rate_limit_delay_seconds(exc, offset + 1))
        if last_failover_error is not None:
            raise last_failover_error
        raise RuntimeError("LLM池没有可用模型")

    async def _select_entry(self) -> TenderLLMPoolEntry:
        return self.entries[await self._select_entry_index()]

    async def _select_entry_index(self) -> int:
        async with self._selection_lock:
            entry_index = self._next_index
            self._next_index = (self._next_index + 1) % len(self.entries)
            return entry_index


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if status_code == 429 or response_status == 429:
        return True
    return exc.__class__.__name__ == "RateLimitError" or "429" in str(exc)


def _is_retryable_failover_error(exc: Exception) -> bool:
    if _is_rate_limit_error(exc):
        return True
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError)):
        return True
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    effective_status = status_code or response_status
    if effective_status in {408, 429}:
        return True
    if isinstance(effective_status, int) and effective_status >= 500:
        return True
    return exc.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "RateLimitError",
    }


def _llm_rate_limit_delay_seconds(exc: Exception, attempt: int) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return retry_after

    base_seconds = float(os.getenv("TENDER_LLM_RATE_LIMIT_BASE_DELAY_SECONDS", "2"))
    max_seconds = float(os.getenv("TENDER_LLM_RATE_LIMIT_MAX_DELAY_SECONDS", "30"))
    jitter_seconds = float(os.getenv("TENDER_LLM_RATE_LIMIT_JITTER_SECONDS", "0.5"))
    exponential_delay = base_seconds * (2 ** max(0, attempt - 1))
    return min(max_seconds, exponential_delay) + random.uniform(0, jitter_seconds)


def _retry_after_seconds(exc: Exception) -> float | None:
    headers = getattr(exc, "headers", None)
    response = getattr(exc, "response", None)
    if headers is None and response is not None:
        headers = getattr(response, "headers", None)
    if not headers:
        return None

    value = None
    for key in ("retry-after", "Retry-After"):
        try:
            value = headers.get(key)
        except AttributeError:
            value = headers[key] if key in headers else None
        if value:
            break
    if not value:
        return None

    text = str(value).strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


def _is_retryable_agnes_not_found(
    exc: Exception, base_url: str | None
) -> bool:
    if "apihub.agnes-ai.com" not in (base_url or "").lower():
        return False
    response = getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None) or getattr(
        response, "status_code", None
    )
    if status_code != 404:
        return False
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("upstream_error", "notfounderror", "not found")
    )


class OpenAICompatibleTenderLLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        provider: str | None = None,
        api_mode: str | None = None,
    ):
        self._load_environment()
        selected_provider = provider or self._selected_provider()
        self.provider = selected_provider.strip().lower()
        self.api_mode = (
            api_mode or self._provider_api_mode(self.provider)
        ).strip().lower()
        self.api_key = api_key or self._first_configured_value(
            [
                "TENDER_LLM_API_KEY",
                *self._provider_key_names(self.provider),
                "OPENAI_API_KEY",
            ]
        )
        self.base_url = self._normalize_base_url(
            base_url
            or os.getenv("TENDER_LLM_BASE_URL")
            or self._provider_base_url(self.provider)
            or self._default_base_url()
        )
        self.model = (
            model
            or os.getenv("TENDER_LLM_MODEL")
            or self._provider_model(self.provider)
            or os.getenv("OPENAI_MODEL")
            or self._default_model(self.base_url)
        )
        self.temperature = temperature
        self.retry_rate_limits = True
        self.retry_transient_errors = True
        if not self.api_key:
            raise RuntimeError(
                "启用 LLM 时需要配置 TENDER_LLM_API_KEY、BAILIAN_API_KEY、GLM_API_KEY 或 OPENAI_API_KEY"
            )

    async def review_candidate(
        self,
        candidate: TenderCandidate,
        rule_decision: TenderFilterDecision,
        detail_text: str = "",
    ) -> TenderFilterDecision:
        prompt = self._candidate_prompt(candidate, rule_decision, detail_text)
        data = await self._json_chat(prompt)
        if not data:
            return rule_decision
        return TenderFilterDecision(
            is_relevant=bool(data.get("is_relevant", rule_decision.is_relevant)),
            reason=str(data.get("reason") or rule_decision.reason),
            confidence=float(data.get("confidence", rule_decision.confidence)),
            decision_source="llm",
            matched_positive_keywords=rule_decision.matched_positive_keywords,
            matched_negative_keywords=rule_decision.matched_negative_keywords,
            project_category=normalize_project_category(data.get("project_category"))
            or normalize_project_category(rule_decision.project_category),
        )

    async def review_candidates(
        self,
        candidates: Sequence[TenderCandidate],
        rule_decision: TenderFilterDecision,
    ) -> dict[str, TenderFilterDecision]:
        prompt = self._candidate_batch_prompt(candidates, rule_decision)
        data = await self._json_chat(prompt)
        decisions: dict[str, TenderFilterDecision] = {}
        candidate_by_index = {
            index + 1: candidate for index, candidate in enumerate(candidates)
        }
        keep_indexes = self._keep_indexes_from_batch_response(data)
        if keep_indexes is not None:
            for index in keep_indexes:
                candidate = candidate_by_index.get(index)
                if candidate is None:
                    continue
                decisions[candidate.normalized_url_key()] = TenderFilterDecision(
                    is_relevant=True,
                    reason="LLM初筛命中环境业务公告",
                    confidence=0.8,
                    decision_source="llm",
                )
            return decisions

        rows = data.get("decisions", []) if isinstance(data, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                index = int(row.get("index"))
            except (TypeError, ValueError):
                continue
            candidate = candidate_by_index.get(index)
            if candidate is None:
                continue
            decisions[candidate.normalized_url_key()] = TenderFilterDecision(
                is_relevant=bool(row.get("is_relevant", False)),
                reason=str(row.get("reason") or "LLM批量筛选未给出原因"),
                confidence=float(row.get("confidence", 0.0)),
                decision_source="llm",
                project_category=normalize_project_category(row.get("project_category")),
            )
        return decisions

    def _keep_indexes_from_batch_response(self, data: Any) -> list[int] | None:
        raw_keep = data
        if isinstance(data, dict):
            raw_keep = data.get("keep")
        if not isinstance(raw_keep, list):
            return None

        keep: list[int] = []
        for value in raw_keep:
            try:
                keep.append(int(value))
            except (TypeError, ValueError):
                continue
        return keep

    async def extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice:
        raw_content = clean_detail_content(detail_text)
        prompt = self._notice_prompt(candidate, raw_content, decision)
        data = await self._json_chat(prompt)

        notice_type = self._notice_type_or_default(
            data.get("notice_type"), candidate.notice_type
        )
        budget_amount = self._string_or_none(data.get("budget_amount"))
        winning_bidder = None
        winning_amount = None
        if notice_type == NoticeType.WINNING_BID:
            winning_bidder = self._string_or_none(data.get("winning_bidder"))
            winning_amount = self._string_or_none(data.get("winning_amount"))
        notice = TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=notice_type,
            raw_content=raw_content,
            project_name=self._string_or_none(data.get("project_name")),
            purchaser=self._string_or_none(data.get("purchaser")),
            agency=self._string_or_none(data.get("agency")),
            winning_bidder=winning_bidder,
            budget_amount=budget_amount,
            budget_amount_wan_yuan=amount_to_wan_yuan(budget_amount),
            winning_amount=winning_amount,
            winning_amount_wan_yuan=amount_to_wan_yuan(winning_amount),
            province=self._string_or_none(data.get("province")),
            city=self._string_or_none(data.get("city")),
            publish_date=self._date_or_default(
                data.get("publish_date"), candidate.publish_date
            ),
            bid_open_date=self._string_or_none(data.get("bid_open_date")),
            deadline=self._string_or_none(data.get("deadline")),
            industry_category=normalize_project_category(data.get("industry_category"))
            or normalize_project_category(data.get("project_category"))
            or normalize_project_category(decision.project_category),
            environment_relevance=decision.is_relevant,
            filter_reason=decision.reason,
            filter_confidence=decision.confidence,
            summary=self._string_or_none(data.get("summary")) or "",
            key_requirements=self._string_list(data.get("key_requirements")),
            attachment_urls=extract_attachment_urls(detail_text, candidate.url),
        )
        notice.structured_json = self._notice_payload(notice)
        return notice

    async def review_and_extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice | TenderFilterDecision:
        raw_content = clean_detail_content(detail_text)
        prompt = self._combined_notice_prompt(candidate, raw_content, decision)
        data = await self._json_chat(prompt)
        is_relevant = bool(data.get("is_relevant", False))
        confidence = float(data.get("confidence", decision.confidence))
        project_category = normalize_project_category(data.get("project_category")) or normalize_project_category(
            decision.project_category
        )
        if not is_relevant:
            return TenderFilterDecision(
                is_relevant=False,
                reason=str(data.get("reject_reason") or "详情页复核非环境业务采购公告"),
                confidence=confidence,
                decision_source="llm",
                matched_positive_keywords=decision.matched_positive_keywords,
                matched_negative_keywords=decision.matched_negative_keywords,
                project_category=project_category,
            )

        detail_decision = TenderFilterDecision(
            is_relevant=True,
            reason=str(data.get("relevance_reason") or decision.reason),
            confidence=confidence,
            decision_source="llm",
            matched_positive_keywords=decision.matched_positive_keywords,
            matched_negative_keywords=decision.matched_negative_keywords,
            project_category=project_category,
        )
        return self._notice_from_data(
            candidate,
            detail_text,
            raw_content,
            detail_decision,
            data,
        )

    async def refine_notice(self, notice: TenderNotice) -> TenderNotice:
        return notice

    async def _json_chat(self, prompt: str) -> Dict[str, Any]:
        if getattr(self, "api_mode", "chat_completions") == "anthropic_messages":
            return await self._anthropic_json_chat(prompt)

        from openai import (
            APIConnectionError,
            APITimeoutError,
            AsyncOpenAI,
            InternalServerError,
            RateLimitError,
        )

        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        client_kwargs["timeout"] = float(os.getenv("TENDER_LLM_TIMEOUT_SECONDS", "120"))
        client_kwargs["max_retries"] = 0
        client = AsyncOpenAI(**client_kwargs)
        max_retries = (
            int(os.getenv("TENDER_LLM_MAX_RETRIES", "3"))
            if getattr(self, "retry_transient_errors", True)
            else 1
        )
        rate_limit_max_retries = (
            int(os.getenv("TENDER_LLM_RATE_LIMIT_MAX_RETRIES", "3"))
            if getattr(self, "retry_rate_limits", True)
            else 1
        )
        max_attempts = max(max_retries, rate_limit_max_retries)
        agnes_not_found_max_retries = 1
        max_attempts = max(max_attempts, agnes_not_found_max_retries + 1)
        response = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是招投标项目筛选和结构化抽取助手。只输出JSON。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                break
            except RateLimitError as exc:
                if attempt >= rate_limit_max_retries:
                    raise
                await asyncio.sleep(_llm_rate_limit_delay_seconds(exc, attempt))
            except (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
            ):
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(min(2 * attempt, 8))
            except Exception as exc:
                if (
                    not _is_retryable_agnes_not_found(exc, self.base_url)
                    or attempt > agnes_not_found_max_retries
                ):
                    raise
                await asyncio.sleep(attempt)
        if response is None:
            raise RuntimeError("LLM响应为空")
        content = response.choices[0].message.content or "{}"
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content.removeprefix("json").strip()
        return json.loads(content)

    async def _anthropic_json_chat(self, prompt: str) -> Dict[str, Any]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=(self.base_url or "").rstrip("/"),
            timeout=float(os.getenv("TENDER_LLM_TIMEOUT_SECONDS", "120")),
            max_retries=(
                int(os.getenv("TENDER_LLM_MAX_RETRIES", "3"))
                if getattr(self, "retry_transient_errors", True)
                else 0
            ),
        )
        try:
            response = await client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                system="你是招投标项目筛选和结构化抽取助手。只输出JSON。",
                messages=[{"role": "user", "content": prompt}],
            )
        finally:
            await client.close()

        content = "\n".join(
            str(getattr(block, "text", ""))
            for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        return json.loads(content or "{}")

    def _load_environment(self) -> None:
        try:
            from dotenv import dotenv_values, load_dotenv
        except ImportError:
            return
        for env_file in [".env", ".env.native_llm", ".env.hybrid"]:
            load_dotenv(env_file, override=False)
        for key, value in dotenv_values(".env.production").items():
            if (
                key
                in {
                    "TENDER_LLM_API_KEY",
                    "OPENAI_API_KEY",
                    "TENDER_LLM_BASE_URL",
                    "TENDER_LLM_MODEL",
                    "OPENAI_MODEL",
                }
                and value
                and (key not in os.environ or self._looks_placeholder(os.environ[key]))
            ):
                os.environ[key] = value

    def _selected_provider(self) -> str:
        provider = os.getenv("TENDER_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or ""
        return provider.strip().split("#", 1)[0].strip().lower()

    def _provider_key_names(self, provider: str) -> list[str]:
        if provider == "doubao":
            return ["DOUBAO_API_KEY"]
        if provider == "bailian":
            return ["BAILIAN_API_KEY"]
        if provider == "glm":
            return ["GLM_API_KEY"]
        return []

    def _provider_base_url(self, provider: str) -> str | None:
        if provider == "doubao":
            return os.getenv("DOUBAO_BASE_URL")
        if provider == "bailian":
            return os.getenv("BAILIAN_BASE_URL")
        if provider == "glm":
            return os.getenv("GLM_BASE_URL")
        return None

    def _provider_model(self, provider: str) -> str | None:
        if provider == "doubao":
            return os.getenv("DOUBAO_MODEL")
        if provider == "bailian":
            return os.getenv("BAILIAN_MODEL")
        if provider == "glm":
            return os.getenv("GLM_MODEL")
        return None

    def _provider_api_mode(self, provider: str) -> str:
        env_name = {
            "doubao": "DOUBAO_API_MODE",
            "agnes": "AGNES_API_MODE",
            "bailian": "BAILIAN_API_MODE",
            "glm": "GLM_API_MODE",
        }.get(provider)
        if env_name:
            configured = os.getenv(env_name)
            if configured:
                return configured
        return "anthropic_messages" if provider == "bailian" else "chat_completions"

    def _default_base_url(self) -> str | None:
        return None

    def _default_model(self, base_url: str | None = None) -> str:
        return "gpt-4.1-mini"

    def _normalize_base_url(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.rstrip("/")
        suffix = "/chat/completions"
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
        return normalized

    def _first_configured_value(self, names: list[str]) -> str | None:
        for name in names:
            value = os.getenv(name)
            if value and not self._looks_placeholder(value):
                return value
        return None

    def _looks_placeholder(self, value: str) -> bool:
        normalized = value.strip().lower()
        return any(
            marker in normalized
            for marker in ["your", "test", "demo", "xxx", "placeholder", "填写", "替换"]
        )

    def _candidate_prompt(
        self,
        candidate: TenderCandidate,
        rule_decision: TenderFilterDecision,
        detail_text: str = "",
    ) -> str:
        return json.dumps(
            {
                "task": "判断招投标候选项目是否属于环境业务项目。请基于项目的业务内容、采购目标、服务范围和公告语境进行语义判断，不要依赖固定关键词匹配。",
                "include_when": [
                    "项目实质内容服务于环境监测、污染治理、生态环境分区管控、排污口治理、环境咨询评估、生态环境执法支撑、环保设施设备或环境数据能力建设。",
                    "采购单位不是生态环境部门，但项目本身明确属于环境治理、环境监测、环保咨询或污染防治业务。",
                ],
                "exclude_when": [
                    "只是生态环境部门采购通用办公、后勤保障、车辆维修、广告宣传、网络电信、物业餐饮、装修家具等非环境业务内容。",
                    "只是行政审批、公示、受理、环评批复等政府信息公开事项，并非采购或招投标项目。",
                    "采购意向、合同履约验收、网上超市、定点采购、招标代理、采购代理、印刷宣传、业务用车等不属于目标公告。",
                    "环境相关内容仅出现在网页导航、推荐信息、站点热词或无关上下文中。",
                ],
                "candidate": {
                    "title": candidate.title,
                    "url": candidate.url,
                    "notice_type": candidate.notice_type.value,
                    "raw_list_text": candidate.raw_list_text,
                    "raw_detail_text": detail_text[:6000],
                },
                "prior_decision": {
                    "is_relevant": rule_decision.is_relevant,
                    "reason": rule_decision.reason,
                    "confidence": rule_decision.confidence,
                },
                "output_schema": {
                    "is_relevant": "boolean",
                    "reason": "string",
                    "confidence": "number between 0 and 1",
                    "project_category": f"{project_category_schema()}|null",
                },
            },
            ensure_ascii=False,
        )

    def _candidate_batch_prompt(
        self,
        candidates: Sequence[TenderCandidate],
        rule_decision: TenderFilterDecision,
    ) -> str:
        return json.dumps(
            {
                "task": "批量判断招投标候选项目是否属于环境业务项目。只返回需要进入详情页复核的候选序号，不要输出原因、置信度、分类或未命中项目。",
                "include_when": [
                    "项目实质内容服务于环境监测、污染治理、生态环境分区管控、排污口治理、环境咨询评估、生态环境执法支撑、环保设施设备或环境数据能力建设。",
                    "采购单位不是生态环境部门，但项目本身明确属于环境治理、环境监测、环保咨询或污染防治业务。",
                ],
                "exclude_when": [
                    "只是生态环境部门采购通用办公、后勤保障、车辆维修、广告宣传、网络电信、物业餐饮、装修家具等非环境业务内容。",
                    "只是行政审批、公示、受理、环评批复等政府信息公开事项，并非采购或招投标项目。",
                    "采购意向、合同履约验收、网上超市、定点采购、招标代理、采购代理、印刷宣传、业务用车等不属于目标公告。",
                    "环境相关内容仅出现在网页导航、推荐信息、站点热词或无关上下文中。",
                ],
                "candidates": [
                    {
                        "i": index + 1,
                        "t": candidate.title,
                        "n": candidate.notice_type.value,
                        "x": candidate.raw_list_text[:200],
                    }
                    for index, candidate in enumerate(candidates)
                ],
                "output_schema": {
                    "keep": ["number"],
                },
            },
            ensure_ascii=False,
        )

    def _notice_prompt(
        self,
        candidate: TenderCandidate,
        raw_content: str,
        decision: TenderFilterDecision,
    ) -> str:
        return json.dumps(
            {
                "task": "从招投标详情原文中直接抽取结构化字段。必须以原文语义为依据，不要沿用规则抽取结果；无法确定的字段返回null。",
                "candidate": {
                    "title": candidate.title,
                    "url": candidate.url,
                    "notice_type": candidate.notice_type.value,
                    "publish_date_from_list": (
                        candidate.publish_date.isoformat()
                        if candidate.publish_date
                        else None
                    ),
                    "area_name_from_list": candidate.metadata.get("area_name"),
                },
                "relevance_decision": {
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                    "project_category": decision.project_category,
                },
                "extraction_rules": [
                    "项目名称优先取公告正文中的正式项目名称；若正文被脱敏导致名称残缺，可用标题补全。",
                    "采购人、招标人、中选机构、中标供应商等字段必须按公告角色区分，不要把网站导航、推荐信息、企业名录当作字段值。",
                    "金额字段保留原文单位和符号，例如￥243,500、265万元、183300.0元。",
                    "只有公告类型为winning_bid时才抽取winning_bidder和winning_amount；采购、招标、询价、磋商等未出结果阶段不得填写中标字段。",
                    "省市优先参考列表地区，但如果正文明确给出更准确地点，以正文为准。",
                    "摘要只总结本项目正文，不要包含网页页眉、页脚、推荐公告或站点宣传语。",
                ],
                "raw_content": raw_content[:8000],
                "output_schema": {
                    "notice_type": "tender|winning_bid|change|other，必须基于详情正文语义判断公告类型：采购/招标阶段为tender，成交/中标/结果/合同签订阶段为winning_bid，变更阶段为change，无法判断为other",
                    "project_name": "string|null",
                    "purchaser": "string|null",
                    "agency": "string|null",
                    "winning_bidder": "string|null",
                    "budget_amount": "string|null",
                    "winning_amount": "string|null",
                    "province": "string|null",
                    "city": "string|null",
                    "publish_date": "YYYY-MM-DD|null",
                    "bid_open_date": "string|null",
                    "deadline": "string|null",
                    "industry_category": "string|null",
                    "summary": "string",
                    "key_requirements": ["string"],
                },
            },
            ensure_ascii=False,
        )

    def _combined_notice_prompt(
        self,
        candidate: TenderCandidate,
        raw_content: str,
        decision: TenderFilterDecision,
    ) -> str:
        return json.dumps(
            {
                "task": "先判断采购内容是否属于环境业务；如果不是环境业务，直接返回is_relevant=false，不需要结构化抽取。若是环境业务采购/招标/成交/中标/合同类公告，再在同一次响应中抽取结构化字段。",
                "judgement_logic": [
                    "第一步判断是否存在采购行为或采购结果：详情正文应体现采购人/招标人/采购标的/预算金额/投标截止/开标/成交供应商/中标金额/合同金额等采购要素之一，且语境是采购、招标、询价、磋商、竞价、成交、中标、合同或更正。",
                    "第二步判断采购内容是否属于环境业务：采购标的或服务范围应实质服务于环境监测、污染治理、生态环境执法支撑、排污口治理、环境数据能力建设、环保设施设备、环境咨询评估等。",
                    "如果只是环境影响报告书、环境影响评价受理公示、审批公示、行政审批、行政许可、批复、政府信息公开、新闻动态、政策通知或项目介绍，即使出现生态环境词，也必须判定为非目标公告。",
                    "如果采购内容只是办公用品、宣传印刷、物业餐饮、车辆维修、网络电信、家具装修等通用事务，且不直接服务环境业务，必须判定为非目标公告。",
                    "边界情况从严：无法确认采购内容属于环境业务时返回is_relevant=false。",
                ],
                "candidate": {
                    "title": candidate.title,
                    "url": candidate.url,
                    "notice_type": candidate.notice_type.value,
                    "publish_date_from_list": (
                        candidate.publish_date.isoformat()
                        if candidate.publish_date
                        else None
                    ),
                    "area_name_from_list": candidate.metadata.get("area_name"),
                },
                "prior_decision": {
                    "reason": decision.reason,
                    "confidence": decision.confidence,
                    "project_category": decision.project_category,
                },
                "extraction_rules": [
                    "仅当is_relevant=true时填写结构化字段；is_relevant=false时除reject_reason、confidence、project_category外字段可为null。",
                    "project_category必须且只能从project_category_options中的value选择一个；确认属于环境业务采购但无法归类时选择other_environment_procurement，不要输出other、null或自造分类。",
                    "notice_type必须基于详情正文语义判断：采购/招标/询价/磋商/竞价阶段为tender，成交/中标/结果/合同签订阶段为winning_bid，变更/更正/澄清阶段为change，无法判断为other。",
                    "项目名称优先取公告正文正式项目名称；正文脱敏或缺失时可用标题补全。",
                    "金额字段保留原文单位和符号，例如5600000元、650万元、1.47亿元；多分包金额可用逗号保留列表。",
                    "只有notice_type为winning_bid时才抽取winning_bidder和winning_amount；采购、招标、询价、磋商等未出结果阶段不得填写中标字段。",
                    "摘要只总结本采购项目正文，不要包含网页页眉、页脚、推荐公告或站点宣传语。",
                ],
                "project_category_options": project_category_options(),
                "raw_content": raw_content[:9000],
                "output_schema": {
                    "is_relevant": "boolean",
                    "reject_reason": "string|null，仅is_relevant=false时填写",
                    "relevance_reason": "string|null，仅is_relevant=true时填写",
                    "confidence": "number between 0 and 1",
                    "project_category": project_category_schema(),
                    "notice_type": "tender|winning_bid|change|other|null",
                    "project_name": "string|null",
                    "purchaser": "string|null",
                    "agency": "string|null",
                    "winning_bidder": "string|null",
                    "budget_amount": "string|null",
                    "winning_amount": "string|null",
                    "province": "string|null",
                    "city": "string|null",
                    "publish_date": "YYYY-MM-DD|null",
                    "bid_open_date": "string|null",
                    "deadline": "string|null",
                    "industry_category": "string|null",
                    "summary": "string|null",
                    "key_requirements": ["string"],
                },
            },
            ensure_ascii=False,
        )

    def _notice_from_data(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        raw_content: str,
        decision: TenderFilterDecision,
        data: dict[str, Any],
    ) -> TenderNotice:
        notice_type = self._notice_type_or_default(
            data.get("notice_type"), candidate.notice_type
        )
        budget_amount = self._string_or_none(data.get("budget_amount"))
        winning_bidder = None
        winning_amount = None
        if notice_type == NoticeType.WINNING_BID:
            winning_bidder = self._string_or_none(data.get("winning_bidder"))
            winning_amount = self._string_or_none(data.get("winning_amount"))
        notice = TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=notice_type,
            raw_content=raw_content,
            project_name=self._string_or_none(data.get("project_name")),
            purchaser=self._string_or_none(data.get("purchaser")),
            agency=self._string_or_none(data.get("agency")),
            winning_bidder=winning_bidder,
            budget_amount=budget_amount,
            budget_amount_wan_yuan=amount_to_wan_yuan(budget_amount),
            winning_amount=winning_amount,
            winning_amount_wan_yuan=amount_to_wan_yuan(winning_amount),
            province=self._string_or_none(data.get("province")),
            city=self._string_or_none(data.get("city")),
            publish_date=self._date_or_default(
                data.get("publish_date"), candidate.publish_date
            ),
            bid_open_date=self._string_or_none(data.get("bid_open_date")),
            deadline=self._string_or_none(data.get("deadline")),
            industry_category=normalize_project_category(data.get("industry_category"))
            or normalize_project_category(data.get("project_category"))
            or normalize_project_category(decision.project_category),
            environment_relevance=decision.is_relevant,
            filter_reason=decision.reason,
            filter_confidence=decision.confidence,
            summary=self._string_or_none(data.get("summary")) or "",
            key_requirements=self._string_list(data.get("key_requirements")),
            attachment_urls=extract_attachment_urls(detail_text, candidate.url),
        )
        notice.structured_json = self._notice_payload(notice)
        return notice

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        compact = normalized.replace(" ", "")
        if (
            not normalized
            or normalized.lower() in {"null", "none", "未知", "不详"}
            or set(compact) <= {"*"}
            or "****" in compact
        ):
            return None
        return normalized

    def _notice_type_or_default(
        self, value: Any, default: NoticeType
    ) -> NoticeType:
        normalized = str(value or "").strip().lower()
        mapping = {
            "tender": NoticeType.TENDER,
            "招标": NoticeType.TENDER,
            "招标公告": NoticeType.TENDER,
            "采购": NoticeType.TENDER,
            "采购公告": NoticeType.TENDER,
            "winning": NoticeType.WINNING_BID,
            "winning_bid": NoticeType.WINNING_BID,
            "中标": NoticeType.WINNING_BID,
            "中标公告": NoticeType.WINNING_BID,
            "成交": NoticeType.WINNING_BID,
            "成交公告": NoticeType.WINNING_BID,
            "结果公告": NoticeType.WINNING_BID,
            "合同公告": NoticeType.WINNING_BID,
            "change": NoticeType.CHANGE,
            "变更": NoticeType.CHANGE,
            "变更公告": NoticeType.CHANGE,
            "other": NoticeType.OTHER,
            "其他": NoticeType.OTHER,
        }
        return mapping.get(normalized, default)

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _date_or_default(self, value: Any, default: date | None) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return date.fromisoformat(value.strip()[:10])
            except ValueError:
                return default
        return default

    def _notice_payload(self, notice: TenderNotice) -> dict:
        return {
            "title": notice.title,
            "url": notice.url,
            "notice_type": (
                notice.notice_type.value
                if isinstance(notice.notice_type, NoticeType)
                else str(notice.notice_type)
            ),
            "project_name": notice.project_name,
            "purchaser": notice.purchaser,
            "agency": notice.agency,
            "winning_bidder": notice.winning_bidder,
            "budget_amount": notice.budget_amount,
            "budget_amount_wan_yuan": notice.budget_amount_wan_yuan,
            "winning_amount": notice.winning_amount,
            "winning_amount_wan_yuan": notice.winning_amount_wan_yuan,
            "province": notice.province,
            "city": notice.city,
            "publish_date": (
                notice.publish_date.isoformat() if notice.publish_date else None
            ),
            "bid_open_date": notice.bid_open_date,
            "deadline": notice.deadline,
            "industry_category": notice.industry_category,
            "environment_relevance": notice.environment_relevance,
            "filter_reason": notice.filter_reason,
            "filter_confidence": notice.filter_confidence,
            "summary": notice.summary,
            "key_requirements": notice.key_requirements,
            "attachment_urls": notice.attachment_urls,
        }
