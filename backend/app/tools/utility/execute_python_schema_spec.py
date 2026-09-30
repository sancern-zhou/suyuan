import pytest

from app.agent.prompts.expert_prompt import build_expert_prompt
from app.agent.prompts.query_prompt import build_query_prompt
from app.agent.prompts.report_prompt import build_report_prompt
from app.tools.utility.execute_python_tool import ExecutePythonTool, ExecuteEChartsPythonTool
from app.tools.visualization.create_business_chart.tool import CreateBusinessChartTool


def test_execute_python_schema_describes_general_capability_and_bash_boundary():
    schema = ExecutePythonTool().get_function_schema()
    description = schema["description"]

    assert "通用 Python 代码执行工具" in description
    assert "复杂逻辑、结构化数据处理、数值计算、调用 Python 库、文件读写或文件生成" in description
    assert "无网络 Bubblewrap 沙箱" in description
    assert "查看文件、搜索文本、检查进程或调用现成 CLI" in description
    assert "优先使用 bash" in description
    assert "不限制于数据分析、Excel或可视化" in description
    assert "backend/app/tools/utility/execute_python_data_manual.md" in description
    assert "backend/app/tools/utility/execute_python_chart_manual.md" in description
    assert "backend/app/tools/utility/execute_python_report_manual.md" in description
    assert "read_file(path=...)" in description
    assert "混合任务" in description


def test_python_is_primary_report_plotting_tool_with_shared_style():
    schema = ExecutePythonTool().get_function_schema()
    assert "专家/报告模式的静态分析和正式报告图表优先使用 execute_python" in schema["description"]
    assert "问数模式绘图优先使用 execute_echarts_python" in schema["description"]
    assert "无需用户预先指定" in schema["description"]
    assert "默认一个独立图表一个图片文件" in schema["description"]
    assert "一次调用可保存多张图" in schema["description"]
    assert "仅联合阅读确有必要或用户明确要求时使用多子图" in schema["description"]
    code_description = schema["parameters"]["properties"]["code"]["description"]
    assert "5.8 英寸插入宽度" in code_description
    assert "最终刻度/图例一般不小于 9 pt" in code_description
    assert "dpi=240" in code_description
    assert "apply_report_style()" in schema["parameters"]["properties"]["code"]["description"]
    assert "正式报告静态图表优先使用 create_business_chart" not in schema["description"]


def test_environment_constraints_use_existing_tool_description():
    description = ExecutePythonTool().get_function_schema()["parameters"]["properties"]["code"]["description"]
    assert "图例默认在下方" in description
    assert "小时值不得直接按日均限值判断达标" in description
    for helper in ("aqi_color", "pollutant_color", "get_pollutant_scale",
                   "get_environment_limit", "add_standard_limit", "legend_below"):
        assert helper in description
    assert "风向箭头须明确来向/去向" in description


@pytest.mark.parametrize("tool_class", [ExecutePythonTool, ExecuteEChartsPythonTool, CreateBusinessChartTool])
def test_business_chart_requirement_precedes_mode_defaults_in_tool_descriptions(tool_class):
    tool = tool_class()
    for description in (tool.description, tool.get_function_schema()["description"]):
        normalized = description.replace("`", "")
        assert "必须使用 create_business_chart" in normalized
        assert "禁止用 Python/ECharts 重绘替代" in normalized
        assert "优先于模式默认工具" in normalized


@pytest.mark.parametrize("builder", [build_query_prompt, build_expert_prompt, build_report_prompt])
def test_business_chart_requirement_is_in_existing_mode_prompts(builder):
    prompt = builder(["execute_python", "execute_echarts_python", "create_business_chart"])
    assert "已支持的专用业务图型必须使用 `create_business_chart`" in prompt
    assert "禁止用 Python/ECharts 重绘替代" in prompt
    assert "优先于模式默认工具" in prompt
