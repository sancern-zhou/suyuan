"""阶段 C 回归：交付验收清单（delivery_checklists）与 mandate 授权边界。"""

import pytest

from app.agent.workflow.delivery_checklists import (
    checklist_text,
    evaluate_delivery_checklist,
)
from app.tools.agent_tools.call_sub_agent import CallSubAgentTool

GOOD_RESULT = {
    "status": "completed",
    "findings": [{"finding": "x"}],
    "evidence": [{"source": "y"}],
    "uncertainties": [],
    "data_gaps": [],
}


def test_checklist_text_has_generic_gap_discipline():
    text = checklist_text("expert_meteorology")
    assert "data_gaps" in text
    assert "起报时间" in text  # 按模式条目


def test_checklist_text_unknown_mode_keeps_generic():
    text = checklist_text("unknown_mode")
    assert "data_gaps" in text
    assert "起报时间" not in text


def test_evaluate_missing_data_gaps_is_violation():
    violations = evaluate_delivery_checklist("expert_meteorology", {"status": "completed"})
    assert any(v["path"] == "$.data_gaps" for v in violations)


def test_evaluate_present_gaps_pass():
    assert evaluate_delivery_checklist("expert_meteorology", GOOD_RESULT) == []


def test_evaluate_gaps_alias_accepted():
    result = {**GOOD_RESULT, "data_gaps": None, "gaps": ["缺同期气象"]}
    assert evaluate_delivery_checklist("expert_analysis", result) == []


def test_evaluate_wrong_type_is_violation():
    result = {**GOOD_RESULT, "data_gaps": "无"}
    violations = evaluate_delivery_checklist("expert_analysis", result)
    assert any(v["path"] == "$.data_gaps" and v["expected"] == "array" for v in violations)


def test_evaluate_mandate_requires_scope():
    mandate = {"region": "许昌", "time_range": "2026-10"}
    violations = evaluate_delivery_checklist("expert_analysis", GOOD_RESULT, mandate)
    assert any(v["path"] == "$.scope" for v in violations)
    scoped = {**GOOD_RESULT, "scope": {"region": "许昌", "time_range": "2026-10"}}
    assert evaluate_delivery_checklist("expert_analysis", scoped, mandate) == []


def test_evaluate_without_mandate_skips_scope():
    assert evaluate_delivery_checklist("expert_analysis", GOOD_RESULT) == []


def _tool():
    return CallSubAgentTool(memory_manager=None, llm_planner=None, tool_executor=None)


def test_tool_schema_documents_mandate():
    schema = _tool().get_function_schema()
    mandate = schema["parameters"]["properties"]["mandate"]
    assert set(mandate["properties"]) == {
        "region",
        "time_range",
        "metrics",
        "responsibility",
    }


def test_tool_checklist_observe_records_without_blocking(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "delivery_checklist_mode", "observe", raising=False)
    blocking, observed = _tool()._evaluate_delivery_checklist(
        "expert_meteorology", None, {"status": "completed"}
    )
    assert blocking == []
    assert any(v["path"] == "$.data_gaps" for v in observed)


def test_tool_checklist_enforce_blocks(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "delivery_checklist_mode", "enforce", raising=False)
    blocking, observed = _tool()._evaluate_delivery_checklist(
        "expert_meteorology", None, {"status": "completed"}
    )
    assert blocking == observed
    assert any(v["path"] == "$.data_gaps" for v in blocking)


def test_tool_checklist_off_skips(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "delivery_checklist_mode", "off", raising=False)
    blocking, observed = _tool()._evaluate_delivery_checklist(
        "expert_meteorology", None, {"status": "completed"}
    )
    assert blocking == [] and observed == []


def test_tool_checklist_non_structured_result_skipped(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "delivery_checklist_mode", "enforce", raising=False)
    blocking, observed = _tool()._evaluate_delivery_checklist(
        "expert_meteorology", None, None
    )
    assert blocking == [] and observed == []


def test_result_card_surfaces_data_gaps():
    from app.social.assistant_runs import build_delegation_result_card

    item = {
        "run_id": "delegation_" + "a" * 32,
        "result": {
            "status": "success",
            "data": {
                "file_paths": [],
                "result_envelope": {
                    "summary": "结论摘要",
                    "outputs": {"data_gaps": ["缺同期气象数据", "站点 X 审核数据未发布"]},
                },
            },
        },
    }
    card = build_delegation_result_card(item, "x" * 5000)
    assert card["data_gaps"] == ["缺同期气象数据", "站点 X 审核数据未发布"]


def test_result_card_empty_gaps_without_envelope():
    from app.social.assistant_runs import build_delegation_result_card

    card = build_delegation_result_card({"run_id": "r"}, "x")
    assert card["data_gaps"] == []
