from app.tools.query.guangdong_cube_metrics.semantic_registry import (
    cube_metadata,
    load_registry,
)
from app.tools.query.guangdong_cube_metrics.tool import CATALOG
from app.tools.query.guangdong_ops_sql_query.tool import ExecuteGuangdongMartSQLTool
from app.tools.query.guangdong_cube_metrics.result_contract import validate_result
from app.tools.query.guangdong_cube_metrics.tool import GuangdongQueryMetricsTool
from app.tools.query.guangdong_cube_metrics.quality_policy import quality_guidance
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
    metadata = cube_metadata("WorkOrder", CATALOG)
    assert metadata["measures"]["count"]["name"] == "工单量"


def test_sql_tool_whitelist_matches_generated_contract():
    """白名单来自 contract.txt 生成物（datasets/*.yaml 单一来源），含分析宽表。"""
    from app.tools.query.guangdong_ops_sql_query import tool as sql_tool_module
    assert "mart_work_order_analysis" in sql_tool_module.MART_TABLES
    assert "working_orders" in sql_tool_module.MART_TABLES
    assert "dim_station" in sql_tool_module.MART_TABLES


def test_contract_txt_matches_datasets_yaml():
    """契约防漂移：contract.txt 必须等于 gen_tool_contract.build_contract() 生成物。"""
    import sys
    from pathlib import Path
    data_ops_sync = (Path(__file__).resolve().parents[2]
                     / "projects/guangdong/data-ops/sync")
    sys.path.insert(0, str(data_ops_sync))
    try:
        import gen_tool_contract
    finally:
        sys.path.pop(0)
    generated = gen_tool_contract.build_contract()
    deployed = (resolve_agent_path(
        "backend/app/tools/query/guangdong_ops_sql_query/contract.txt"
    )).read_text(encoding="utf-8")
    assert deployed == generated


def test_sparse_result_contract_only_requires_context_for_metric_queries():
    payload = {
        "success": True,
        "data": [],
        "semantic_context": {
            "dataset": "mart_work_order_analysis",
            "grain": "one row per ops work order",
            "applicability": "all work order types",
            "data_as_of": None,
            "metric_definitions": {"count": {"name": "工单量"}},
        },
        "quality_status": "unknown",
    }
    assert validate_result("metric_query", payload) == []


def test_metric_query_missing_data_as_of_is_reported():
    payload = {
        "success": True,
        "data": [],
        "semantic_context": {
            "dataset": "mart_work_order_analysis",
            "grain": "one row per ops work order",
            "applicability": "all work order types",
            "metric_definitions": {},
        },
        "quality_status": "unknown",
    }
    errors = validate_result("metric_query", payload)
    assert any("data_as_of" in e for e in errors)


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


def test_metric_definition_query_does_not_call_cube_service():
    payload = asyncio.run(
        GuangdongQueryMetricsTool().execute(describe_cube="WorkOrder")
    )
    assert payload["success"] is True
    assert payload["semantic_context"]["metric_definitions"][
        "responseWithin2hRate"]["denominator"] == "responseEvaluable"
    assert payload["semantic_context"]["applicability"].startswith("全部")


def test_metrics_tool_rejects_cross_cube_and_unknown_members():
    tool = GuangdongQueryMetricsTool()
    assert tool._validate(["UnknownMetric"], [], None, [])[1] is not None
    assert tool._validate(["WorkOrder.count", "Other.count"], [], None, []) is not None


def test_quality_state_exposes_agent_decision_boundary():
    assert quality_guidance("ok")["decision"] == "可用于定量判断"
    assert quality_guidance("blocked")["decision"] == "不可形成业务结论"
    assert quality_guidance("unexpected")["decision"] == "质量未知"


def test_generated_semantic_index_keeps_registry_and_catalog_visible():
    path = resolve_agent_path("projects/guangdong/data-ops/semantic/catalog.generated.yaml")
    generated = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(generated["cubes"]) == len(CATALOG)
    assert generated["cubes"]["WorkOrder"]["measures"]["overdueRate"]["denominator"] == "overdueEvaluable"


def test_phase1_cubes_registered_with_rate_denominators():
    """一期扩展 cube（告警/设备/巡检/态势）必须登记且率类指标有分母。"""
    registry = load_registry()
    for cube in ("AlarmNotify", "StationAlarmStatus", "DeviceLifecycle", "InspectionTask"):
        assert cube in registry["cubes"], cube
        assert cube in CATALOG, cube
    inspection = registry["cubes"]["InspectionTask"]
    assert inspection["measures"]["finishedRate"]["denominator"] == "count"
    assert inspection["measures"]["overdueRate"]["denominator"] == "count"
    assert inspection["dataset"] == "mart_inspection_task_analysis"


def test_phase1_marts_in_sql_whitelist():
    from app.tools.query.guangdong_ops_sql_query import tool as sql_tool_module
    for t in ("mart_inspection_task_analysis", "mart_alarm_notify_analysis",
              "mart_device_lifecycle_analysis", "mart_station_alarm_status",
              "sup_rf_common", "alm_alarm"):
        assert t in sql_tool_module.MART_TABLES, t
