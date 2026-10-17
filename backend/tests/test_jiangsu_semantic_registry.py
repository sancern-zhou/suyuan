from app.tools.query.jiangsu_cube_metrics.semantic_registry import (
    cube_metadata,
    load_registry,
)
from app.tools.query.jiangsu_cube_metrics.tool import CATALOG


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
