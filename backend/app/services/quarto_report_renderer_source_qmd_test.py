import json
from pathlib import Path

import pytest

import app.api.report_routes as report_routes
import app.services.report_preview_refresh as report_preview_refresh
import app.tools.report.report_package.tool as report_package_tool
import app.tools.utility.publish_session_file_tool as publish_session_file_tool
from app.services.quarto_report_renderer import QuartoReportRenderer


def test_render_preview_html_snapshots_source_qmd_before_rendering_report_qmd(tmp_path):
    report_root = tmp_path / "reports"
    report_dir = report_root / "air_report"
    source_dir = tmp_path / "source"
    source_qmd = source_dir / "original.qmd"
    source_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    source_qmd.write_text("# Original report\n", encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps({"files": {"source_qmd": str(source_qmd)}}),
        encoding="utf-8",
    )

    renderer = QuartoReportRenderer(report_root=report_root)
    calls = []

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        calls.append((cwd, args))

    renderer._run_quarto = fake_run_quarto

    html_path = renderer.render_preview_html("air_report")

    assert html_path == report_dir.resolve() / "report.html"
    assert (report_dir / "report.qmd").read_text(encoding="utf-8") == "# Original report\n"
    assert calls == [
        (
            report_dir.resolve(),
            [
                "render",
                "report.qmd",
                "--to",
                "html",
                "--output",
                "report.html",
            ],
        )
    ]


def test_get_qmd_path_falls_back_to_report_package_qmd(tmp_path):
    report_root = tmp_path / "reports"
    report_dir = report_root / "air_report"
    report_dir.mkdir(parents=True)
    package_qmd = report_dir / "report.qmd"
    package_qmd.write_text("# Package report\n", encoding="utf-8")

    renderer = QuartoReportRenderer(report_root=report_root)

    assert renderer.get_qmd_path("air_report") == package_qmd.resolve()


def test_refresh_report_preview_maps_source_qmd_to_report_id(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    report_dir = report_root / "air_report"
    source_dir = tmp_path / "source"
    source_qmd = source_dir / "original.qmd"
    source_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    source_qmd.write_text("# Updated original report\n", encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps({"files": {"source_qmd": str(source_qmd)}, "version": 1}),
        encoding="utf-8",
    )

    renderer = QuartoReportRenderer(report_root=report_root)

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        (report_dir / "report.html").write_text("<h1>Updated</h1>", encoding="utf-8")

    renderer._run_quarto = fake_run_quarto
    monkeypatch.setattr(report_preview_refresh, "quarto_report_renderer", renderer)

    result = report_preview_refresh.refresh_report_preview_for_qmd_path(source_qmd)

    assert result["report_id"] == "air_report"
    assert result["file_path"] == str(source_qmd.resolve())
    assert result["html_preview"]["html_url"] == "/api/reports/air_report/html"
    assert result["report_preview_refresh"]["success"] is True
    meta = json.loads((report_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["files"]["source_qmd"] == str(source_qmd.resolve())
    assert meta["files"]["qmd"] == str(report_dir / "report.qmd")


def test_refresh_report_preview_ignores_source_qmd_when_it_is_report_qmd(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    report_dir = report_root / "air_report"
    charts_dir = report_dir / "assets" / "charts"
    charts_dir.mkdir(parents=True)
    package_qmd = report_dir / "report.qmd"
    package_qmd.write_text("# Package report\n\n![](assets/charts/a.png)\n", encoding="utf-8")
    (charts_dir / "a.png").write_bytes(b"png")
    (report_dir / "meta.json").write_text(
        json.dumps(
            {
                "files": {
                    "qmd": str(package_qmd),
                    "source_qmd": str(package_qmd),
                },
                "version": 1,
            }
        ),
        encoding="utf-8",
    )

    renderer = QuartoReportRenderer(report_root=report_root)

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        (report_dir / "report.html").write_text("<h1>Package</h1>", encoding="utf-8")

    renderer._run_quarto = fake_run_quarto
    monkeypatch.setattr(report_preview_refresh, "quarto_report_renderer", renderer)

    result = report_preview_refresh.refresh_report_preview_for_qmd_path(package_qmd)

    assert result["report_preview_refresh"]["success"] is True
    meta = json.loads((report_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["files"]["qmd"] == str(package_qmd)
    assert "source_qmd" not in meta["files"]


@pytest.mark.asyncio
async def test_create_report_package_records_source_qmd_path(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    source_dir = tmp_path / "source"
    source_qmd = source_dir / "original.qmd"
    source_dir.mkdir(parents=True)
    source_qmd.write_text("# Source report\n", encoding="utf-8")

    renderer = QuartoReportRenderer(report_root=report_root)
    calls = []

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        calls.append((cwd, args))
        (report_root / "air_report" / "report.html").write_text(
            "<h1>Source report</h1>",
            encoding="utf-8",
        )

    renderer._run_quarto = fake_run_quarto
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)
    monkeypatch.setattr(report_preview_refresh, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content="# Snapshot report\n",
        source_qmd_path=str(source_qmd),
        render_html=True,
    )

    assert result["success"] is True
    assert result["data"]["file_path"] == str(source_qmd.resolve())
    assert (report_root / "air_report" / "report.qmd").read_text(encoding="utf-8") == "# Source report\n"
    assert calls[0][0] == (report_root / "air_report").resolve()
    assert calls[0][1][1] == "report.qmd"
    meta = json.loads((report_root / "air_report" / "meta.json").read_text(encoding="utf-8"))
    assert meta["files"]["source_qmd"] == str(source_qmd.resolve())
    assert meta["files"]["qmd"] == str(report_root / "air_report" / "report.qmd")


@pytest.mark.asyncio
async def test_create_report_package_omits_source_qmd_when_it_is_report_qmd(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    report_dir = report_root / "air_report"
    report_dir.mkdir(parents=True)
    package_qmd = report_dir / "report.qmd"
    package_qmd.write_text("# Existing package report\n", encoding="utf-8")

    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)
    monkeypatch.setattr(report_preview_refresh, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content="# Updated package report\n",
        source_qmd_path=str(package_qmd),
        render_html=False,
    )

    assert result["success"] is True
    meta = json.loads((report_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["files"]["qmd"] == str(package_qmd)
    assert "source_qmd" not in meta["files"]


@pytest.mark.asyncio
async def test_create_report_package_rejects_r_chunks_before_writing_qmd(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content='''---
title: "Report"
---

```{r chart, echo=FALSE}
knitr::include_graphics("assets/charts/chart.png")
```
''',
        render_html=False,
    )

    assert result["success"] is False
    assert "unsupported R/knitr content" in result["data"]["error"]
    assert "R code chunk" in result["data"]["unsupported_r_features"]
    assert "knitr::" in result["data"]["unsupported_r_features"]
    assert not (report_root / "air_report" / "report.qmd").exists()


@pytest.mark.asyncio
async def test_create_report_package_rejects_r_in_source_qmd_path(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    source_dir = tmp_path / "source"
    source_qmd = source_dir / "original.qmd"
    source_dir.mkdir(parents=True)
    source_qmd.write_text("Report date: `r Sys.Date()`\n", encoding="utf-8")

    renderer = QuartoReportRenderer(report_root=report_root)
    monkeypatch.setattr(report_package_tool, "quarto_report_renderer", renderer)

    result = await report_package_tool.CreateReportPackageTool().execute(
        report_id="air_report",
        qmd_content="# Snapshot report\n",
        source_qmd_path=str(source_qmd),
        render_html=False,
    )

    assert result["success"] is False
    assert "unsupported R/knitr content" in result["data"]["error"]
    assert result["data"]["unsupported_r_features"] == ["inline R expression"]
    assert not (report_root / "air_report" / "report.qmd").exists()


@pytest.mark.asyncio
async def test_get_report_html_refreshes_when_source_qmd_is_newer(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    report_dir = report_root / "air_report"
    source_dir = tmp_path / "source"
    source_qmd = source_dir / "original.qmd"
    source_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    html_path = report_dir / "report.html"
    source_qmd.write_text("# Updated source report\n", encoding="utf-8")
    html_path.write_text("<h1>Old</h1>", encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps({"files": {"source_qmd": str(source_qmd)}}),
        encoding="utf-8",
    )
    old_mtime_ns = source_qmd.stat().st_mtime_ns - 1_000_000_000
    html_path.touch()
    import os

    os.utime(html_path, ns=(old_mtime_ns, old_mtime_ns))

    renderer = QuartoReportRenderer(report_root=report_root)
    calls = []

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        calls.append((cwd, args))
        html_path.write_text("<h1>Updated</h1>", encoding="utf-8")

    renderer._run_quarto = fake_run_quarto
    monkeypatch.setattr(report_routes, "quarto_report_renderer", renderer)
    monkeypatch.setattr(report_preview_refresh, "quarto_report_renderer", renderer)

    response = await report_routes.get_report_html("air_report")

    assert response.path == str(html_path.resolve())
    assert (report_dir / "report.qmd").read_text(encoding="utf-8") == "# Updated source report\n"
    assert calls[0][0] == report_dir.resolve()
    assert calls[0][1][1] == "report.qmd"


@pytest.mark.asyncio
async def test_publish_session_file_renders_unmapped_qmd_as_report_resource(tmp_path, monkeypatch):
    report_root = tmp_path / "reports"
    source_dir = tmp_path / "source"
    source_qmd = source_dir / "original.qmd"
    source_dir.mkdir(parents=True)
    source_qmd.write_text("# Presented report\n", encoding="utf-8")

    renderer = QuartoReportRenderer(report_root=report_root)
    calls = []

    def fake_run_quarto(cwd: Path, args: list[str]) -> None:
        calls.append((cwd, args))
        (cwd / "report.html").write_text("<h1>Presented report</h1>", encoding="utf-8")

    renderer._run_quarto = fake_run_quarto
    monkeypatch.setattr(report_preview_refresh, "quarto_report_renderer", renderer)
    monkeypatch.setattr(publish_session_file_tool, "refresh_report_preview_for_qmd_path", lambda path: None)
    monkeypatch.setattr(
        publish_session_file_tool,
        "create_report_preview_for_source_qmd_path",
        report_preview_refresh.create_report_preview_for_source_qmd_path,
    )

    tool = publish_session_file_tool.PublishSessionFileTool()
    tool.allowed_dirs = [tmp_path.resolve()]

    result = await tool.execute(str(source_qmd))

    assert result["success"] is True
    assert result["metadata"]["file_type"] == "report"
    assert result["data"]["file_path"] == str(source_qmd.resolve())
    assert result["data"]["file_type"] == "report"
    report_id = result["data"]["report_id"]
    assert result["resources"][0]["group_key"] == f"report:{report_id}"
    assert result["resources"][1]["relation"] == "preview"
    assert result["resources"][1]["renderer"] == "html"
    assert "html_preview" not in result["data"]
    report_dir = report_root / report_id
    assert (report_dir / "report.qmd").read_text(encoding="utf-8") == "# Presented report\n"
    assert calls[0][0] == report_dir.resolve()
    assert calls[0][1][1] == "report.qmd"
