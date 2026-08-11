from app.tools.utility.execute_python_tool import ExecutePythonTool


def test_schema_requires_registered_paths_for_cross_tool_data():
    schema = ExecutePythonTool().get_function_schema()
    description = schema["description"]
    code_description = schema["parameters"]["properties"]["code"]["description"]

    assert "跨调用或交给其他工具" in description
    assert "原样复用 save_data 返回的 file_path" in description
    assert "执行环境相互隔离" in description
    assert "自行写入、拼接或猜测" in description
    assert "必须使用 path = save_data" in code_description
    assert "不能传递其他文件写入方式产生的中间路径" in code_description
