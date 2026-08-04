from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool


def test_execute_echarts_python_schema_owns_data_access_contract():
    schema = ExecuteEChartsPythonTool().get_function_schema()
    contract = " ".join(
        [
            schema["description"],
            schema["parameters"]["properties"]["code"]["description"],
        ]
    )

    assert "app/tools/utility/execute_echarts_python_manual.md" in contract
    assert "backend/app/tools/utility/execute_echarts_python_manual.md" not in contract
    assert "read_file" in contract
    assert "load_data(file_path)" in contract
    assert "read_data_registry" not in contract
    assert "data_id" not in contract
    assert "stdout" in contract
    assert "series" in contract
