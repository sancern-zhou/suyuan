import pytest

from app.services.expert_deliberation.fact_ingestor import FactIngestor
from app.services.expert_deliberation.schemas import DeliberationRequest, FactQuality, FactRecord, TableInput


class FakeExtractor:
    def __init__(self, table_facts=None, report_facts=None, data_facts=None):
        self.table_facts = table_facts or []
        self.report_facts = report_facts or []
        self.data_facts = data_facts or []
        self.table_called = False

    async def extract_table_facts(self, request, tables, start_index):
        self.table_called = True
        return self.table_facts

    async def extract_report_facts(self, request, text, source_type, start_index):
        return self.report_facts

    async def extract_data_asset_facts(self, request, start_index):
        return self.data_facts


def make_fact(fact_id="fact_consultation_table_llm_0001"):
    return FactRecord(
        fact_id=fact_id,
        source_type="consultation_table",
        source_ref={"llm_extracted": True},
        region="广东省",
        statement="广州 PM2.5 月均浓度为 28 微克/立方米。",
        method="LLM结构化事实抽取",
        quality=FactQuality(confidence=0.9),
        tags=["监测", "PM2.5"],
    )


@pytest.mark.asyncio
async def test_fact_ingestor_requires_llm_for_tables():
    extractor = FakeExtractor(table_facts=[make_fact()])
    request = DeliberationRequest(
        consultation_tables=[TableInput(name="会商表", rows=[{"城市": "广州", "PM2.5": 28}])],
    )

    ledger = await FactIngestor(llm_extractor=extractor).build_async(request)

    assert extractor.table_called is True
    assert ledger.all()[0].method == "LLM结构化事实抽取"


@pytest.mark.asyncio
async def test_fact_ingestor_fails_when_llm_returns_no_table_facts():
    extractor = FakeExtractor(table_facts=[])
    request = DeliberationRequest(
        consultation_tables=[TableInput(name="会商表", rows=[{"城市": "广州", "PM2.5": 28}])],
    )

    with pytest.raises(RuntimeError, match="LLM未能从会商表格中抽取事实"):
        await FactIngestor(llm_extractor=extractor).build_async(request)


def test_sync_fact_ingestor_is_disabled():
    with pytest.raises(RuntimeError, match="异步 LLM 抽取路径"):
        FactIngestor(llm_extractor=FakeExtractor()).build(DeliberationRequest())
