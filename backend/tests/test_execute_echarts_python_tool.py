import json
from types import SimpleNamespace

import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.tools import create_global_tool_registry
from app.tools.utility.execute_python_tool import ExecuteEChartsPythonTool, ExecutePythonTool


def test_execute_python_discovers_session_path_used_by_open():
    tool = ExecutePythonTool()
    path = "/data/registry/sessions/agent_session_demo/data/result.json"

    assert tool._find_data_file_accesses(
        f'fp = "{path}"\nwith open(fp, "r", encoding="utf-8") as stream:\n    stream.read()'
    ) == [path]


@pytest.mark.asyncio
async def test_execute_python_can_open_authorized_session_path_in_bubblewrap(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    source = data_dir / "result.json"
    source.write_text('{"value": 42}', encoding="utf-8")
    context = SimpleNamespace(
        available_file_paths=[],
        data_manager=SimpleNamespace(
            memory=SimpleNamespace(
                session=SimpleNamespace(data_dir=data_dir),
            ),
        ),
    )

    result = await ExecutePythonTool().execute(
        context=context,
        code=(
            f'fp = "{source}"\n'
            'with open(fp, "r", encoding="utf-8") as stream:\n'
            '    print(stream.read())'
        ),
        timeout=10,
    )

    assert result["success"] is True
    assert '"value": 42' in result["data"]["output"]


@pytest.mark.asyncio
async def test_execute_echarts_python_converts_multiple_json_lines_to_visuals():
    tool = ExecuteEChartsPythonTool()
    code = f"""
import json

options = [
    {{
        "title": {{"text": "Chart A"}},
        "xAxis": {{"type": "category", "data": ["a", "b"]}},
        "yAxis": {{"type": "value"}},
        "series": [{{"type": "bar", "data": [1, 2]}}],
    }},
    {{
        "title": {{"text": "Chart B"}},
        "xAxis": {{"type": "category", "data": ["a", "b"]}},
        "yAxis": {{"type": "value"}},
        "series": [{{"type": "line", "data": [2, 3]}}],
    }},
]

for option in options:
    print(json.dumps(option, ensure_ascii=False))
"""

    result = await tool.execute(code=code, timeout=10)

    assert result["success"] is True
    assert [visual["title"] for visual in result["visuals"]] == ["Chart A", "Chart B"]
    assert [visual["type"] for visual in result["visuals"]] == ["bar", "line"]
    assert all(visual["meta"]["generator"] == "execute_echarts_python" for visual in result["visuals"])
    resources = [ResourceDeclaration.model_validate(item) for item in result["resources"]]
    assert [resource.resource_key for resource in resources] == ["chart-spec", "chart-spec"]
    assert all(resource.renderer.value == "chart" for resource in resources)


@pytest.mark.asyncio
async def test_execute_echarts_python_uses_catalog_spec_without_legacy_image_url():
    tool = ExecuteEChartsPythonTool()
    code = """
import json
option = {
    "title": {"text": "关系图"},
    "series": [{"type": "graph", "data": [{"name": "A"}], "links": []}],
}
print(json.dumps(option, ensure_ascii=False))
"""

    result = await tool.execute(code=code, timeout=10)

    assert result["success"] is True
    visual = result["visuals"][0]
    assert visual["type"] == "graph"
    assert visual["data"]["series"][0]["type"] == "graph"
    assert "image_url" not in visual
    assert "/api/image/" not in result["summary"]
    resource = ResourceDeclaration.model_validate(result["resources"][0])
    assert resource.resource_key == "chart-spec"
    assert resource.kind.value == "visual"
    assert resource.renderer.value == "chart"


@pytest.mark.asyncio
async def test_execute_echarts_python_fails_when_no_echarts_option_is_printed():
    tool = ExecuteEChartsPythonTool()

    result = await tool.execute(code='print("not a chart")', timeout=10)

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["visuals"] == []
    assert "未解析到有效的 ECharts option" in result["summary"]


def test_chart_mode_exposes_general_and_echarts_python_tools():
    chart_tools = get_tools_by_mode("chart")

    assert "execute_python" in chart_tools
    assert "execute_echarts_python" in chart_tools


def test_global_registry_registers_execute_echarts_python_with_dedicated_schema():
    registry = create_global_tool_registry()
    tool = registry.get_tool("execute_echarts_python")

    assert tool is not None
    schema = tool.get_function_schema()
    assert schema["name"] == "execute_echarts_python"
    assert "ECharts" in schema["description"]
    assert set(schema["parameters"]["required"]) == {"code"}


@pytest.mark.asyncio
async def test_execute_python_does_not_convert_echarts_stdout_to_visuals():
    tool = ExecutePythonTool()
    code = """
import json
option = {
    "title": {"text": "Should Not Render"},
    "xAxis": {"type": "category", "data": ["a", "b"]},
    "yAxis": {"type": "value"},
    "series": [{"type": "bar", "data": [1, 2]}],
}
print(json.dumps(option, ensure_ascii=False))
"""

    result = await tool.execute(code=code, timeout=10)

    assert result["success"] is True
    assert result.get("visuals", []) == []


def test_execute_python_schema_does_not_advertise_echarts_visuals():
    schema = ExecutePythonTool().get_function_schema()
    description = schema["description"]

    assert "ECharts" not in description
    assert "图片/ECharts返回visuals" not in description
