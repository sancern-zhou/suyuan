from app.tools.utility.execute_python_tool import ExecutePythonTool


def test_execute_python_schema_describes_general_capability_and_bash_boundary():
    schema = ExecutePythonTool().get_function_schema()
    description = schema["description"]

    assert "通用 Python 代码执行工具" in description
    assert "复杂逻辑、结构化数据处理、数值计算、调用 Python 库、文件读写或文件生成" in description
    assert "无网络 Bubblewrap 沙箱" in description
    assert "查看文件、搜索文本、检查进程或调用现成 CLI" in description
    assert "优先使用 bash" in description
    assert "不限制于数据分析、Excel或可视化" in description
