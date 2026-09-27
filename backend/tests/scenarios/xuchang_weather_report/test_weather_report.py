from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.scenarios.xuchang_weather_report import evidence, qmd_report
from app.scenarios.xuchang_weather_report import task_migration
from app.scheduled_tasks.models import ScheduledTask, TriggerType, ScheduleType

START = date(2026, 9, 28)


def sources(missing_wind=False):
    nmc = []
    for offset in range(56):
        stamp = datetime(2026, 9, 28) + timedelta(hours=3 * offset)
        nmc.append({
            "forecast_time": stamp.isoformat(sep=" "), "publish_time": "2026-09-28 07:30:00",
            "weather_text": "多云", "temperature": 20 + offset % 5, "humidity": 60 + offset % 20,
            "pressure": 1005, "wind_direction": "东北风", "wind_direction_degrees": 45,
            "wind_speed": None if missing_wind and offset == 3 else (1.2 if offset in (2, 3, 4) else 3.0),
            "precipitation_probability": 10,
        })
    aq = [{"TimePoint": (START + timedelta(days=i)).isoformat(), "MinAqi": 45,
           "MaxAqi": 65, "MaxPollution": "PM2.5", "UpdateDate": START.isoformat()} for i in range(7)]
    outlook = [{"forecast_date": (START + timedelta(days=i)).isoformat(),
                "fetched_at": "2026-09-28 06:20:00", "weather_text": "晴",
                "temp_max": 25, "temp_min": 15, "wind_direction_day": "东风",
                "wind_direction_night": "东北风", "wind_force": "<3级"} for i in range(7, 15)]
    return {"nmc": nmc, "aq": aq, "outlook": outlook}


def agent(facts):
    return {
        "overview": "前七天气象条件总体平稳，局地弱风时次需关注扩散。",
        "daily": {day["date"]: {"situation": "气温平稳，弱风时次关注扩散。",
                                "pm25": "弱风时次关注颗粒物累积。",
                                "o3": "仅作气象条件提示，无浓度预报。"} for day in facts["days"]},
        "outlook": {day["date"]: "日尺度风力信息有限，需滚动更新。" for day in facts["outlook"]},
        "phases": ["9月28日—30日：局地弱风→扩散关注。"],
        "outlook_trend": "中期风力为日尺度预报，继续跟踪更新。",
    }


def test_evidence_separates_batches_and_keeps_missingness():
    data = sources(missing_wind=True)
    data["aq"] = [{**row, "UpdateDate": "2026-09-27"} for row in data["aq"]]
    data["outlook"][0]["fetched_at"] = "2026-09-27 06:20:00"
    facts = evidence.build_evidence(START, data)
    assert len(facts["days"]) == 7
    assert facts["days"][0]["aqi_grade"] == "未提供"
    assert facts["days"][0]["wind_mean_complete"] is False
    assert "fetched_at" not in facts["outlook"][0]
    assert not facts["risk_periods"]
    assert any("空气质量预报" in note for note in facts["warnings"])


def test_returning_wind_grade_is_preserved_and_empty_sources_keep_template():
    assert evidence._changes(["一般", "差", "差", "一般"]) == ["一般", "差", "一般"]
    facts = evidence.build_evidence(START, {"nmc": [], "aq": [], "outlook": []})
    narrative = agent(facts)
    for fields in narrative["daily"].values():
        fields.update(situation="气象资料未提供，无法判断。", pm25="气象风险证据不足。", o3="气象风险证据不足。")
    for key in narrative["outlook"]:
        narrative["outlook"][key] = "当日预报未提供。"
    qmd = qmd_report.build_qmd(facts, narrative, None)
    assert "无法生成七日连续气象图" in qmd
    assert qmd_report.validate_qmd_structure(qmd, has_chart=False)["outlook_rows"] == 8


def test_fixed_report_and_single_chart(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(evidence, "render_weather_timeseries", lambda **_: ("aGVsbG8=", {"valid_point_count": 56, "day_count": 7}, []))
    package = evidence.write_evidence_package(START, sources(), registry=tmp_path)
    manifest = json.loads(Path(package["manifest_path"]).read_text(encoding="utf-8"))
    facts = json.loads(Path(manifest["facts_path"]).read_text(encoding="utf-8"))
    output = tmp_path / "report.qmd"
    result = qmd_report.write_qmd_report_from_evidence(package["manifest_path"], agent(facts), str(output), "exec_123")
    qmd = output.read_text(encoding="utf-8")
    assert result["validation"] == {"headings": 8, "tables": 6, "chart_count": 1, "day_rows": 7, "outlook_rows": 8}
    assert result["report_id"] == "xuchang_weather_exec_123"
    assert "![未来7天气象小时变化](assets/charts/weather_timeseries.png)" in qmd
    assert "preserve-template-structure: true" in qmd
    assert "title:" not in qmd.split("---", 2)[1]
    assert len(facts["risk_periods"]) == 1
    assert facts["risk_periods"][0]["alpha"] == 0.2
    bad = agent(facts); bad["daily"].pop(START.isoformat())
    with pytest.raises(ValueError, match="7个日期"):
        qmd_report.build_qmd(facts, bad, "weather_timeseries.png")


def test_only_original_weather_seed_is_migrated():
    path = task_migration.PROJECT_ROOT / "projects/xuchang/scheduled_tasks" / f"{task_migration.TASK_ID}.json"
    seed = ScheduledTask.model_validate_json(path.read_text(encoding="utf-8"))
    old = seed.model_copy(update={
        "trigger_type": TriggerType.SCHEDULE,
        "schedule_type": ScheduleType.WEEKLY_MONDAY_8AM,
        "event_type": None,
        "prompt": task_migration.OLD_PROMPT_MARKER,
        "tool_names": ["execute_sql_query", "execute_python"],
    })
    updated = []
    service = SimpleNamespace(task_storage=SimpleNamespace(get=lambda _: old),
                              update_task=lambda task: updated.append(task))
    assert task_migration.migrate_weather_task(service)
    assert updated[0].trigger_type == TriggerType.EVENT
    assert updated[0].event_type == evidence.EVENT_TYPE
    assert updated[0].tool_names == ["execute_python", "create_report_package", "broadcast_social_users"]
    old.prompt = "用户自定义天气任务"
    assert not task_migration.migrate_weather_task(service)
