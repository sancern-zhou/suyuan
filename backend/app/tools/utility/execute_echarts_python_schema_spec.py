from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool


def test_execute_echarts_python_schema_owns_data_access_contract():
    schema = ExecuteEChartsPythonTool().get_function_schema()
    contract = " ".join(
        [
            schema["description"],
            schema["parameters"]["properties"]["code"]["description"],
        ]
    )

    assert "backend/app/tools/utility/execute_echarts_python_manual.md" in contract
    assert "read_file" in contract
    assert "load_data(file_path)" in contract
    assert "read_data_registry" not in contract
    assert "data_id" not in contract
    assert "stdout" in contract
    assert "series" in contract


def test_echarts_visuals_receive_the_preferred_browser_font_stack():
    from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool
    from app.utils.font_utils import BROWSER_CHART_FONT_FAMILY

    visuals = ExecuteEChartsPythonTool()._build_echarts_visuals(
        [{"textStyle": {"fontFamily": "Arial", "color": "#333"}, "series": [{"type": "bar", "data": [1]}]}],
        generator="execute_echarts_python",
    )

    assert visuals[0]["data"]["textStyle"] == {
        "fontFamily": BROWSER_CHART_FONT_FAMILY,
        "color": "#333",
    }
