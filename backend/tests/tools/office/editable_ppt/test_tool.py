from pathlib import Path

import pytest

from app.tools.office.editable_ppt.project_service import EditablePptProjectService
from app.tools.office.editable_ppt.tool import ManageEditablePptTool


class FakeCompiler:
    async def inspect(self, project_dir):
        return {"success": True, "slideCount": 1}

    async def preview(self, project_dir, output_dir=None, **kwargs):
        return {"success": True, "previewDir": str(Path(project_dir) / "build/preview"), "pages": []}

    async def compile(self, project_dir, output_dir=None, **kwargs):
        pptx = Path(project_dir) / "build/pptx/presentation.pptx"
        pptx.parent.mkdir(parents=True, exist_ok=True)
        pptx.write_bytes(b"fake-pptx")
        return {
            "success": True,
            "pptxPath": str(pptx),
            "report": {"editable": "strict", "forbiddenRasterFallbacks": 0, "issues": []},
        }


def make_tool(tmp_path):
    return ManageEditablePptTool(
        project_service=EditablePptProjectService(tmp_path), compiler_client=FakeCompiler()
    )


def test_schema_exposes_complete_direct_document_edit_contract(tmp_path):
    schema = make_tool(tmp_path).get_function_schema()
    branches = schema["parameters"]["oneOf"]
    operations = {branch["properties"]["operation"]["const"] for branch in branches}
    assert operations == {"create", "inspect", "read_source", "edit_source", "render", "compile", "validate", "restore", "finalize"}
    edit = next(branch for branch in branches if branch["properties"]["operation"]["const"] == "edit_source")
    assert set(edit["required"]) == {"operation", "project_dir", "relative_path", "content", "base_revision"}
    compile_branch = next(branch for branch in branches if branch["properties"]["operation"]["const"] == "compile")
    assert compile_branch["properties"]["editable"]["default"] == "strict"


@pytest.mark.asyncio
async def test_create_edit_render_compile_flow_has_stable_results(tmp_path):
    tool = make_tool(tmp_path)
    created = await tool.execute(operation="create", title="年度报告", theme="government")
    assert created["success"] is True
    project_dir = created["data"]["project_dir"]
    revision = created["data"]["revision"]
    source = await tool.execute(operation="read_source", project_dir=project_dir, relative_path="slides/slide-001.js")
    edited = await tool.execute(
        operation="edit_source", project_dir=project_dir, relative_path="slides/slide-001.js",
        content=source["data"]["content"].replace("年度报告", "年度总结"), base_revision=revision,
    )
    assert edited["data"]["revision"] == revision + 1
    rendered = await tool.execute(operation="render", project_dir=project_dir)
    compiled = await tool.execute(operation="compile", project_dir=project_dir)
    assert rendered["success"] and compiled["success"]
    assert compiled["data"]["dirty_slides"] == []


@pytest.mark.asyncio
async def test_unsupported_operation_returns_structured_failure(tmp_path):
    result = await make_tool(tmp_path).execute(operation="unknown")
    assert result["success"] is False
    assert result["data"]["issues"][0]["code"] == "UNSUPPORTED_OPERATION"


class FailingQa:
    async def execute(self, **kwargs):
        return {"success": True, "summary": "QA found issues", "data": {"success": False, "issues": [{"type": "blank_slide", "message": "blank"}], "gate": {"passed": False}}}


@pytest.mark.asyncio
async def test_finalize_rejects_qa_failure_and_stale_source(tmp_path):
    tool = make_tool(tmp_path)
    tool.validator = FailingQa()
    created = await tool.execute(operation="create", title="QA")
    project = created["data"]["project_dir"]
    await tool.execute(operation="compile", project_dir=project)
    qa = await tool.execute(operation="finalize", project_dir=project)
    assert qa["success"] is False
    state = tool.projects.inspect(project)
    source = tool.projects.read_source(project, "slides/slide-001.js")
    tool.projects.edit_source(project, "slides/slide-001.js", source.replace("QA", "changed"), state.revision)
    stale = await tool.execute(operation="finalize", project_dir=project)
    assert stale["data"]["issues"][0]["code"] == "STALE_COMPILE_ARTIFACT"
