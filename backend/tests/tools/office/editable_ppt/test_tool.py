from pathlib import Path

import pytest

from app.tools.office.editable_ppt.compiler_client import CompilerClientError
from app.tools.office.editable_ppt.project_service import EditablePptProjectService
from app.tools.office.editable_ppt.tool import ManageEditablePptTool


class FakeCompiler:
    def __init__(self):
        self.preview_calls = []

    async def inspect(self, project_dir):
        return {"success": True, "slideCount": 1}

    async def preview(self, project_dir, output_dir=None, **kwargs):
        self.preview_calls.append(kwargs)
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
    assert operations == {"create", "inspect", "read_source", "edit_source", "edit_sources", "render", "compile", "validate", "restore", "finalize"}
    edit = next(branch for branch in branches if branch["properties"]["operation"]["const"] == "edit_source")
    assert set(edit["required"]) == {"operation", "project_dir", "relative_path", "content", "base_revision"}
    edit_many = next(branch for branch in branches if branch["properties"]["operation"]["const"] == "edit_sources")
    assert set(edit_many["required"]) == {"operation", "project_dir", "edits", "base_revision"}
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
async def test_render_accepts_json_encoded_page_array_from_llm(tmp_path):
    compiler = FakeCompiler()
    tool = ManageEditablePptTool(
        project_service=EditablePptProjectService(tmp_path), compiler_client=compiler
    )
    created = await tool.execute(operation="create", title="分页预览")

    result = await tool.execute(
        operation="render",
        project_dir=created["data"]["project_dir"],
        pages="[1]",
    )

    assert result["success"] is True
    assert compiler.preview_calls[-1]["pages"] == [1]


@pytest.mark.asyncio
async def test_edit_source_accepts_numeric_string_revision_from_llm(tmp_path):
    tool = make_tool(tmp_path)
    created = await tool.execute(operation="create", title="字符串版本号")
    project_dir = created["data"]["project_dir"]
    source = await tool.execute(
        operation="read_source", project_dir=project_dir, relative_path="slides/slide-001.js"
    )

    result = await tool.execute(
        operation="edit_source",
        project_dir=project_dir,
        relative_path="slides/slide-001.js",
        content=source["data"]["content"].replace("字符串版本号", "已更新"),
        base_revision=str(created["data"]["revision"]),
    )

    assert result["success"] is True
    assert result["data"]["revision"] == created["data"]["revision"] + 1


@pytest.mark.asyncio
async def test_edit_sources_applies_multiple_documents_in_one_revision(tmp_path):
    tool = make_tool(tmp_path)
    created = await tool.execute(operation="create", title="批量修改")
    project_dir = created["data"]["project_dir"]
    slide = await tool.execute(
        operation="read_source", project_dir=project_dir, relative_path="slides/slide-001.js"
    )
    theme = await tool.execute(
        operation="read_source", project_dir=project_dir, relative_path="theme.json"
    )

    result = await tool.execute(
        operation="edit_sources",
        project_dir=project_dir,
        edits=[
            {
                "relative_path": "slides/slide-001.js",
                "content": slide["data"]["content"].replace("批量修改", "原子批量修改"),
            },
            {
                "relative_path": "theme.json",
                "content": theme["data"]["content"].replace("#E8A317", "#FFAA00"),
            },
        ],
        base_revision=str(created["data"]["revision"]),
    )

    assert result["success"] is True
    assert result["data"]["revision"] == created["data"]["revision"] + 1
    assert result["data"]["dirty_slides"] == ["cover"]
    assert "原子批量修改" in Path(project_dir, "slides/slide-001.js").read_text(encoding="utf-8")
    assert "#FFAA00" in Path(project_dir, "theme.json").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_unsupported_operation_returns_structured_failure(tmp_path):
    result = await make_tool(tmp_path).execute(operation="unknown")
    assert result["success"] is False
    assert result["data"]["issues"][0]["code"] == "UNSUPPORTED_OPERATION"


class CompilerWithActionableFailure(FakeCompiler):
    async def inspect(self, project_dir):
        raise CompilerClientError(
            "COMPILER_PROCESS_FAILED",
            "exit code 1",
            stderr=(
                "slide-004.js native element roi-chart: expected kind='chart'; "
                "HTML must contain data-pptx-ref='roi-chart'"
            ),
        )


@pytest.mark.asyncio
async def test_compiler_stderr_is_returned_as_actionable_evidence(tmp_path):
    tool = ManageEditablePptTool(
        project_service=EditablePptProjectService(tmp_path),
        compiler_client=CompilerWithActionableFailure(),
    )
    created = await tool.execute(operation="create", title="错误反馈")

    result = await tool.execute(operation="inspect", project_dir=created["data"]["project_dir"])

    assert result["success"] is False
    issue = result["data"]["issues"][0]
    assert "expected kind='chart'" in issue["evidence"]["stderr"]
    assert "data-pptx-ref='roi-chart'" in result["data"]["next_actions"][0]


class FailingQa:
    async def execute(self, **kwargs):
        return {"success": True, "summary": "QA found issues", "data": {"success": False, "issues": [{"type": "blank_slide", "message": "blank"}], "gate": {"passed": False}}}


class PassingQa:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "summary": "QA passed", "data": {"success": True, "issues": [], "gate": {"passed": True}}}


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


@pytest.mark.asyncio
async def test_finalize_records_current_revision_as_the_only_presentable_artifact(tmp_path):
    tool = make_tool(tmp_path)
    tool.validator = PassingQa()
    created = await tool.execute(operation="create", title="可交付版本")
    project = Path(created["data"]["project_dir"])
    compiled = await tool.execute(operation="compile", project_dir=str(project))

    finalized = await tool.execute(operation="finalize", project_dir=str(project))

    assert finalized["success"] is True
    manifest = __import__("json").loads((project / ".editable-ppt" / "finalized.json").read_text(encoding="utf-8"))
    assert manifest["sourceRevision"] == compiled["data"]["sourceRevision"]
    assert manifest["sourceHashes"] == compiled["data"]["sourceHashes"]
    assert manifest["pptxSha256"] == compiled["data"]["pptxSha256"]
    assert manifest["pptxPath"] == compiled["data"]["pptxPath"]
    assert tool.validator.calls[-1]["expected_fonts"] == ["Noto Sans CJK SC"]
