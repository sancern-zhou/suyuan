import json

import pytest

from app.scenarios.xuchang_daily_review.html_report import (
    build_html_report,
    build_report_from_evidence,
)


def _event(event_id="review-001"):
    return {
        "event_id": event_id, "station_id": "1005A", "station_name": "市一中",
        "pollutant": "PM10", "start_time": "2026-09-25T10:00:00",
        "end_time": "2026-09-25T11:00:00", "start_concentration": 30,
        "end_concentration": 45, "peak_concentration": 45,
        "peak_time": "2026-09-25T11:00:00", "peak_rise_absolute": 15,
        "peak_rise_percent": 50, "target_mean": 37.5,
        "wind": {"status": "ok", "direction_name": "北", "direction_deg": 0, "valid_hours": 2},
        "upwind_township_stations": [{
            "station_name": "建安区苏桥镇", "distance_km": 8.2,
            "bearing_name": "北", "concentration_mean": 40,
            "valid_hours": 2, "vs_target": "高于",
        }],
    }


def _map():
    return {"pollutant": "PM10", "frames": [{
        "time": "2026-09-25T10:00:00", "active_event_ids": ["review-001"],
        "records": [{"station_id": "1005A", "station_name": "市一中",
                     "longitude": 113.8, "latitude": 34.0, "concentration": 30}],
    }]}


def test_html_report_keeps_chapter_text_static_and_maps_per_pollutant():
    report = build_html_report({
        "target_date": "2026-09-25", "events": [_event()], "maps": [_map()],
        "event_analysis": {"review-001": "周边站同期浓度较高，传输方向仍需更多证据。"},
        "conclusion": "建议继续关注北部区域。",
    }, amap_key="test-key")
    assert report.count("PM10 时序变化地图</h3>") == 1
    assert "一、持续升高基本情况" in report
    assert "二、持续升高原因分析" in report
    assert "四、结论" in report
    assert "建安区苏桥镇" in report
    assert "30 → 45" in report
    assert "周边站同期浓度较高" in report
    assert "建议继续关注北部区域" in report
    assert "阶段说明" not in report
    assert "const MAPS=" in report
    assert "loadMap()" in report
    assert "v=2.1Beta" in report and "v=2.0" in report
    assert "base-satellite-0" in report and "base-terrain-0" in report
    assert "new AMap.TileLayer.Satellite()" in report
    assert "new AMap.TileLayer.RoadNet()" in report
    assert "timeline-0" in report and "speed-0" in report
    assert "legend-gradient" in report and "全天固定色阶" in report
    assert "红色光环标识" in report
    assert "marker.setOptions(options)" in report
    assert report.count("<table class='facts-table'>") == 1
    assert report.count("<table class='comparison-table'>") == 1
    assert "<th>站点</th><th>污染物</th><th>升高时段</th><th>浓度变化</th><th>升幅</th><th>绝对增量</th>" in report
    assert "<th>类型</th><th>站名</th><th>距离(km)</th><th>方位</th><th>浓度(μg/m³)</th><th>对比</th>" in report
    assert "table-layout:fixed" in report
    assert "overflow-x:auto" in report
    assert "tbody tr:nth-child(even)" in report


def test_html_groups_station_pollutant_and_shows_each_interrupted_segment():
    first = _event()
    second_segment = _event("segment-b")
    second_segment.update(start_time="2026-09-25T13:00:00", end_time="2026-09-25T13:00:00")
    first.update(
        end_time="2026-09-25T13:00:00", gap_hour_count=1,
        alert_intervals=[
            {"start_time": "2026-09-25T10:00:00", "end_time": "2026-09-25T11:00:00"},
            {"start_time": "2026-09-25T13:00:00", "end_time": "2026-09-25T13:00:00"},
        ],
        segments=[_event("segment-a"), second_segment],
    )
    later = _event("review-002")
    later.update(start_time="2026-09-25T16:00:00", end_time="2026-09-25T16:00:00")
    report = build_html_report({
        "target_date": "2026-09-25", "events": [first, later], "maps": [_map()],
        "event_analysis": {"review-001": "分段比较。", "review-002": "后续过程。"},
        "conclusion": "保留过程差异。",
    }, amap_key="test-key")
    assert report.count("<section class='station'>") == 1
    assert "市一中站｜PM10（2次过程）" in report
    assert report.count("<article>") == 2
    assert report.count("<table class='comparison-table'>") == 3
    assert "第1段｜2026-09-25 10:00—2026-09-25 11:00" in report
    assert "第2段｜2026-09-25 13:00—2026-09-25 13:00" in report
    assert "间隔1个无告警小时" in report


def test_assembler_reads_merged_events_and_requires_every_analysis(tmp_path):
    paths = {}
    for name, content in {
        "event_brief": {"event_count": 1, "events": [_event()]},
        "pollutant_maps": {"pollutant_count": 1, "maps": [_map()]},
        "provenance": {"source_provenance": {"station_hourly": "test"}},
    }.items():
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        paths[name] = str(path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"target_date": "2026-09-25", "episode_count": 1,
                                    "evidence_files": paths}), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing Agent event analysis"):
        build_report_from_evidence(str(manifest), {"conclusion": "结论"}, amap_key="test-key")
    output = build_report_from_evidence(str(manifest), {
        "summary_text": "合并后1次告警。", "conclusion": "仍需核查。",
        "event_analysis": {"review-001": "北部乡镇站高于目标站。"},
    }, amap_key="test-key")
    assert "合并后1次告警" in output
    assert "北部乡镇站高于目标站" in output
    render_config = tmp_path / "render_config.json"
    render_config.write_text(json.dumps({"public_key": "public-test-key"}), encoding="utf-8")
    manifest.write_text(json.dumps({"target_date": "2026-09-25", "episode_count": 1,
                                    "evidence_files": paths, "render_config_path": str(render_config)}), encoding="utf-8")
    assert "key=public-test-key" in build_report_from_evidence(str(manifest), {
        "event_analysis": {"review-001": "北部乡镇站高于目标站。"},
        "conclusion": "仍需核查。",
    })
