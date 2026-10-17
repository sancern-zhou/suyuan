from app.tools.query.jiangsu_cube_metrics.semantic_registry import (
    cube_metadata,
    load_registry,
)
from app.tools.query.jiangsu_cube_metrics.tool import CATALOG
from app.tools.query.jiangsu_ops_sql_query.tool import ExecuteJiangsuOpsSQLQueryTool
from app.tools.query.jiangsu_cube_metrics.result_contract import validate_result
from app.tools.query.jiangsu_cube_metrics.tool import JiangsuQueryMetricsTool
from app.tools.query.jiangsu_cube_metrics.quality_policy import quality_guidance
import yaml
from app.utils.path_config import resolve_agent_path
import asyncio


def test_registry_contains_metric_definition_and_catalog_fallback():
    registry = load_registry()
    assert registry["version"] == 1
    metadata = cube_metadata("WorkOrder", CATALOG)
    metric = metadata["measures"]["responseWithin2hRate"]
    assert metric["denominator"] == "responseEvaluable"
    assert metadata["dataset"] == "mart_work_order_analysis"


def test_registry_falls_back_to_catalog_titles_for_unregistered_measures():
    metadata = cube_metadata("StationEnvPower", CATALOG)
    assert metadata["measures"]["avgValue"]["name"] == "平均动环值(数值点)"


def test_sql_evidence_resolves_registered_dataset_and_quality_state():
    tool = ExecuteJiangsuOpsSQLQueryTool
    assert tool._datasets_from_sql(
        "select station_code from jiangsu_mart.mart_work_order_analysis "
        "join mart_alarm_event_analysis using (station_code)"
    ) == ["mart_work_order_analysis", "mart_alarm_event_analysis"]
    assert tool._quality_status_from_checks([]) == "unknown"
    assert tool._quality_status_from_checks([{"status": "WARN"}]) == "degraded"
    assert tool._quality_status_from_checks([{"status": "FAIL"}]) == "blocked"


def test_sparse_result_contract_only_requires_context_for_metric_queries():
    payload = {
        "success": True,
        "data": [],
        "semantic_context": {
            "dataset": "mart_work_order_analysis",
            "grain": "one row per fault work order",
            "applicability": "fault orders",
            "data_as_of": None,
            "metric_definitions": {"count": {"name": "工单量"}},
        },
        "quality_status": "unknown",
    }
    assert validate_result("metric_query", payload) == []


def test_schema_introspection_does_not_require_metric_fields():
    payload = {
        "success": True,
        "columns": [],
        "semantic_context": {
            "query_role": "schema_introspection",
            "official_metric_calculation": False,
        },
    }
    assert validate_result("schema_introspection", payload) == []


def test_metric_definition_profile_is_sparse_but_explainable():
    payload = {
        "success": True,
        "cube": "WorkOrder",
        "semantic_context": {
            "metric_definitions": {"responseWithin2hRate": {"denominator": "responseEvaluable"}},
            "grain": "one row per fault work order",
            "applicability": "fault orders",
        },
    }
    assert validate_result("metric_definition", payload) == []


def test_metric_definition_query_does_not_call_cube_service():
    payload = asyncio.run(
        JiangsuQueryMetricsTool().execute(describe_cube="WorkOrder")
    )
    assert payload["success"] is True
    assert payload["semantic_context"]["metric_definitions"]["responseWithin2hRate"]["denominator"] == "responseEvaluable"


def test_quality_state_exposes_agent_decision_boundary():
    assert quality_guidance("ok")["decision"] == "可用于定量判断"
    assert quality_guidance("blocked")["decision"] == "不可形成业务结论"
    assert quality_guidance("unexpected")["decision"] == "质量未知"


def test_generated_semantic_index_keeps_registry_and_catalog_visible():
    path = resolve_agent_path("projects/jiangsu-ops/data-ops/semantic/catalog.generated.yaml")
    generated = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(generated["cubes"]) == len(CATALOG)
    assert generated["cubes"]["WorkOrder"]["measures"]["responseWithin2hRate"]["denominator"] == "responseEvaluable"
