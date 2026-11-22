"""④污染原因分析通报工作流兜底模板与投递链路单元测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app.utils.path_config import PROJECT_ROOT

from app.scenarios.xuchang_pollution_cause import notification
from app.scenarios.xuchang_station_deviation import wechat_push_queue


def _evidence(**overrides):
    evidence = {
        "city": "许昌市",
        "target_date": "2026-11-10",
        "rule_description": "许昌市PM2.5日均浓度高于相邻五市均值30%以上（轻度污染及以上为20%）",
        "ratio_threshold": 0.20,
        "default_ratio_threshold": 0.30,
        "light_pollution_ratio_threshold": 0.20,
        "light_pollution_pm25_limit": 60.0,
        "pollution_level_tier": "light_pollution_or_above",
        "neighbor_cities": ["郑州市", "开封市", "平顶山市", "漯河市", "周口市"],
        "xuchang_pm25": 96.0,
        "neighbor_mean_pm25": 74.0,
        "deviation_percent": 29.7,
        "triggered": True,
        "streak_days": 2,
        "city_rank": 14,
        "city_count": 18,
        "city_rows": [
            {"city": "许昌市", "pm25": 96.0, "is_neighbor": False, "is_xuchang": True},
            {"city": "郑州市", "pm25": 80.0, "is_neighbor": True, "is_xuchang": False},
            {"city": "周口市", "pm25": 80.0, "is_neighbor": True, "is_xuchang": False},
        ],
    }
    evidence.update(overrides)
    return evidence


def test_fallback_message_sections_and_numbers(tmp_path, monkeypatch):
    import app.scenarios.xuchang_pollution_cause.notification as notification_module

    monkeypatch.setattr(
        notification_module,
        "load_review_manifest",
        lambda target_date: {
            "episode_count": 2,
            "alert_list": [{"station_name": "许昌学院"}, {"station_name": "开发区"}],
            "meteorology_intervals": {
                "nmc": {
                    "valid_hours": 24,
                    "temperature_2m": {"min": 10.0, "max": 20.0},
                    "relative_humidity_2m": {"mean": 75.0},
                    "wind_speed_10m": {"mean": 1.8},
                    "precipitation": {"sum": 0.0},
                }
            },
        },
    )
    message = notification.compose_fallback_message(_evidence())
    assert message.startswith("【污染原因分析】")
    for section in ("一、触发情况", "二、区域对比", "三、气象概况",
                    "四、站点告警情况", "五、关注建议"):
        assert section in message
    assert "29.7%" in message
    assert "超过20%触发阈值" in message
    assert "轻度污染及以上" in message
    assert "连续2天" in message
    assert "第14位" in message
    assert "郑州市80.0" in message
    assert "2个" in message
    assert "不认定" in message


def test_fallback_message_normal_tier(tmp_path, monkeypatch):
    """normal 档（默认 30%）触发时阈值表述不带轻污染档附注。"""
    import app.scenarios.xuchang_pollution_cause.notification as notification_module

    monkeypatch.setattr(
        notification_module, "load_review_manifest", lambda target_date: None
    )
    evidence = _evidence(
        xuchang_pm25=58.0,
        ratio_threshold=0.30,
        pollution_level_tier="normal",
        deviation_percent=36.8,
    )
    message = notification.compose_fallback_message(evidence)
    assert "超过30%触发阈值" in message
    assert "轻度污染及以上" not in message


def test_fallback_message_v1_evidence_without_tier(tmp_path, monkeypatch):
    """旧 v1 证据（无档位字段）只表述生效阈值，不报错。"""
    import app.scenarios.xuchang_pollution_cause.notification as notification_module

    monkeypatch.setattr(
        notification_module, "load_review_manifest", lambda target_date: None
    )
    evidence = _evidence(
        default_ratio_threshold=None,
        light_pollution_ratio_threshold=None,
        light_pollution_pm25_limit=None,
        pollution_level_tier=None,
    )
    message = notification.compose_fallback_message(evidence)
    assert "超过20%触发阈值" in message
    assert "轻度污染及以上" not in message


def test_fallback_message_without_review_manifest(tmp_path, monkeypatch):
    import app.scenarios.xuchang_pollution_cause.notification as notification_module

    monkeypatch.setattr(
        notification_module, "load_review_manifest", lambda target_date: None
    )
    message = notification.compose_fallback_message(_evidence())
    assert "气象观测数据暂缺" in message
    assert "无站点快速告警记录" in message


def test_build_llm_evidence_folds_review():
    evidence = _evidence()
    brief = {"episode_count": 3, "meteorology_intervals": {"nmc": {"valid_hours": 20}}}
    payload = notification.build_llm_evidence(evidence, brief)
    assert payload["trigger_evidence"]["deviation_percent"] == 29.7
    assert payload["trigger_evidence"]["pollution_level_tier"] == "light_pollution_or_above"
    assert payload["trigger_evidence"]["light_pollution_pm25_limit"] == 60.0
    assert payload["daily_review"]["episode_count"] == 3
    assert "meteorology_intervals" in payload["daily_review"]
    assert len(payload["city_rows"]) == 3

    payload_empty = notification.build_llm_evidence(evidence, None)
    assert "daily_review" not in payload_empty


def test_load_review_brief_prefers_report_brief_file(tmp_path):
    review_dir = tmp_path / "xuchang_station_daily_reviews" / "20261110"
    review_dir.mkdir(parents=True)
    brief_path = review_dir / "report_brief.json"
    brief_path.write_text(json.dumps({
        "episode_count": 2,
        "alert_list": [{"station_name": "许昌学院"}],
        "meteorology_intervals": {"nmc": {"valid_hours": 24}},
    }, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "schema_version": "xuchang_station_daily_review/v3",
        "episode_count": 99,
        "evidence_files": {"report_brief": str(brief_path)},
    }

    brief = notification.load_review_brief(manifest)

    assert brief is not None
    assert brief["episode_count"] == 2
    assert brief["alert_list"] == [{"station_name": "许昌学院"}]
    assert brief["meteorology_intervals"]["nmc"]["valid_hours"] == 24

    legacy = notification.load_review_brief({"episode_count": 1, "alert_list": []})
    assert legacy == {"episode_count": 1, "alert_list": []}
    assert notification.load_review_brief(None) is None


def _prepare_workflow(monkeypatch, tmp_path):
    evidence_path = tmp_path / "trigger-evidence.json"
    evidence_path.write_text(
        json.dumps(_evidence(), ensure_ascii=False), encoding="utf-8"
    )
    review_dir = tmp_path / "xuchang_station_daily_reviews" / "20261110"
    review_dir.mkdir(parents=True, exist_ok=True)
    brief_path = review_dir / "report_brief.json"
    brief_path.write_text(json.dumps({
        "episode_count": 1,
        "alert_list": [{"station_name": "许昌学院", "target_pollutant": "PM2.5"}],
        "meteorology_intervals": {"nmc": {"valid_hours": 24}},
    }, ensure_ascii=False), encoding="utf-8")
    (review_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "xuchang_station_daily_review/v3",
        "episode_count": 1,
        "evidence_files": {"report_brief": str(brief_path)},
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(notification, "get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(
        "app.scenarios.xuchang_station_deviation.wechat_push_queue.get_data_registry",
        lambda: tmp_path,
    )
    monkeypatch.setattr(notification, "resolve_audience_accounts", lambda roles: [])

    delivered = {}

    class _FakeDelivery:
        async def resolve_recipients(self, user_ids):
            delivered["user_ids"] = list(user_ids)
            return [{"user_id": user_ids[0], "sent": True}]

        async def deliver(self, *, task, event, execution, output, recipients):
            delivered["message"] = output.broadcast.message
            delivered["media"] = output.broadcast.media
            return [{"user_id": recipients[0]["user_id"], "sent": True}]

    monkeypatch.setattr(notification, "EventTaskDelivery", _FakeDelivery)

    async def _fake_message(evidence, review_brief, task, history_section=None):
        return "【污染原因分析】一、触发情况\n许昌PM2.5偏高。"

    monkeypatch.setattr(notification, "_generate_cause_message", _fake_message)

    task = SimpleNamespace(
        target_user_ids=["app:android:android_demo"],
        prompt="执行指令测试",
        timeout_seconds=600,
    )
    execution = SimpleNamespace(execution_id="exec-report-1")
    event = SimpleNamespace(payload={"evidence_package_path": str(evidence_path)})
    return task, execution, event, delivered


def test_workflow_generates_report_and_delivers_docx_attachment(tmp_path, monkeypatch):
    task, execution, event, delivered = _prepare_workflow(monkeypatch, tmp_path)
    docx_path = tmp_path / "reports" / "xuchang_pollution_cause" / "report.docx"
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    docx_path.write_bytes(b"fake-docx")
    report_payload = {
        "report_id": "xuchang_pollution_cause_20261110_exec_report_1",
        "docx_path": str(docx_path),
        "html_path": str(docx_path.with_name("report.html")),
        "agent_path": str(docx_path),
        "attachment": {
            "path": str(docx_path),
            "filename": "污染原因分析通报_20261110.docx",
            "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
    }

    async def _fake_report(evidence, review_brief, message, *, task, execution):
        assert review_brief is not None and review_brief["episode_count"] == 1
        return report_payload

    monkeypatch.setattr(
        notification, "generate_pollution_cause_report", _fake_report
    )

    result = asyncio.run(
        notification.run_pollution_cause_workflow(
            task=task, execution=execution, event=event
        )
    )

    assert result["success"] is True
    assert result["report_generated"] is True
    assert result["final_message"].endswith("报告全文见附件。")
    assert delivered["media"] == [str(docx_path)]
    assert result["tool_call_details"]["media"] == [str(docx_path)]
    pending = wechat_push_queue.list_pending_messages(root=tmp_path)
    assert len(pending) == 1
    assert pending[0]["media"] == []
    assert pending[0]["attachments"] == [report_payload["attachment"]]


def test_workflow_fails_open_when_report_generation_fails(tmp_path, monkeypatch):
    task, execution, event, delivered = _prepare_workflow(monkeypatch, tmp_path)

    async def _broken_report(evidence, review_brief, message, *, task, execution):
        raise RuntimeError("quarto missing")

    monkeypatch.setattr(
        notification, "generate_pollution_cause_report", _broken_report
    )

    result = asyncio.run(
        notification.run_pollution_cause_workflow(
            task=task, execution=execution, event=event
        )
    )

    assert result["success"] is True
    assert result["report_generated"] is False
    assert "报告未生成" in result["summary"]
    assert "报告全文见附件。" not in result["final_message"]
    assert delivered["media"] == []
    pending = wechat_push_queue.list_pending_messages(root=tmp_path)
    assert len(pending) == 1
    assert pending[0]["attachments"] == []

def test_wechat_sink_enqueues_broadcast_message_and_docx(monkeypatch):
    """Agent 模式执行成功后，钩子取广播调用的文案与 DOCX 补投微信群队列。"""
    from app.scheduled_tasks.models.execution import ExecutionStatus, StepExecution
    from app.scenarios.xuchang_pollution_cause import wechat_delivery

    captured = {}
    monkeypatch.setattr(
        wechat_delivery,
        "enqueue_wechat_message",
        lambda kind, text, **kwargs: captured.update(
            {"kind": kind, "text": text, **kwargs}
        ) or {"id": "wx-test"},
    )
    execution = SimpleNamespace(
        task_id=wechat_delivery.TASK_ID,
        execution_id="exec-report-1",
        status=ExecutionStatus.SUCCESS,
        steps=[StepExecution(
            step_id="task",
            status=ExecutionStatus.SUCCESS,
            agent_prompt="p",
            agent_response="done",
            tool_calls=[{
                "tool": "broadcast_social_users",
                "success": True,
                "args": {
                    "message": "【污染原因分析】通报全文",
                    "media": [
                        # 绝对路径应归一化为项目相对路径（PROJECT_ROOT 动态构造）
                        str(Path(PROJECT_ROOT) / "backend/backend_data_registry/reports/r1/report.docx"),
                        "backend/backend_data_registry/reports/r2/report.docx",
                    ],
                },
                "media": [],
            }],
        )],
    )
    event = SimpleNamespace(
        payload={"target_date": "2026-11-21"},
        attributes={"target_date": "2026-11-21"},
    )
    asyncio.run(wechat_delivery.sink_dispatch(
        SimpleNamespace(task_id=wechat_delivery.TASK_ID),
        event,
        execution,
    ))

    assert captured["kind"] == "pollution_cause"
    assert captured["text"] == "【污染原因分析】通报全文"
    assert captured["attachments"] == [{
        "path": "backend/backend_data_registry/reports/r1/report.docx",
        "filename": "污染原因分析通报_20261121.docx",
        "mime": wechat_delivery.DOCX_MIME_TYPE,
    }]
    assert captured["metadata"]["execution_id"] == "exec-report-1"

def test_wechat_sink_ignores_failure_and_other_tasks(monkeypatch):
    from app.scheduled_tasks.models.execution import ExecutionStatus
    from app.scenarios.xuchang_pollution_cause import wechat_delivery

    enqueued = []
    monkeypatch.setattr(
        wechat_delivery,
        "enqueue_wechat_message",
        lambda kind, text, **kwargs: enqueued.append((kind, text)),
    )
    failed = SimpleNamespace(
        task_id=wechat_delivery.TASK_ID,
        execution_id="exec-failed",
        status=ExecutionStatus.FAILED,
        steps=[],
    )
    asyncio.run(wechat_delivery.sink_dispatch(
        SimpleNamespace(task_id=wechat_delivery.TASK_ID),
        SimpleNamespace(payload={}),
        failed,
    ))
    other_task = SimpleNamespace(
        task_id="task_other",
        execution_id="exec-other",
        status=ExecutionStatus.SUCCESS,
        steps=[],
    )
    asyncio.run(wechat_delivery.sink_dispatch(other_task, SimpleNamespace(payload={}), other_task))
    assert enqueued == []


def test_wechat_sink_skips_when_broadcast_call_missing(monkeypatch):
    from app.scheduled_tasks.models.execution import ExecutionStatus
    from app.scenarios.xuchang_pollution_cause import wechat_delivery

    enqueued = []
    monkeypatch.setattr(
        wechat_delivery,
        "enqueue_wechat_message",
        lambda kind, text, **kwargs: enqueued.append((kind, text)),
    )
    execution = SimpleNamespace(
        task_id=wechat_delivery.TASK_ID,
        execution_id="exec-no-broadcast",
        status=ExecutionStatus.SUCCESS,
        steps=[SimpleNamespace(
            tool_calls=[{"tool": "read_file", "success": True, "args": {}}],
        )],
    )
    asyncio.run(wechat_delivery.sink_dispatch(
        SimpleNamespace(task_id=wechat_delivery.TASK_ID),
        SimpleNamespace(payload={}),
        execution,
    ))
    assert enqueued == []
