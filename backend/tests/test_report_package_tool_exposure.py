from app.agent.prompts.tool_registry import get_tool_order, get_tools_by_mode
from app.tools import create_global_tool_registry
from app.tools.report.report_package.tool import CreateReportPackageTool


def test_render_report_package_is_registered_globally():
    registry = create_global_tool_registry()

    assert "render_report_package" in registry.list_tools()


def test_render_report_package_is_exposed_to_assistant_mode():
    assistant_tools = get_tools_by_mode("assistant")
    assistant_order = get_tool_order("assistant")

    assert "render_report_package" in assistant_tools
    assert "render_report_package" in assistant_order


def test_create_report_package_schema_points_to_real_reference_path():
    schema = CreateReportPackageTool().get_function_schema()
    description = schema["description"]

    assert "app/tools/report/report_package/references/index.md" in description
    assert "backend/app/tools/report/report_package/references/index.md" not in description
