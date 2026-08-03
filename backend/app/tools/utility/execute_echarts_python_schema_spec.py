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
    assert "read_data_registry" in contract
    assert "get_raw_data(data_id)" in contract
    assert "open()" in contract
    assert "pathlib" in contract
    assert "物理文件路径" in contract
    assert "stdout" in contract
    assert "series" in contract
