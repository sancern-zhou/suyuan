import pytest
import importlib.util
import sys
import types
from pathlib import Path

from app.services.expert_deliberation.fact_ingestor import FactIngestor
from app.services.expert_deliberation.discussion_ledger import DiscussionLedger
from app.services.expert_deliberation.deliberation_engine import ExpertDeliberationEngine
from app.services.expert_deliberation.expert_agent_runner import LLMExpertAgentRunner
from app.services.expert_deliberation.expert_registry import get_default_experts
from app.services.expert_deliberation.llm_fact_extractor import LLMFactExtractor
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


class FakeAnthropicMessages:
    async def create(self, **kwargs):
        text_block = type("TextBlock", (), {"text": '{"facts": []}'})()
        return type("Response", (), {"content": [text_block]})()


class FakeChunkingAnthropicMessages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        statement = f"第{len(self.calls)}块报告明确记录广州 PM2.5 污染特征。"
        text_block = type(
            "TextBlock",
            (),
            {
                "text": (
                    '{"facts":[{"statement":"'
                    + statement
                    + '","fact_type":"report_finding","region":"广东省","city":"广州",'
                    '"pollutant":"PM2.5","metrics":{},"tags":["监测","PM2.5"],'
                    '"evidence_quote":"报告原文","confidence":0.8}]}'
                )
            },
        )()
        return type("Response", (), {"content": [text_block]})()


class FakeNormalizeAnthropicMessages:
    async def create(self, **kwargs):
        text_block = type(
            "TextBlock",
            (),
            {
                "text": (
                    '{"position":"归一化观点","used_fact_ids":[],"claims":[],'
                    '"tool_call_plan":[],"questions_to_others":[],"uncertainties":[]}'
                )
            },
        )()
        return type("Response", (), {"content": [text_block]})()


class FakeAnthropicService:
    base_url = "https://api.xiaomimimo.com/anthropic"
    model = "mimo-v2.5-pro"
    temperature = 0.3

    def __init__(self):
        self.anthropic_client = type("Client", (), {"messages": FakeAnthropicMessages()})()

    async def call_llm_with_json_response(self, prompt, max_retries=2):
        raise AssertionError("OpenAI-compatible JSON endpoint should not be used when anthropic_client is available")


class FakeChunkingAnthropicService(FakeAnthropicService):
    def __init__(self):
        self.messages = FakeChunkingAnthropicMessages()
        self.anthropic_client = type("Client", (), {"messages": self.messages})()


class FakeNormalizeAnthropicService(FakeAnthropicService):
    def __init__(self):
        self.anthropic_client = type("Client", (), {"messages": FakeNormalizeAnthropicMessages()})()


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


def test_default_discussion_rounds_are_maximum_not_fixed_two():
    request = DeliberationRequest()

    assert request.options.max_discussion_rounds == 5


@pytest.mark.asyncio
async def test_llm_fact_extractor_uses_anthropic_client_for_json():
    extractor = LLMFactExtractor(llm_service=FakeAnthropicService())

    payload = await extractor._call_llm_json("输出JSON")

    assert payload == {"facts": []}


@pytest.mark.asyncio
async def test_report_fact_extraction_splits_long_text_for_llm():
    service = FakeChunkingAnthropicService()
    extractor = LLMFactExtractor(llm_service=service)
    request = DeliberationRequest(region="广东省")
    long_report = "\n".join([f"第{i}段：广州 PM2.5 污染过程描述。" + "监测事实" * 60 for i in range(8)])

    facts = await extractor.extract_report_facts(request, long_report, "monthly_trace_report", start_index=10)

    assert len(service.messages.calls) > 1
    assert all(call["timeout"] == extractor.FACT_EXTRACTION_TIMEOUT_SECONDS for call in service.messages.calls)
    assert [fact.fact_id for fact in facts] == [
        f"fact_monthly_trace_report_llm_{index:04d}"
        for index in range(10, 10 + len(facts))
    ]


@pytest.mark.asyncio
async def test_expert_json_normalization_uses_anthropic_client(monkeypatch):
    class FakeLLMServiceFactory:
        def __new__(cls):
            return FakeNormalizeAnthropicService()

    fake_module = types.ModuleType("app.services.llm_service")
    fake_module.LLMService = FakeLLMServiceFactory
    monkeypatch.setitem(sys.modules, "app.services.llm_service", fake_module)
    expert = get_default_experts()[0]

    payload = await LLMExpertAgentRunner()._parse_or_normalize_json(
        expert,
        "不是JSON的最终回答",
        [{"type": "thought", "data": {"text": "需要归一化"}}],
    )

    assert payload["position"] == "归一化观点"


def test_deliberation_modes_are_isolated_from_generic_expert_mode():
    registry_path = Path(__file__).resolve().parents[1] / "app" / "agent" / "prompts" / "tool_registry.py"
    spec = importlib.util.spec_from_file_location("backend_tool_registry_for_test", registry_path)
    assert spec and spec.loader
    tool_registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool_registry)
    get_tools_by_mode = tool_registry.get_tools_by_mode

    meteorology_tools = get_tools_by_mode("deliberation_meteorology")
    chemistry_tools = get_tools_by_mode("deliberation_chemistry")
    monitoring_tools = get_tools_by_mode("deliberation_monitoring")
    reviewer_tools = get_tools_by_mode("deliberation_reviewer")

    assert "query_new_standard_report" in monitoring_tools
    assert "execute_python" in monitoring_tools
    assert "calculate_iaqi" not in monitoring_tools
    assert "meteorological_trajectory_analysis" not in monitoring_tools
    assert "calculate_pm_pmf" not in monitoring_tools

    assert "meteorological_trajectory_analysis" in meteorology_tools
    assert "analyze_upwind_enterprises" in meteorology_tools
    assert "calculate_pm_pmf" not in meteorology_tools

    assert "get_vocs_data" in chemistry_tools
    assert "calculate_pm_pmf" in chemistry_tools
    assert "meteorological_trajectory_analysis" not in chemistry_tools

    assert set(reviewer_tools) == {"read_data_registry", "TodoWrite"}
    assert "call_sub_agent" not in reviewer_tools

    modes = {expert.expert_id: expert.deliberation_mode for expert in get_default_experts()}
    assert modes == {
        "monitoring_feature_expert": "deliberation_monitoring",
        "weather_transport_expert": "deliberation_meteorology",
        "chemistry_source_expert": "deliberation_chemistry",
        "reviewer_moderator": "deliberation_reviewer",
    }


def test_discussion_ledger_routes_questions_and_keeps_latest_analysis():
    ledger = DiscussionLedger()
    first = get_default_experts()[0]
    second = get_default_experts()[1]
    analysis = LLMExpertAgentRunner()._to_analysis(
        first,
        {
            "position": "气象输送初判",
            "used_fact_ids": [],
            "claims": [{"claim": "存在输送待核查", "confidence": 0.6}],
            "questions_to_others": [
                {
                    "target_expert": second.expert_id,
                    "question": "组分证据是否支持输送影响？",
                    "reason": "交叉验证",
                }
            ],
            "tool_call_plan": [],
            "uncertainties": [],
        },
        [],
    )
    ledger.add_analysis(analysis, round_index=1, turn_type="initial_opinion")

    assert ledger.question_targets({second.expert_id}) == {second.expert_id}
    context = ledger.summary_for_expert(second.expert_id, "cross_review")
    assert "指向你的问题" in context
    assert "组分证据是否支持输送影响" in context

    revised = analysis.model_copy(update={"position": "气象输送复议"})
    ledger.add_analysis(revised, round_index=2, turn_type="cross_review")

    latest = {item.expert_id: item.position for item in ledger.latest_analyses()}
    assert latest[first.expert_id] == "气象输送复议"


def test_reviewer_controls_discussion_stop():
    engine = ExpertDeliberationEngine()
    reviewer = get_default_experts()[-1]
    stop_analysis = LLMExpertAgentRunner()._to_analysis(
        reviewer,
        {
            "position": "证据链完整，可以结束讨论。",
            "used_fact_ids": [],
            "claims": [{"claim": "可形成会商结论", "confidence": 0.8}],
            "questions_to_others": [],
            "tool_call_plan": [],
            "uncertainties": [],
        },
        [],
    )
    continue_analysis = stop_analysis.model_copy(
        update={
            "position": "仍需补证后再判断。",
            "questions_to_others": [
                {"target_expert": "chemistry_source_expert", "question": "请补充PMF依据", "reason": "审查"}
            ],
        }
    )

    assert engine._reviewer_allows_stop(stop_analysis) is True
    assert engine._reviewer_allows_stop(continue_analysis) is False


def test_evidence_matrix_and_timeline_are_built_from_discussion():
    engine = ExpertDeliberationEngine()
    expert = get_default_experts()[0]
    fact = make_fact()
    analysis = LLMExpertAgentRunner()._to_analysis(
        expert,
        {
            "position": "气象输送证据支持污染累积。",
            "used_fact_ids": [fact.fact_id],
            "claims": [
                {
                    "claim": "气象输送证据支持污染累积",
                    "supporting_facts": [fact.fact_id],
                    "missing_facts": [],
                    "confidence": 0.82,
                }
            ],
            "questions_to_others": [],
            "tool_call_plan": [],
            "uncertainties": [],
        },
        [fact],
    )
    discussion = DiscussionLedger()
    discussion.add_analysis(analysis, round_index=1, turn_type="initial_opinion")

    matrix = engine._build_evidence_matrix([analysis])
    timeline = engine._build_timeline_events([fact], discussion, matrix)

    assert matrix[0].writability == "可写"
    assert matrix[0].evidence_fact_ids == [fact.fact_id]
    assert timeline[0].stage == "fact_ingestion"
    assert any(event.stage == "initial_opinion" for event in timeline)
    assert timeline[-1].stage == "evidence_matrix"


def test_deliberation_prompt_files_match_merged_expert_roles():
    prompt_root = Path(__file__).resolve().parents[2] / "backend" / "config" / "prompts"
    monitoring_prompt = (prompt_root / "monitoring_expert.md").read_text(encoding="utf-8")
    weather_prompt = (prompt_root / "weather_expert.md").read_text(encoding="utf-8")
    chemistry_prompt = (prompt_root / "chemical_expert_pm.md").read_text(encoding="utf-8")
    reviewer_prompt = (prompt_root / "report_expert.md").read_text(encoding="utf-8")

    assert "常规监测与污染特征专家" in monitoring_prompt
    assert "气象-输送会商专家" in weather_prompt
    assert "化学-来源会商专家" in chemistry_prompt
    assert "会商审查与统稿员" in reviewer_prompt

    for prompt in [monitoring_prompt, weather_prompt, chemistry_prompt, reviewer_prompt]:
        assert "最终回答必须严格服从用户消息中的 JSON schema" in prompt
        assert "不要输出 Markdown 报告" in prompt
