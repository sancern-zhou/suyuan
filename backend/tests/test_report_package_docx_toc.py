import pytest

from app.tools.report.report_package.tool import CreateReportPackageTool


@pytest.mark.asyncio
async def test_create_report_package_disables_quarto_docx_toc_and_section_numbering(
    tmp_path, monkeypatch
):
    tool = CreateReportPackageTool()
    report_root = tmp_path / "reports"
    monkeypatch.setattr(
        "app.tools.report.report_package.tool.quarto_report_renderer.report_root",
        report_root,
    )

    qmd_content = """---
title: "测试报告"
format:
  docx:
    toc: true
    number-sections: true
---

# 一、正文

内容
"""

    result = await tool.execute(
        report_id="toc_test",
        qmd_content=qmd_content,
        render_html=False,
    )

    assert result["success"] is True
    written = (report_root / "toc_test" / "report.qmd").read_text(encoding="utf-8")
    assert "toc: true" not in written
    assert "number-sections: true" not in written
    assert "toc: false" in written
    assert "number-sections: false" in written
    assert result["refs"]["files"][0]["path"] == str(report_root / "toc_test" / "report.qmd")
    assert result["refs"]["artifacts"][0]["file_path"] == str(report_root / "toc_test" / "report.qmd")
    assert result["llm_resume"]["artifact_path"] == str(report_root / "toc_test" / "report.qmd")
    assert result["llm_resume"]["report_dir"] == str(report_root / "toc_test")
    assert "read_file" in result["llm_resume"]["tool_hint"]


@pytest.mark.asyncio
async def test_create_report_package_returns_source_and_html_resource_refs(
    tmp_path, monkeypatch
):
    tool = CreateReportPackageTool()
    report_root = tmp_path / "reports"
    source_qmd = tmp_path / "source.qmd"
    source_qmd.write_text("# 原始报告\n", encoding="utf-8")
    html_path = report_root / "resource_refs" / "report.html"
    monkeypatch.setattr(
        "app.tools.report.report_package.tool.quarto_report_renderer.report_root",
        report_root,
    )

    def fake_render_preview_html(report_id):
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text("<html>preview</html>", encoding="utf-8")
        return html_path

    monkeypatch.setattr(
        "app.tools.report.report_package.tool.quarto_report_renderer.render_preview_html",
        fake_render_preview_html,
    )

    result = await tool.execute(
        report_id="resource_refs",
        qmd_content="# 正式报告\n",
        source_qmd_path=str(source_qmd),
        render_html=True,
        render_docx=False,
    )

    file_paths = {item["path"] for item in result["refs"]["files"]}

    assert result["success"] is True
    assert str(report_root / "resource_refs" / "report.qmd") in file_paths
    assert str(source_qmd.resolve()) in file_paths
    assert str(html_path) in file_paths
    assert result["llm_resume"]["source_qmd_path"] == str(source_qmd.resolve())
    assert result["llm_resume"]["primary_artifact_path"] == str(html_path)
    assert "/api/" not in result["llm_resume"]["tool_hint"]


@pytest.mark.asyncio
async def test_create_report_package_renders_validates_and_presents_in_one_call(
    tmp_path, monkeypatch
):
    tool = CreateReportPackageTool()
    report_root = tmp_path / "reports"
    report_dir = report_root / "one_call"
    html_path = report_dir / "report.html"
    docx_path = report_dir / "report.docx"
    monkeypatch.setattr(
        "app.tools.report.report_package.tool.quarto_report_renderer.report_root",
        report_root,
    )

    def fake_render_preview_html(_report_id):
        html_path.write_text("<html><body>preview</body></html>", encoding="utf-8")
        return html_path

    def fake_render_docx(_report_id):
        docx_path.write_bytes(b"docx")
        return docx_path

    class FakeRenderedHtmlReport:
        def __init__(self, _path):
            pass

        def validate(self, _path):
            return {"valid": True}

    monkeypatch.setattr(
        "app.tools.report.report_package.tool.quarto_report_renderer.render_preview_html",
        fake_render_preview_html,
    )
    monkeypatch.setattr(
        "app.tools.report.report_package.tool.quarto_report_renderer.render_docx",
        fake_render_docx,
    )
    monkeypatch.setattr(
        "app.services.report.html_docx_bridge.RenderedHtmlReport",
        FakeRenderedHtmlReport,
    )

    result = await tool.execute(
        report_id="one_call",
        qmd_content="# 一次收口报告\n",
        output_formats=["html", "docx"],
    )

    assert result["success"] is True
    assert result["data"]["pipeline"]["render"]["success"] is True
    assert result["data"]["pipeline"]["render"]["requested_formats"] == ["html", "docx"]
    assert result["data"]["pipeline"]["validation"]["success"] is True
    assert {"qmd", "docx"} <= {item["resource_key"] for item in result["resources"]}
    assert result["presentation"] == {
        "action": "open",
        "resource_key": "html",
        "target_tab": "document",
    }
