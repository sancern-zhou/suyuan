import base64
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.quarto_report_renderer as renderer_module
import app.services.report_preview_refresh as preview_refresh
import app.tools.report.report_package.tool as report_package_tool
from app.services.quarto_report_renderer import (
    QuartoReportRenderer,
    ReportRenderError,
    inspect_report_image_refs,
)


def _write_report(report_root: Path, report_id: str, qmd: str) -> Path:
    report_dir = report_root / report_id
    report_dir.mkdir(parents=True)
    (report_dir / "report.qmd").write_text(qmd, encoding="utf-8")
    return report_dir


def test_prepare_docx_qmd_normalizes_tight_chinese_ascii_quotes_without_overwriting_source(
    tmp_path,
):
    report_root = tmp_path / "reports"
    source = (
        "观察一：榆林\"量大价低\"，西安\"量少价高\"\n"
        "观察二：榆林“维持运转”，西安“升级能力”\n"
    )
    report_dir = _write_report(report_root, "air_report", source)
    qmd_path = report_dir / "report.qmd"
    renderer = QuartoReportRenderer(report_root=report_root)

    prepared = renderer._prepare_docx_qmd(report_dir, qmd_path)

    assert prepared != qmd_path
    assert prepared.read_text(encoding="utf-8") == (
        "观察一：榆林“量大价低”，西安“量少价高”\n"
        "观察二：榆林“维持运转”，西安“升级能力”\n"
    )
    assert qmd_path.read_text(encoding="utf-8") == source


def test_prepare_docx_qmd_normalizes_chinese_ascii_quotes_in_markdown_table(
    tmp_path,
):
    report_root = tmp_path / "reports"
    source = (
        "| 目标 | 说明 |\n"
        "|------|------|\n"
        '| 污染过程"说得清" | 覆盖全部污染类型 |\n'
        '| 达标形势"算得明" | 测算年度目标进度 |\n'
    )
    report_dir = _write_report(report_root, "air_report", source)
    qmd_path = report_dir / "report.qmd"
    renderer = QuartoReportRenderer(report_root=report_root)

    prepared = renderer._prepare_docx_qmd(report_dir, qmd_path)

    assert prepared.read_text(encoding="utf-8") == (
        "| 目标 | 说明 |\n"
        "|------|------|\n"
        "| 污染过程“说得清” | 覆盖全部污染类型 |\n"
        "| 达标形势“算得明” | 测算年度目标进度 |\n"
    )


def test_prepare_docx_qmd_normalizes_only_markdown_prose(tmp_path):
    report_root = tmp_path / "reports"
    source = '''---
title: 榆林"量大价低"
---

`榆林"量大价低"`

```text
榆林"量大价低"
```

````text
围栏内榆林"量大价低"
`````still code
仍在围栏内西安"量少价高"
````

`跨行代码开始
榆林"量大价低"
跨行代码结束`

未闭合：榆林"量大价低
下一行西安"量少价高"

**结论：榆林"量大价低"**
'''
    report_dir = _write_report(report_root, "air_report", source)
    qmd_path = report_dir / "report.qmd"
    renderer = QuartoReportRenderer(report_root=report_root)

    prepared = renderer._prepare_docx_qmd(report_dir, qmd_path)
    prepared_text = prepared.read_text(encoding="utf-8")

    assert 'title: 榆林"量大价低"' in prepared_text
    assert '`榆林"量大价低"`' in prepared_text
    assert '```text\n榆林"量大价低"\n```' in prepared_text
    assert '`````still code\n仍在围栏内西安"量少价高"\n````' in prepared_text
    assert '`跨行代码开始\n榆林"量大价低"\n跨行代码结束`' in prepared_text
    assert '未闭合：榆林"量大价低\n下一行西安“量少价高”' in prepared_text
    assert '**结论：榆林“量大价低”**' in prepared_text


def test_render_docx_removes_temporary_qmd_when_reference_doc_setup_fails(
    tmp_path, monkeypatch
):
    report_root = tmp_path / "reports"
    report_dir = _write_report(
        report_root,
        "air_report",
        '观察一：榆林"量大价低"\n',
    )
    renderer = QuartoReportRenderer(report_root=report_root)

    def fail_reference_doc_setup():
        raise RuntimeError("reference doc setup failed")

    monkeypatch.setattr(
        renderer_module,
        "ensure_government_reference_docx",
        fail_reference_doc_setup,
    )

    with pytest.raises(RuntimeError, match="reference doc setup failed"):
        renderer.render_docx("air_report")

    assert list(report_dir.glob("report_docx_render*.qmd")) == []


def test_preview_renders_normalized_package_qmd_without_source_overwrite(tmp_path):
    report_root = tmp_path / "reports"
    report_dir = _write_report(
        report_root,
        "air_report",
        "# Package\n\n![](assets/charts/visibility.png)\n",
    )
    charts_dir = report_dir / "assets" / "charts"
    charts_dir.mkdir(parents=True)
    (charts_dir / "visibility.png").write_bytes(b"png")

    source_qmd = tmp_path / "evidence" / "report.qmd"
    source_qmd.parent.mkdir()
    source_qmd.write_text("# Source\n\n![](visibility.png)\n", encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps({"files": {"source_qmd": str(source_qmd)}}),
        encoding="utf-8",
    )

    renderer = QuartoReportRenderer(report_root=report_root)
    rendered_qmd = []

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        rendered_qmd.append((cwd / "report.qmd").read_text(encoding="utf-8"))

    renderer._run_quarto = fake_run_quarto

    renderer.render_preview_html("air_report")

    assert renderer.get_qmd_path("air_report") == (report_dir / "report.qmd").resolve()
    assert rendered_qmd == ["# Package\n\n![](assets/charts/visibility.png)\n"]
    assert (report_dir / "report.qmd").read_text(encoding="utf-8") == rendered_qmd[0]


def test_preview_rejects_missing_local_image_before_quarto(tmp_path):
    report_root = tmp_path / "reports"
    report_dir = _write_report(
        report_root,
        "air_report",
        "# Package\n\n![](assets/visibility.png)\n",
    )
    renderer = QuartoReportRenderer(report_root=report_root)
    quarto_called = False

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        nonlocal quarto_called
        quarto_called = True

    renderer._run_quarto = fake_run_quarto

    with pytest.raises(ReportRenderError) as exc_info:
        renderer.render_preview_html("air_report")

    message = str(exc_info.value)
    assert "assets/visibility.png" in message
    assert str(report_dir / "assets" / "visibility.png") in message
    assert "create_report_package.assets" in message
    assert "assets/charts/visibility.png" in message
    assert quarto_called is False


def test_image_validation_accepts_markdown_path_with_optional_title(tmp_path):
    report_dir = tmp_path / "reports" / "air_report"
    charts_dir = report_dir / "assets" / "charts"
    charts_dir.mkdir(parents=True)
    (charts_dir / "visibility.png").write_bytes(b"png")

    validation = inspect_report_image_refs(
        report_dir,
        '![](assets/charts/visibility.png "Visibility at alert time")\n',
    )

    assert validation["issues"] == []


def test_quarto_missing_resource_warning_is_render_failure(tmp_path, monkeypatch):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")

    monkeypatch.setattr(
        renderer_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="Output created: report.docx\n",
            stderr=(
                "[WARNING] Could not fetch resource assets/charts/visibility.png: "
                "replacing image with description\n"
            ),
        ),
    )

    with pytest.raises(ReportRenderError) as exc_info:
        renderer._run_quarto(tmp_path, ["render", "report.qmd"])

    message = str(exc_info.value)
    assert "Could not fetch resource assets/charts/visibility.png" in message
    assert "unresolved" in message.lower()


@pytest.mark.asyncio
async def test_validate_report_package_returns_actionable_image_issues(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    report_dir = _write_report(
        report_root,
        "air_report",
        "# Package\n\n![](assets/visibility.png)\n",
    )
    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    result = await report_package_tool.ValidateReportPackageTool().execute(
        report_id="air_report",
        require_html=False,
    )

    assert result["success"] is False
    issue = result["data"]["image_refs"]["issues"][0]
    assert issue["reference"] == "assets/visibility.png"
    assert issue["resolved_path"] == str(report_dir / "assets" / "visibility.png")
    assert issue["reason"] == "file does not exist"
    assert "create_report_package.assets" in result["data"]["error"]
    assert "assets/charts/visibility.png" in result["data"]["error"]


@pytest.mark.asyncio
async def test_create_report_package_fails_for_unresolved_image_refs(tmp_path, monkeypatch):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content="# Package\n\n![](assets/visibility.png)\n",
        render_html=False,
    )

    assert result["success"] is False
    assert result["data"]["validation"]["issues"][0]["reference"] == "assets/visibility.png"
    assert "create_report_package.assets" in result["data"]["error"]


@pytest.mark.asyncio
async def test_create_report_package_rewrites_api_image_ref_from_copied_asset(
    tmp_path,
    monkeypatch,
):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)
    image_path = tmp_path / "images" / "daily_chart.png"
    image_path.parent.mkdir()
    image_path.write_bytes(b"png")

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="tender_report",
        qmd_content="# Report\n\n![](/api/image/daily_chart.png)\n",
        assets=[str(image_path)],
        render_html=False,
    )

    assert result["success"] is True
    package_qmd = tmp_path / "reports" / "tender_report" / "report.qmd"
    assert "![](assets/charts/daily_chart.png)" in package_qmd.read_text(encoding="utf-8")
    assert result["data"]["validation"]["api_image_refs"] == []


@pytest.mark.asyncio
async def test_create_report_package_fails_for_residual_api_image_ref(tmp_path, monkeypatch):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="tender_report",
        qmd_content="# Report\n\n![](/api/image/missing_chart.png)\n",
        render_html=False,
    )

    assert result["success"] is False
    validation = result["data"]["validation"]
    assert validation["api_image_refs"] == ["/api/image/missing_chart.png"]
    assert validation["issues"][0]["reference"] == "/api/image/missing_chart.png"
    assert validation["issues"][0]["reason"] == "API image reference was not normalized"
    assert "assets/charts/missing_chart.png" in result["data"]["error"]


@pytest.mark.asyncio
async def test_create_report_package_returns_failure_for_quarto_resource_error(
    tmp_path,
    monkeypatch,
):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    def fail_render(cwd: Path, args: list[str]) -> None:
        raise ReportRenderError(
            "Quarto rendered with unresolved image resources: Could not fetch resource chart.png"
        )

    renderer._run_quarto = fail_render

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content="# Package without local refs\n",
        render_html=True,
    )

    assert result["success"] is False
    assert "Could not fetch resource chart.png" in result["data"]["error"]
    assert result["data"]["render_error"] == result["data"]["error"]


def test_yuncheng_skill_defines_source_and_package_image_path_contract():
    skill_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "skills"
        / "yuncheng_alert_tracing_skill.md"
    )
    skill = skill_path.read_text(encoding="utf-8")

    assert "![后向轨迹](trajectory.png)" in skill
    assert "assets/charts/trajectory.png" in skill
    assert "report_qmd_path.parent" in skill
    assert "Path(image_path).resolve().relative_to" in skill
    assert "copied_assets[].relative_path" in skill
    assert "禁止在源 `report.qmd`" not in skill
    assert "create_report_package.assets" in skill

    source_qmd_description = report_package_tool.CreateReportPackageTool().function_schema[
        "parameters"
    ]["properties"]["source_qmd_path"]["description"]
    assert "不会直接覆盖" in source_qmd_description
    assert "报告包内 report.qmd" in source_qmd_description


def test_record_report_update_preserves_external_source_metadata(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    report_dir = _write_report(report_root, "air_report", "# Package\n")
    source_qmd = tmp_path / "evidence" / "report.qmd"
    source_qmd.parent.mkdir()
    source_qmd.write_text("# Source\n", encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps({"files": {"source_qmd": str(source_qmd)}, "version": 1}),
        encoding="utf-8",
    )
    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(preview_refresh, "quarto_report_renderer", renderer)

    meta = preview_refresh.record_report_update("air_report", source="test")

    assert meta["files"]["source_qmd"] == str(source_qmd)


def test_editing_external_source_requires_repack_instead_of_rendering_stale_package(
    tmp_path,
    monkeypatch,
):
    report_root = tmp_path / "reports"
    report_dir = _write_report(report_root, "air_report", "# Package\n")
    source_qmd = tmp_path / "evidence" / "report.qmd"
    source_qmd.parent.mkdir()
    source_qmd.write_text("# Updated source\n", encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps({"files": {"source_qmd": str(source_qmd)}, "version": 1}),
        encoding="utf-8",
    )
    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(preview_refresh, "quarto_report_renderer", renderer)
    quarto_called = False

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        nonlocal quarto_called
        quarto_called = True

    renderer._run_quarto = fake_run_quarto

    result = preview_refresh.refresh_report_preview_for_qmd_path(source_qmd)

    assert result["report_preview_refresh"]["success"] is False
    assert "create_report_package" in result["render_error"]
    assert "rebuild" in result["render_error"].lower()
    assert quarto_called is False


def test_standalone_source_preview_initializes_a_transient_package(tmp_path, monkeypatch):
    source_qmd = tmp_path / "draft" / "report.qmd"
    source_qmd.parent.mkdir()
    source_qmd.write_text("# Draft report\n\n![](chart.png)\n", encoding="utf-8")
    (source_qmd.parent / "chart.png").write_bytes(b"png")
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(preview_refresh, "quarto_report_renderer", renderer)

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        (cwd / "report.html").write_text("<h1>Draft report</h1>", encoding="utf-8")

    renderer._run_quarto = fake_run_quarto

    result = preview_refresh.create_report_preview_for_source_qmd_path(source_qmd)

    assert result["report_preview_refresh"]["success"] is True
    report_dir = renderer.get_report_dir(result["report_id"])
    assert (report_dir / "report.qmd").read_text(encoding="utf-8") == (
        "# Draft report\n\n![](chart.png)\n"
    )
    assert (report_dir / "chart.png").read_bytes() == b"png"


@pytest.mark.asyncio
async def test_real_quarto_renders_normalized_image_into_html_and_docx(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    source_qmd = evidence_dir / "report.qmd"
    source_qmd.write_text("# Image report\n\n![Chart](chart.png)\n", encoding="utf-8")
    image_path = evidence_dir / "chart.png"
    image_path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
    )

    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)
    monkeypatch.setattr(preview_refresh, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content=source_qmd.read_text(encoding="utf-8"),
        source_qmd_path=str(source_qmd),
        assets=[str(image_path)],
        render_html=True,
    )

    assert result["success"] is True
    report_dir = report_root / "air_report"
    package_qmd = report_dir / "report.qmd"
    assert "![](assets/charts/chart.png)" not in package_qmd.read_text(encoding="utf-8")
    assert "![Chart](assets/charts/chart.png)" in package_qmd.read_text(encoding="utf-8")
    assert (report_dir / "report.html").is_file()
    renderer.render_preview_html("air_report")
    assert "assets/charts/chart.png" in package_qmd.read_text(encoding="utf-8")

    docx_path = renderer.render_docx("air_report")
    with zipfile.ZipFile(docx_path) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())

    validation = await report_package_tool.ValidateReportPackageTool().execute(
        report_id="air_report",
        require_html=True,
        require_docx=True,
    )
    assert validation["success"] is True
