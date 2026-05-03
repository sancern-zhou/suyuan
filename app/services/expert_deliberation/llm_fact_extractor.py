"""LLM-backed fact extraction for expert deliberation."""

from __future__ import annotations

from typing import Any

import structlog

from .schemas import DeliberationRequest, FactQuality, FactRecord

logger = structlog.get_logger()


class LLMFactExtractor:
    """Extract auditable FactRecord candidates with LLM JSON output."""

    MAX_SOURCE_CHARS = 12000

    def __init__(self, llm_service: object | None = None) -> None:
        self.llm_service = llm_service

    def is_available(self) -> bool:
        if self.llm_service is None:
            try:
                from app.services.llm_service import LLMService

                self.llm_service = LLMService()
            except Exception as exc:
                raise RuntimeError(f"LLM fact extractor is unavailable: {exc}") from exc
        if not getattr(self.llm_service, "base_url", None):
            raise RuntimeError("LLM fact extractor is unavailable: LLM base_url is not configured")
        return True

    async def extract_report_facts(
        self,
        request: DeliberationRequest,
        text: str,
        source_type: str,
        start_index: int,
    ) -> list[FactRecord]:
        if not text.strip():
            return []
        return await self._extract_from_prompt(
            request=request,
            prompt=self._build_text_prompt(request, text[: self.MAX_SOURCE_CHARS], source_type),
            source_type=source_type,
            start_index=start_index,
            max_facts=80,
        )

    async def extract_table_facts(
        self,
        request: DeliberationRequest,
        tables: list[Any],
        start_index: int,
    ) -> list[FactRecord]:
        if not tables:
            return []
        serializable_tables = []
        for table in tables:
            rows = getattr(table, "rows", []) or []
            serializable_tables.append(
                {
                    "name": getattr(table, "name", ""),
                    "source_type": getattr(table, "source_type", "consultation_table"),
                    "rows": rows[:200],
                    "row_count": len(rows),
                }
            )
        prompt = self._build_table_prompt(request, serializable_tables)
        return await self._extract_from_prompt(
            request=request,
            prompt=prompt,
            source_type="consultation_table",
            start_index=start_index,
            max_facts=120,
        )

    async def extract_data_asset_facts(
        self,
        request: DeliberationRequest,
        start_index: int,
    ) -> list[FactRecord]:
        if not request.data_ids:
            return []
        prompt = self._build_data_asset_prompt(request)
        return await self._extract_from_prompt(
            request=request,
            prompt=prompt,
            source_type="data_id",
            start_index=start_index,
            max_facts=30,
        )

    async def _extract_from_prompt(
        self,
        request: DeliberationRequest,
        prompt: str,
        source_type: str,
        start_index: int,
        max_facts: int,
    ) -> list[FactRecord]:
        self.is_available()
        try:
            payload = await self.llm_service.call_llm_with_json_response(prompt, max_retries=2)
        except Exception as exc:
            logger.error("llm_fact_extraction_failed", source_type=source_type, error=str(exc))
            raise RuntimeError(f"LLM fact extraction failed for {source_type}: {exc}") from exc

        raw_facts = payload.get("facts", [])
        if not isinstance(raw_facts, list):
            raise RuntimeError(f"LLM fact extraction for {source_type} returned invalid JSON: facts must be a list")

        facts: list[FactRecord] = []
        for offset, item in enumerate(raw_facts[:max_facts]):
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            if len(statement) < 8:
                continue
            confidence = item.get("confidence", 0.72)
            try:
                confidence = max(0.0, min(float(confidence), 1.0))
            except (TypeError, ValueError):
                confidence = 0.72

            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
            source_ref: dict[str, Any] = {"llm_extracted": True, "source_type": source_type}
            if item.get("evidence_quote"):
                source_ref["evidence_quote"] = str(item["evidence_quote"])[:500]

            facts.append(
                FactRecord(
                    fact_id=f"fact_{source_type}_llm_{start_index + offset:04d}",
                    source_type=source_type,
                    source_ref=source_ref,
                    time_range=request.time_range,
                    region=str(item.get("region") or request.region),
                    city=item.get("city"),
                    pollutant=item.get("pollutant"),
                    fact_type=str(item.get("fact_type") or "report_finding"),
                    statement=statement,
                    metrics=metrics,
                    method="LLM结构化事实抽取",
                    quality=FactQuality(
                        completeness="medium",
                        temporal_coverage=request.time_range.display or "unknown",
                        confidence=confidence,
                    ),
                    tags=[str(tag) for tag in tags] or ["LLM事实"],
                )
            )
        return facts

    def _build_text_prompt(self, request: DeliberationRequest, text: str, source_type: str) -> str:
        pollutants = "、".join(request.pollutants) or "未指定"
        return f"""
你是空气质量会商的事实入账引擎。请从材料中抽取可审计事实，输出严格 JSON。

会商主题：{request.topic}
区域：{request.region}
时段：{request.time_range.display or request.time_range.start or ""}
重点污染物：{pollutants}
来源类型：{source_type}

抽取要求：
1. 只抽取材料明确支持的事实，不要推理补全。
2. 每条事实必须可被专家引用，statement 要完整表达主体、指标、时间/区域、变化或结论。
3. 数值、同比、环比、浓度、贡献率等放入 metrics。
4. evidence_quote 填原文短证据。
5. tags 可使用：监测、气象、传输、组分、源解析、PM2.5、O3、数据资产、管控。

输出 JSON 格式：
{{
  "facts": [
    {{
      "statement": "...",
      "fact_type": "observation|report_finding|causal_hint|data_asset|supplement",
      "region": "...",
      "city": "...或null",
      "pollutant": "PM2.5/O3/其他或null",
      "metrics": {{}},
      "tags": ["..."],
      "evidence_quote": "...",
      "confidence": 0.0
    }}
  ]
}}

材料：
{text}
""".strip()

    def _build_table_prompt(self, request: DeliberationRequest, tables: list[dict[str, Any]]) -> str:
        pollutants = "、".join(request.pollutants) or "未指定"
        table_json = json.dumps(tables, ensure_ascii=False, default=str)[: self.MAX_SOURCE_CHARS]
        return f"""
你是空气质量会商的事实入账引擎。请从会商表格 JSON 中抽取可审计事实，输出严格 JSON。

会商主题：{request.topic}
区域：{request.region}
时段：{request.time_range.display or request.time_range.start or ""}
重点污染物：{pollutants}
来源类型：consultation_table

抽取要求：
1. 必须理解表头和行值，抽取城市、污染物、浓度、同比、环比、污染过程、排名、超标、首要污染物等事实。
2. 只抽取表格明确支持的事实，不要用关键词规则，也不要补写表格没有的信息。
3. statement 必须能独立阅读，并引用表格名称或行上下文。
4. metrics 保存数值、单位、同比、环比、贡献率等结构化指标。
5. evidence_quote 填写可回溯的表名、行号或关键单元格。

输出 JSON 格式：
{{
  "facts": [
    {{
      "statement": "...",
      "fact_type": "observation|ranking|comparison|pollution_episode|data_asset",
      "region": "...",
      "city": "...或null",
      "pollutant": "PM2.5/O3/其他或null",
      "metrics": {{}},
      "tags": ["监测","PM2.5","O3","污染过程"],
      "evidence_quote": "...",
      "confidence": 0.0
    }}
  ]
}}

表格 JSON：
{table_json}
""".strip()

    def _build_data_asset_prompt(self, request: DeliberationRequest) -> str:
        payload = json.dumps({"data_ids": request.data_ids}, ensure_ascii=False)
        return f"""
你是空气质量会商的事实入账引擎。请把已有 data_id 清单转成可审计的数据资产事实，输出严格 JSON。

区域：{request.region}
时段：{request.time_range.display or request.time_range.start or ""}

要求：
1. 只能描述 data_id 本身可作为后续补证数据资产，不得声称已经读取其中数据。
2. schema 或数据类型只能依据 data_id 字符串中明确出现的信息。
3. 每个 data_id 至少生成一条 data_asset 事实。

输出 JSON 格式：
{{
  "facts": [
    {{
      "statement": "...",
      "fact_type": "data_asset",
      "region": "...",
      "city": null,
      "pollutant": null,
      "metrics": {{}},
      "tags": ["数据资产"],
      "evidence_quote": "...",
      "confidence": 0.0
    }}
  ]
}}

data_id 清单：
{payload}
""".strip()
