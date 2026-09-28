from app.utils.echarts_legend import ensure_echarts_legend
from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool


def test_named_series_get_legend_and_bottom_space():
    option = {
        "xAxis": {"data": ["09-27", "09-28"]},
        "yAxis": {"type": "value"},
        "series": [{"name": "许昌市"}, {"name": "郑州市"}],
    }
    ensure_echarts_legend(option)
    assert option["legend"] == {
        "data": ["许昌市", "郑州市"],
        "orient": "horizontal",
        "bottom": 35,
    }
    assert option["grid"] == {"bottom": 84, "containLabel": True}


def test_explicit_or_unlabeled_legend_is_not_overridden():
    hidden = {"xAxis": {}, "yAxis": {}, "series": [{"name": "A"}, {"name": "B"}], "legend": {"show": False}}
    assert ensure_echarts_legend(hidden)["legend"] == {"show": False}
    unnamed = {"xAxis": {}, "yAxis": {}, "series": [{"data": [1]}, {"data": [2]}]}
    assert "legend" not in ensure_echarts_legend(unnamed)


def test_execute_echarts_visual_includes_synthesized_city_legend():
    option = {
        "xAxis": {"data": ["09-27", "09-28"]},
        "yAxis": {"type": "value"},
        "series": [
            {"type": "line", "name": "许昌市", "data": [20, 30]},
            {"type": "line", "name": "郑州市", "data": [25, 35]},
        ],
    }
    visual = ExecuteEChartsPythonTool()._build_echarts_visuals(
        [option], generator="execute_echarts_python"
    )[0]
    assert visual["data"]["legend"]["data"] == ["许昌市", "郑州市"]
    assert visual["data"]["grid"]["bottom"] >= 84
