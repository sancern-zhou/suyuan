from pathlib import Path

import pytest

from app.services.quarto_report_renderer import QuartoReportRenderer
from app.tools.report.report_package import tool as report_package_tool


@pytest.mark.asyncio
async def test_create_report_package_validates_in_same_call(tmp_path, monkeypatch):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="weekly_audit",
        qmd_content="# Weekly audit\n",
        output_formats=[],
    )

    assert result["success"] is True
    assert result["data"]["pipeline"]["render"]["requested_formats"] == []
    assert result["data"]["pipeline"]["validation"]["success"] is True


@pytest.mark.asyncio
async def test_create_report_package_renders_requested_formats_before_validation(
    tmp_path,
    monkeypatch,
):
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)
    calls = []

    async def fake_render(self, report_id, format="html", **kwargs):
        calls.append(("render", report_id, format))
        path = renderer.get_report_dir(report_id) / f"report.{format}"
        path.write_text("rendered", encoding="utf-8")
        return {
            "success": True,
            "data": {"report_id": report_id, "path": str(path)},
            "resources": [
                {
                    "resource_key": format,
                    "file_path": str(path),
                    "format": format,
                    "kind": "report",
                }
            ],
        }

    async def fake_validate(self, report_id, require_html=True, require_docx=False, **kwargs):
        calls.append(("validate", report_id, require_html, require_docx))
        return {"success": True, "data": {"valid": True}}

    monkeypatch.setattr(report_package_tool.RenderReportPackageTool, "execute", fake_render)
    monkeypatch.setattr(report_package_tool.ValidateReportPackageTool, "execute", fake_validate)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="formal_report",
        qmd_content="# Formal report\n",
        output_formats=["docx"],
    )

    assert result["success"] is True
    assert calls == [
        ("render", "formal_report", "docx"),
        ("validate", "formal_report", False, True),
    ]
    assert any(
        Path(resource.get("file_path", "")).suffix == ".docx"
        for resource in result["resources"]
    )
