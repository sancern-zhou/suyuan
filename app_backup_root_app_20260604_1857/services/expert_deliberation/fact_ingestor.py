"""Convert user supplied tables, reports, and data ids into facts."""

from __future__ import annotations

from .fact_ledger import FactLedger
from .llm_fact_extractor import LLMFactExtractor
from .schemas import DeliberationRequest


class FactIngestor:
    def __init__(self, llm_extractor: LLMFactExtractor | None = None) -> None:
        self.llm_extractor = llm_extractor

    def build(self, request: DeliberationRequest) -> FactLedger:
        raise RuntimeError("专家会商事实入账必须使用异步 LLM 抽取路径 build_async")

    async def build_async(self, request: DeliberationRequest) -> FactLedger:
        ledger = FactLedger()
        extractor = self.llm_extractor or LLMFactExtractor()
        if not request.options.enable_llm_fact_extraction:
            raise RuntimeError("专家会商事实入账必须启用 LLM 抽取，当前请求关闭了 enable_llm_fact_extraction")

        await self._ingest_tables_async(ledger, request, extractor)
        await self._ingest_report_text_async(ledger, request, request.monthly_report_text, "monthly_trace_report", extractor)
        await self._ingest_report_text_async(ledger, request, request.stage5_report_text, "stage5_analysis", extractor)
        await self._ingest_data_ids_async(ledger, request, extractor)
        if not ledger.all():
            raise RuntimeError("LLM事实入账未产生任何事实，请提供会商表格、报告文本或可补证 data_id")
        return ledger

    async def _ingest_tables_async(
        self,
        ledger: FactLedger,
        request: DeliberationRequest,
        extractor: LLMFactExtractor,
    ) -> None:
        if not request.consultation_tables:
            return
        facts = await extractor.extract_table_facts(
            request=request,
            tables=request.consultation_tables,
            start_index=len(ledger.all()) + 1,
        )
        if not facts:
            raise RuntimeError("LLM未能从会商表格中抽取事实，已按严格模式终止")
        ledger.extend(facts)

    async def _ingest_report_text_async(
        self,
        ledger: FactLedger,
        request: DeliberationRequest,
        text: str,
        source_type: str,
        extractor: LLMFactExtractor,
    ) -> None:
        if not text.strip():
            return
        llm_facts = await extractor.extract_report_facts(
            request=request,
            text=text,
            source_type=source_type,
            start_index=len(ledger.all()) + 1,
        )
        if not llm_facts:
            raise RuntimeError(f"LLM未能从{source_type}中抽取事实，已按严格模式终止")
        ledger.extend(llm_facts)

    async def _ingest_data_ids_async(
        self,
        ledger: FactLedger,
        request: DeliberationRequest,
        extractor: LLMFactExtractor,
    ) -> None:
        if not request.data_ids:
            return
        facts = await extractor.extract_data_asset_facts(request=request, start_index=len(ledger.all()) + 1)
        if not facts:
            raise RuntimeError("LLM未能从 data_id 清单中抽取数据资产事实，已按严格模式终止")
        ledger.extend(facts)
