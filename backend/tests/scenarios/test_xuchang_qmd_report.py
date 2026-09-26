from pathlib import Path
import shutil
import zipfile

import pytest

from app.scenarios.xuchang_daily_review.qmd_report import (
    _map_css,
    build_qmd_report,
    write_qmd_report_from_evidence,
)


def _payload():
    return {
        "target_date": "2026-09-25",
        "events": [{
            "event_id": "event-1", "station_id": "1005A", "station_name": "市一中",
            "pollutant": "PM10", "start_time": "2026-09-25T10:00:00",
            "end_time": "2026-09-25T11:00:00", "peak_time": "2026-09-25T11:00:00",
            "start_concentration": 30, "peak_concentration": 45, "end_concentration": 45,
            "peak_rise_absolute": 15, "peak_rise_percent": 50, "target_mean": 37.5,
            "wind": {"status": "ok", "direction_name": "北", "direction_deg": 0, "valid_hours": 2},
            "upwind_township_stations": [{"station_name": "建安区苏桥镇", "distance_km": 8.2,
                                          "bearing_name": "北", "concentration_mean": 40,
                                          "valid_hours": 2, "vs_target": "高于"}],
        }],
        "maps": [{"pollutant": "PM10", "scale_min": 20, "scale_max": 60,
                  "frames": [{"time": "2026-09-25T10:00:00", "active_event_ids": ["event-1"],
                              "records": [{"station_id": "1005A", "station_name": "市一中",
                                           "longitude": 113.8, "latitude": 34.0, "concentration": 30}]}]}],
        "event_analysis": {"event-1": "北部乡镇站同期浓度较高，仍需其他证据确认传输。"},
        "summary_text": "合并后一次告警过程。", "conclusion": "继续关注北部区域。",
    }


def test_qmd_keeps_fixed_chapters_and_format_specific_maps():
    qmd = build_qmd_report(_payload(), {"PM10": "timeline_1_PM10.png"})
    assert "## 一、持续升高基本情况" in qmd
    assert "## 二、持续升高原因分析" in qmd
    assert "## 四、结论" in qmd
    assert qmd.count("| 站点 | 污染物 | 升高时段 |") == 1
    assert "建安区苏桥镇" in qmd
    assert "北部乡镇站同期浓度较高" in qmd
    assert 'when-format="html"' in qmd
    assert 'when-format="docx"' not in qmd
    assert "base-satellite-0" in qmd
    assert "assets/xuchang_map.js" in qmd
    assert "assets/charts/timeline_1_PM10.png" in qmd
    assert "number-sections: false" in qmd
    assert ".map-hud" in _map_css()


def test_qmd_writer_returns_packaging_paths(tmp_path, monkeypatch):
    payload = _payload()
    monkeypatch.setattr(
        "app.scenarios.xuchang_daily_review.qmd_report.load_report_payload_from_evidence",
        lambda *_args, **_kwargs: (payload, "public-test-key"),
    )
    result = write_qmd_report_from_evidence("manifest.json", {}, str(tmp_path / "review.qmd"))
    assert result["report_id"] == "xuchang_daily_review_20260925"
    assert result["event_count"] == result["pollutant_count"] == 1
    assert Path(result["source_qmd_path"]).is_file()
    assert len(result["assets"]) == 3
    assert all(Path(item["path"]).is_file() for item in result["assets"])
    assert "v=2.1Beta" in (tmp_path / "xuchang_map_review.js").read_text()


def test_qmd_writer_keeps_css_when_no_alerts(tmp_path, monkeypatch):
    payload = _payload()
    payload["events"] = []
    payload["maps"] = []
    payload["event_analysis"] = {}
    monkeypatch.setattr(
        "app.scenarios.xuchang_daily_review.qmd_report.load_report_payload_from_evidence",
        lambda *_args, **_kwargs: (payload, "public-test-key"),
    )
    result = write_qmd_report_from_evidence("manifest.json", {}, str(tmp_path / "review.qmd"))
    assert result["event_count"] == result["pollutant_count"] == 0
    assert [item["name"] for item in result["assets"]] == ["xuchang_map_review.css"]
    assert "昨日未识别告警过程" in Path(result["source_qmd_path"]).read_text()


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
async def test_qmd_package_renders_interactive_html_and_static_word(tmp_path, monkeypatch):
    from app.services.quarto_report_renderer import QuartoReportRenderer
    from app.tools.report.report_package import tool as package_tool

    payload = _payload()
    monkeypatch.setattr(
        "app.scenarios.xuchang_daily_review.qmd_report.load_report_payload_from_evidence",
        lambda *_args, **_kwargs: (payload, "public-test-key"),
    )
    built = write_qmd_report_from_evidence("manifest.json", {}, str(tmp_path / "review.qmd"))
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(package_tool, "quarto_report_renderer", renderer)
    result = await package_tool.CreateReportPackageTool().execute(
        report_id=built["report_id"], source_qmd_path=built["source_qmd_path"],
        assets=built["assets"], output_formats=["html", "docx", "share_html"],
    )
    assert result["success"] is True, result.get("summary")
    report_dir = tmp_path / "reports" / built["report_id"]
    html = (report_dir / "report.html").read_text(encoding="utf-8")
    assert "base-satellite-0" in html
    assert "assets/xuchang_map_review.js" in html
    assert "assets/charts/timeline_1_PM10_review.png" in html
    shared_html = (report_dir / "report.export.html").read_text(encoding="utf-8")
    assert "base-satellite-0" in shared_html
    assert "public-test-key" in shared_html
    assert "assets/xuchang_map_review.js" not in shared_html
    assert (report_dir / "report.docx").is_file()
    with zipfile.ZipFile(report_dir / "report.docx") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        assert "北部乡镇站同期浓度较高" in xml
        assert any(name.startswith("word/media/") for name in archive.namelist())
        assert "base-satellite-0" not in xml
