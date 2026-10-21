"""固定工作流叶子模式的结构化交付 schema 默认注入。"""

from app.agent.workflow.protocol import EXPERT_ANALYSIS_RESULT_SCHEMA
from app.tools.agent_tools.call_sub_agent import ensure_structured_delivery_schema


def test_fixed_workflow_leaf_gets_default_schema():
    schema = ensure_structured_delivery_schema("query_forecast", None)
    assert isinstance(schema, dict) and schema
    assert schema["required"] == EXPERT_ANALYSIS_RESULT_SCHEMA["required"]


def test_explicit_schema_passes_through_unmodified():
    caller = {"type": "object", "required": ["answer"]}
    assert ensure_structured_delivery_schema("query_forecast", caller) is caller


def test_non_workflow_target_unchanged():
    assert ensure_structured_delivery_schema("office", None) is None
    assert ensure_structured_delivery_schema("expert_meteorology", None) is None


def test_returned_schema_is_isolated_copy():
    schema = ensure_structured_delivery_schema("query_monitoring_city", None)
    schema["required"].append("mutated")
    assert "mutated" not in EXPERT_ANALYSIS_RESULT_SCHEMA["required"]
