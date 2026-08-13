from pathlib import Path

import pytest

from app.tools.utility.execute_python_tool import ExecutePythonTool


def test_schema_requires_registered_paths_for_cross_tool_data():
    schema = ExecutePythonTool().get_function_schema()
    description = schema["description"]
    code_description = schema["parameters"]["properties"]["code"]["description"]

    assert "artifact_path(filename)" in description
    assert "artifact_path(filename)" in code_description


def test_artifact_path_helper_rejects_absolute_paths():
    tool = ExecutePythonTool()
    code = tool._inject_artifact_path_helper("print(artifact_path('/tmp/report.xlsx'))")

    assert "def artifact_path" in code
    assert "raw.is_absolute()" in code


def test_document_literal_is_detected_as_unpublished_artifact_intent():
    tool = ExecutePythonTool()

    assert tool._code_intends_deliverable_file(
        "output = '/tmp/report.xlsx'\nwb.save(output)"
    ) is True
    assert tool._code_intends_deliverable_file(
        "data = pandas.read_excel('/tmp/input.xlsx')"
    ) is False
    assert tool._code_intends_deliverable_file("print('calculation complete')") is False


@pytest.mark.asyncio
async def test_artifact_path_file_is_collected_and_persisted(tmp_path):
    tool = ExecutePythonTool()
    tool.PERMANENT_DIR = str(tmp_path / "published")
    Path(tool.PERMANENT_DIR).mkdir()

    result = await tool.execute(
        code=(
            "output_path = artifact_path('daily-report.xlsx')\n"
            "with open(output_path, 'wb') as stream:\n"
            "    stream.write(b'xlsx')\n"
        )
    )

    assert result["success"] is True
    assert result["data"]["file_name"] == "daily-report.xlsx"
    assert Path(result["file_path"]).is_file()
    assert result["resources"]
