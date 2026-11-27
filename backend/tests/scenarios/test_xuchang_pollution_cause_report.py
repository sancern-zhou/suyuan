"""④污染原因分析报告 QMD 构建与报告包渲染测试。"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from app.scenarios.xuchang_pollution_cause import report as cause_report


def _evidence():
    return {
        "city": "许昌市",
        "target_date": "2026-11-10",
        "rule_description": "许昌市PM2.5日均浓度高于相邻五市均值30%以上（轻度污染及以上为20%）",
        "deviation_percent": 29.7,
        "city_rank": 14,
        "city_count": 18,
        "xuchang_pm25": 96.0,
        "data_source": "ssfb_city_day",
        "city_rows": [
            {"city": "许昌市", "pm25": 96.0, "is_xuchang": True},
            {"city": "郑州|市", "pm25": 80.0, "is_neighbor": True},
            {"city": "周口市", "pm25": None, "is_neighbor": True},
        ],
    }


def _brief():
    return {
        "episode_count": 1,
        "alert_list": [{
            "station_name": "许昌学院",
            "target_pollutant": "PM2.5",
            "episode_start": "2026-11-10T10:00:00",
            "episode_end": "2026-11-10T12:00:00",
            "peak_time": "2026-11-10T11:00:00",
            "regional_classification": "regional",
            "transport_conclusion": "consistent",
        }],
        "meteorology_intervals": {
            "nmc": {
                "temperature_2m": {"valid_hours": 24, "min": 8.2, "max": 17.9, "mean": 12.4},
                "relative_humidity_2m": {"valid_hours": 24, "mean": 74.5},
                "wind_speed_10m": {"valid_hours": 23, "mean": 1.8},
                "precipitation": {"valid_hours": 24, "sum": 0.0},
            },
            "era5": {
                "boundary_layer_height": {"valid_hours": 24, "min": 120.0, "max": 860.0, "mean": 430.2},
                "cloud_cover": {"valid_hours": 24, "mean": 41.0},
            },
        },
    }


def test_build_qmd_contains_notice_and_evidence_tables():
    message = "【污染原因分析】\n一、触发情况\n许昌PM2.5偏高，区域传输可能性待核实。"
    qmd = cause_report.build_pollution_cause_qmd(_evidence(), _brief(), message)

    assert "title: \"许昌市污染原因分析通报\"" in qmd
    assert "preserve-template-structure: true" in qmd
    assert "## 一、通报正文" in qmd
    assert "【污染原因分析】" not in qmd.split("## 一、通报正文", 1)[1]
    assert "许昌PM2.5偏高" in qmd
    assert "## 附1、区域PM2.5日均值对比" in qmd
    assert "郑州\\|市" in qmd
    assert "| 周口市 | 缺测 | 相邻五市 |" in qmd
    assert "第14位" in qmd
    assert "## 附2、气象要素区间统计" in qmd
    assert "边界层高度(m)" in qmd
    assert "## 附3、站点快速告警过程" in qmd
    assert "许昌学院" in qmd
    assert "不认定具体污染责任" in qmd


def test_build_qmd_degrades_when_brief_missing():
    qmd = cause_report.build_pollution_cause_qmd(_evidence(), None, "通报正文")
    assert "昨日气象观测统计暂缺。" in qmd
    assert "昨日无站点快速告警过程记录。"


def test_build_qmd_renders_v8_hourly_rise_alert_fields_with_transport_join(tmp_path, monkeypatch):
    """生产 report_brief v8 字段名（pollutant/start_time/peak_rise_*）必须可渲染，
    传输结论经 hourly_rise_detection → transport_responses 关联（回归 2026-11-22
    附3 全列为空的字段错位缺陷）。"""
    monkeypatch.setattr(cause_report, "get_data_registry", lambda: tmp_path)
    review_dir = tmp_path / "xuchang_station_daily_reviews" / "20261110"
    review_dir.mkdir(parents=True)
    (review_dir / "hourly_rise_detection.json").write_text(json.dumps({
        "events": [{
            "episode_id": "hourly-rise-2026111009-1008A-pm25",
            "station_id": "1008A",
            "target_pollutant": "PM2.5",
            "episode_start": "2026-11-10T10:00:00",
            "episode_end": "2026-11-10T12:00:00",
        }],
    }, ensure_ascii=False), encoding="utf-8")
    (review_dir / "transport_responses.json").write_text(json.dumps({
        "episodes": [{
            "episode_id": "hourly-rise-2026111009-1008A-pm25",
            "transport_consistency": {
                "conclusion": "local_prominence",
                "conclusion_label": "局地突出",
            },
        }],
    }, ensure_ascii=False), encoding="utf-8")

    brief = {
        "episode_count": 1,
        "alert_list": [{
            "station_id": "1008A",
            "station_name": "许昌学院",
            "pollutant": "PM2.5",
            "start_time": "2026-11-10T10:00:00",
            "end_time": "2026-11-10T12:00:00",
            "peak_rise_absolute": 17.0,
            "peak_rise_percent": 89.5,
        }],
        "meteorology_intervals": {},
    }
    qmd = cause_report.build_pollution_cause_qmd(
        _evidence(), brief, "通报正文",
        transport_conclusions=cause_report.load_transport_conclusions("2026-11-10"),
    )

    assert "| 许昌学院 | PM2.5 | 2026-11-10T10:00 | 2026-11-10T12:00 | 17.0μg（89.5%） | 局地突出 |" in qmd
    assert "| 站点 | 污染物 | 开始 | 结束 | 峰值升幅 | 传输结论 |" in qmd


def test_build_qmd_transport_join_fail_open_without_review_files(tmp_path, monkeypatch):
    """回顾目录缺文件时 fail-open：行仍渲染，传输结论列为"—"。"""
    monkeypatch.setattr(cause_report, "get_data_registry", lambda: tmp_path)
    assert cause_report.load_transport_conclusions("2026-11-10") == {}

    brief = {
        "episode_count": 1,
        "alert_list": [{
            "station_id": "1008A",
            "station_name": "许昌学院",
            "pollutant": "PM2.5",
            "start_time": "2026-11-10T10:00:00",
            "end_time": "2026-11-10T12:00:00",
            "peak_rise_absolute": 17.0,
            "peak_rise_percent": 89.5,
        }],
        "meteorology_intervals": {},
    }
    qmd = cause_report.build_pollution_cause_qmd(_evidence(), brief, "通报正文")
    assert "| 许昌学院 | PM2.5 | 2026-11-10T10:00 | 2026-11-10T12:00 | 17.0μg（89.5%） | — |" in qmd


def test_write_qmd_returns_package_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(cause_report, "get_data_registry", lambda: tmp_path)

    built = cause_report.write_pollution_cause_qmd(
        _evidence(), _brief(), "通报正文", execution_id="exec/中文 1"
    )

    assert built["report_id"] == "xuchang_pollution_cause_20261110_exec____1"
    assert built["assets"] == []
    qmd_path = Path(built["source_qmd_path"])
    assert qmd_path == (
        tmp_path / "xuchang_pollution_cause" / "20261110" / "report_source_exec____1.qmd"
    )
    assert qmd_path.is_file()
    assert "许昌市污染原因分析通报" in qmd_path.read_text(encoding="utf-8")


def test_write_qmd_requires_execution_id(tmp_path, monkeypatch):
    monkeypatch.setattr(cause_report, "get_data_registry", lambda: tmp_path)
    with pytest.raises(ValueError, match="execution_id"):
        cause_report.write_pollution_cause_qmd(_evidence(), None, "正文", execution_id="")


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
async def test_qmd_package_renders_docx(tmp_path, monkeypatch):
    from app.services.quarto_report_renderer import QuartoReportRenderer
    from app.tools.report.report_package import tool as package_tool

    monkeypatch.setattr(cause_report, "get_data_registry", lambda: tmp_path)
    built = cause_report.write_pollution_cause_qmd(
        _evidence(), _brief(), "【污染原因分析】通报正文", execution_id="exec-render-1"
    )
    renderer = QuartoReportRenderer(report_root=tmp_path / "reports")
    monkeypatch.setattr(package_tool, "quarto_report_renderer", renderer)

    result = await package_tool.CreateReportPackageTool().execute(
        report_id=built["report_id"],
        source_qmd_path=built["source_qmd_path"],
        assets=built["assets"],
        output_formats=["html", "docx"],
    )

    assert result["success"], result.get("summary")
    report_dir = tmp_path / "reports" / built["report_id"]
    assert (report_dir / "report.html").is_file()
    assert (report_dir / "report.docx").is_file()
    with zipfile.ZipFile(report_dir / "report.docx") as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        assert "许昌PM2.5偏高" not in xml  # 本用例通报文本为“通报正文”
        assert "通报正文" in xml
        assert "许昌学院" in xml
