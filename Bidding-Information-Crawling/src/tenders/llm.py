from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from typing import Any, Dict, Sequence

from .extractor import amount_to_wan_yuan, clean_detail_content, extract_attachment_urls
from .models import NoticeType, TenderCandidate, TenderFilterDecision, TenderNotice


class OpenAICompatibleTenderLLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
    ):
        self._load_environment()
        self.api_key = api_key or self._first_configured_value(
            [
                "TENDER_LLM_API_KEY",
                "OPENAI_API_KEY",
                "DASHSCOPE_API_KEY",
                "QWEN_API_KEY",
            ]
        )
        self.base_url = self._normalize_base_url(
            base_url or os.getenv("TENDER_LLM_BASE_URL") or self._default_base_url()
        )
        self.model = (
            model
            or os.getenv("TENDER_LLM_MODEL")
            or os.getenv("QWEN_MODEL")
            or os.getenv("DASHSCOPE_MODEL")
            or self._default_model(self.base_url)
        )
        self.temperature = temperature
        if not self.api_key:
            raise RuntimeError(
                "启用 LLM 时需要配置 TENDER_LLM_API_KEY、OPENAI_API_KEY、DASHSCOPE_API_KEY 或 QWEN_API_KEY"
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
            project_category=data.get("project_category")
            or rule_decision.project_category,
        )

    async def review_candidates(
        self,
        candidates: Sequence[TenderCandidate],
        rule_decision: TenderFilterDecision,
    ) -> dict[str, TenderFilterDecision]:
        prompt = self._candidate_batch_prompt(candidates, rule_decision)
        data = await self._json_chat(prompt)
        rows = data.get("decisions", []) if isinstance(data, dict) else []
        decisions: dict[str, TenderFilterDecision] = {}
        candidate_by_index = {
            index + 1: candidate for index, candidate in enumerate(candidates)
        }
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
                project_category=row.get("project_category"),
            )
        return decisions

    async def extract_notice(
        self,
        candidate: TenderCandidate,
        detail_text: str,
        decision: TenderFilterDecision,
    ) -> TenderNotice:
        raw_content = clean_detail_content(detail_text)
        prompt = self._notice_prompt(candidate, raw_content, decision)
        data = await self._json_chat(prompt)

        budget_amount = self._string_or_none(data.get("budget_amount"))
        winning_amount = self._string_or_none(data.get("winning_amount"))
        notice = TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=raw_content,
            project_name=self._string_or_none(data.get("project_name")),
            purchaser=self._string_or_none(data.get("purchaser")),
            agency=self._string_or_none(data.get("agency")),
            winning_bidder=self._string_or_none(data.get("winning_bidder")),
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
            industry_category=self._string_or_none(data.get("industry_category"))
            or decision.project_category,
            environment_relevance=decision.is_relevant,
            filter_reason=decision.reason,
            filter_confidence=decision.confidence,
            summary=self._string_or_none(data.get("summary")) or "",
            key_requirements=self._string_list(data.get("key_requirements")),
            attachment_urls=extract_attachment_urls(detail_text, candidate.url),
        )
        notice.structured_json = self._notice_payload(notice)
        return notice

    async def refine_notice(self, notice: TenderNotice) -> TenderNotice:
        return notice

    async def _json_chat(self, prompt: str) -> Dict[str, Any]:
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
        client = AsyncOpenAI(**client_kwargs)
        max_retries = int(os.getenv("TENDER_LLM_MAX_RETRIES", "3"))
        response = None
        for attempt in range(1, max_retries + 1):
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
            except (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                RateLimitError,
            ):
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(min(2 * attempt, 8))
        if response is None:
            raise RuntimeError("LLM响应为空")
        content = response.choices[0].message.content or "{}"
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content.removeprefix("json").strip()
        return json.loads(content)

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
                    "DASHSCOPE_API_KEY",
                    "QWEN_API_KEY",
                    "TENDER_LLM_BASE_URL",
                    "TENDER_LLM_MODEL",
                    "QWEN_MODEL",
                    "DASHSCOPE_MODEL",
                }
                and value
                and (key not in os.environ or self._looks_placeholder(os.environ[key]))
            ):
                os.environ[key] = value

    def _default_base_url(self) -> str | None:
        if os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY"):
            return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return None

    def _default_model(self, base_url: str | None = None) -> str:
        if base_url and "dashscope.aliyuncs.com" in base_url:
            return "qwen-plus"
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
                    "project_category": "environment_monitoring|pollution_control|environment_consulting|law_enforcement_support|other|null",
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
                "task": "批量判断招投标候选项目是否属于环境业务项目。请逐条基于标题、列表摘要和公告语境进行语义判断，不要依赖固定关键词匹配。",
                "include_when": [
                    "项目实质内容服务于环境监测、污染治理、生态环境分区管控、排污口治理、环境咨询评估、生态环境执法支撑、环保设施设备或环境数据能力建设。",
                    "采购单位不是生态环境部门，但项目本身明确属于环境治理、环境监测、环保咨询或污染防治业务。",
                ],
                "exclude_when": [
                    "只是生态环境部门采购通用办公、后勤保障、车辆维修、广告宣传、网络电信、物业餐饮、装修家具等非环境业务内容。",
                    "只是行政审批、公示、受理、环评批复等政府信息公开事项，并非采购或招投标项目。",
                    "环境相关内容仅出现在网页导航、推荐信息、站点热词或无关上下文中。",
                ],
                "candidates": [
                    {
                        "index": index + 1,
                        "title": candidate.title,
                        "url": candidate.url,
                        "notice_type": candidate.notice_type.value,
                        "raw_list_text": candidate.raw_list_text,
                    }
                    for index, candidate in enumerate(candidates)
                ],
                "prior_decision": {
                    "is_relevant": rule_decision.is_relevant,
                    "reason": rule_decision.reason,
                    "confidence": rule_decision.confidence,
                },
                "output_schema": {
                    "decisions": [
                        {
                            "index": "number",
                            "is_relevant": "boolean",
                            "reason": "string",
                            "confidence": "number between 0 and 1",
                            "project_category": "environment_monitoring|pollution_control|environment_consulting|law_enforcement_support|other|null",
                        }
                    ]
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
                    "省市优先参考列表地区，但如果正文明确给出更准确地点，以正文为准。",
                    "摘要只总结本项目正文，不要包含网页页眉、页脚、推荐公告或站点宣传语。",
                ],
                "raw_content": raw_content[:8000],
                "output_schema": {
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

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.lower() in {"null", "none", "未知", "不详"}:
            return None
        return normalized

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
