from pathlib import Path
import shutil

from app.services.quarto_report_renderer import QuartoReportRenderer


def test_share_html_preserves_preview_assets(tmp_path, monkeypatch):
    renderer = QuartoReportRenderer(report_root=tmp_path)
    report_dir = renderer.get_report_dir("share_test")
    report_dir.mkdir(parents=True)
    (report_dir / "report.qmd").write_text("# Report\n", encoding="utf-8")
    preview_css = report_dir / "report_files" / "libs" / "quarto-html" / "tippy.css"
    preview_css.parent.mkdir(parents=True)
    preview_css.write_text("body {}", encoding="utf-8")

    def render_without_preview_assets(directory: Path, _args: list[str]) -> None:
        shutil.rmtree(directory / "report_files")
        (directory / "report.export.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(renderer, "_run_quarto", render_without_preview_assets)
    assert renderer.render_share_html("share_test") == report_dir / "report.export.html"
    assert preview_css.read_text(encoding="utf-8") == "body {}"
