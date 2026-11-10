"""故障工单审核证据包服务的拆分存储与状态流转测试。"""
import pytest

from app.services.jiangsu_work_order_review import (
    attach_judgment,
    get_order,
    get_order_source,
    list_orders,
    record_operation,
    save_evidence,
    validate_removal_declaration_consistency,
)


@pytest.fixture()
def isolated_registry(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "data_registry_dir", str(tmp_path))
    return tmp_path


def _sample_package(code="FA260914178938611578927"):
    return {
        "working_order_code": code,
        "title": "站点PM10偏高",
        "site_name": "阜宁滨湖高级中学",
        "site_id": "3077A",
        "pollutant": "PM10",
        "window": {"start_time": "2026-09-13 19:41:00", "end_time": "2026-09-16 19:41:00"},
        "sources": {
            "station_hour": {
                "status": "success", "record_count": 2,
                "data": {"points": [{"time": "2026-09-13 20:00:00", "value": 23}]},
            },
            "weather": {
                "status": "success", "record_count": 1,
                "data": {"rows": [{"timePoint": "2026-09-13 20:00:00", "windSpeed": 2.1}]},
            },
        },
    }


def test_save_evidence_splits_index_and_sources(isolated_registry):
    entry = save_evidence(_sample_package())

    assert entry["status"] == "待审核"
    assert set(entry["source_files"]) == {"station_hour", "weather"}
    # index 不含来源明细，分文件单独落盘
    doc = get_order("FA260914178938611578927")
    assert "data" not in doc["index"]["sources"]["station_hour"]
    source = get_order_source("FA260914178938611578927", "station_hour")
    assert source["data"]["points"][0]["value"] == 23


def test_list_orders_filters_by_keyword_and_status(isolated_registry):
    save_evidence(_sample_package())

    payload = list_orders(keyword="阜宁")
    assert payload["total"] == 1
    payload = list_orders(keyword="不存在的站点")
    assert payload["total"] == 0
    payload = list_orders(status="待审核")
    assert payload["total"] == 1
    payload = list_orders(status="已归档")
    assert payload["total"] == 0


def test_attach_judgment_updates_status(isolated_registry):
    save_evidence(_sample_package())

    entry = attach_judgment("FA260914178938611578927", {
        "review_id": "review_abc", "version": 1, "subject_id": "FA260914178938611578927",
        "updated_at": "2026-09-18T10:00:00",
        "submission": {"decision": "pass", "comment": "通过，数据保留",
                       "data_impact": [{"pollutant": "PM10", "decision": "keep"}]},
    })
    assert entry["status"] == "待归档"
    assert entry["review_id"] == "review_abc"

    doc = get_order("FA260914178938611578927")
    assert doc["index"]["judgment"]["comment"] == "通过，数据保留"


def test_attach_judgment_mark_areas_carry_pollutant(isolated_registry):
    """多污染物剔除建议 → 每个区间带 pollutant 字段，工作台据此按污染物补曲线与着色。"""
    save_evidence(_sample_package())
    attach_judgment("FA260914178938611578927", {
        "review_id": "review_mk", "version": 1,
        "submission": {"decision": "needs_evidence", "comment": "多污染物异常",
                       "data_impact": [
                           {"pollutant": "pm10", "decision": "partial_exclude",
                            "start": "2026-09-13T20:00:00", "end": "2026-09-13 23:00:00"},
                           {"pollutant": " NO2 ", "decision": "exclude",
                            "start": "2026-09-14 01:00:00", "end": "2026-09-14 04:00:00"},
                           {"pollutant": "O3", "decision": "keep",
                            "start": "2026-09-14 06:00:00", "end": "2026-09-14 07:00:00"},
                           {"decision": "partial_exclude",
                            "start": "2026-09-14 08:00:00", "end": "2026-09-14 09:00:00"},
                       ]},
    })

    doc = get_order("FA260914178938611578927")
    assert doc["index"]["mark_areas"] == [
        {"name": "PM10剔除区间", "pollutant": "PM10",
         "start": "2026-09-13 20:00:00", "end": "2026-09-13 23:00:00"},
        {"name": "NO2剔除区间", "pollutant": "NO2",
         "start": "2026-09-14 01:00:00", "end": "2026-09-14 04:00:00"},
        {"name": "剔除区间",
         "start": "2026-09-14 08:00:00", "end": "2026-09-14 09:00:00"},
    ]


def test_build_workbench_package_keeps_all_detected_pollutants():
    """工单文本识别到的多目标污染物整单进入 station_hour 源，工作台据此逐污染物拆图；
    单字符串形态回退为单元素清单，与旧行为一致。"""
    from app.services.jiangsu_work_order_review_ingest import build_workbench_package

    pack = {
        "work_order_code": "FA1",
        "summary": "PM10、NO2 数据异常",
        "station": {"station_name": "试点站", "station_code": "5006A"},
        "pollutants_detected_from_text": ["PM10", "NO2"],
        "evidence_time_window": {"start": "2026-09-14 20:00:00", "end": "2026-09-15 20:00:00"},
        "monitoring": {"station_hour_raw": []},
    }
    package = build_workbench_package(pack)
    hour_data = package["sources"]["station_hour"]["data"]
    assert hour_data["pollutant"] == "PM10"
    assert hour_data["pollutants"] == ["PM10", "NO2"]

    single = build_workbench_package({**pack, "pollutants_detected_from_text": "PM10"})
    assert single["sources"]["station_hour"]["data"]["pollutants"] == ["PM10"]


def test_build_workbench_package_keeps_five_minute_flags_and_coverage():
    from app.services.jiangsu_work_order_review_ingest import build_workbench_package

    pack = {
        "work_order_code": "FA5MIN",
        "pollutants_detected_from_text": ["NO", "NO2"],
        "station": {"station_name": "兴化人武部", "station_code": "3098A"},
        "evidence_time_window": {
            "start": "2026-11-06 00:00:00", "end": "2026-11-07 23:59:59",
            "fault_start_anchor": {"time": "2026-11-07 10:41:30"},
            "processing_end_anchor": {"time": "2026-11-07 11:03:40"},
        },
        "quality_control": {"history": {"data": [
            {"rStart": "2026-11-07 08:04:56", "endTime": "2026-11-07 08:18:29"},
            {"rStart": "2026-11-07 10:46:36", "endTime": "2026-11-07 11:01:08"},
        ]}},
        "monitoring": {"station_5minute_raw": {
            "success": True, "status": "success", "data_type": 0,
            "record_count": 576, "returned_records": 500,
            "metadata": {"time_range": ["2026-11-06 00:00:00", "2026-11-07 23:59:59"],
                         "failed_chunk_count": 0},
            "data": [
                {"timePoint": "2026-11-07T08:10:00", "no": "401(PS)", "nO2": "-2(PS)",
                 "nOx": "630(PS)", "pM2_5": "14", "pM10": "34", "co": "0.645"},
                {"timePoint": "2026-11-07T10:45:00", "no": "428(PZ)", "nO2": "12(PZ)"},
                {"timePoint": "2026-11-07T17:35:00", "no": "2", "nO2": "11"},
            ],
        }},
    }
    package = build_workbench_package(pack)
    source = package["sources"]["station_5minute"]
    assert source["status"] == "partial"
    assert source["record_count"] == 3
    points = source["data"]["points_by_pollutant"]
    assert points["NO"][0] == {"time": "2026-11-07T08:10:00", "value": 401, "flag": "PS"}
    assert "PM2.5" not in points
    assert "PM2.5" not in source["data"]["available_pollutants"]
    assert "PM2.5" not in source["data"]["units"]
    assert source["data"]["unsupported_pollutants"]["PM2.5"].startswith("PM2.5不提供5分钟数据")
    assert source["data"]["rows"][0]["pM2_5"] == "14"
    assert points["PM10"][0]["value"] == 34
    assert points["NOX"][0]["value"] == 630
    assert source["data"]["units"]["CO"] == "mg/m³"
    assert source["data"]["rows"][0]["no"] == "401(PS)"
    coverage = source["data"]["coverage"]
    assert coverage["platform_record_count"] == 576
    assert coverage["saved_record_count"] == 3
    assert coverage["missing_record_count"] == 573
    assert coverage["actual_end"] == "2026-11-07T17:35:00"
    assert coverage["query_end"] == "2026-11-07 23:59:59"
    assert coverage["default_window"] == ["2026-11-07 07:49:56", "2026-11-07 13:03:40"]
    assert "尾部 573 条未入包" in coverage["warning"]


def test_build_workbench_package_five_minute_missing_and_failed_are_explicit():
    from app.services.jiangsu_work_order_review_ingest import build_workbench_package

    missing = build_workbench_package({"work_order_code": "FA-NONE", "monitoring": {}})
    assert missing["sources"]["station_5minute"]["status"] == "skipped"
    failed = build_workbench_package({
        "work_order_code": "FA-FAIL",
        "monitoring": {"station_5minute_raw": {
            "success": False, "status": "failed", "record_count": 0, "data": [],
            "metadata": {"failed_chunk_count": 2},
        }},
    })
    source = failed["sources"]["station_5minute"]
    assert source["status"] == "failed"
    assert source["data"]["coverage"]["failed_chunk_count"] == 2
    assert source["data"]["points_by_pollutant"] == {}


def test_five_minute_window_is_independent_of_quality_control_order():
    from app.services.jiangsu_work_order_review_ingest import _five_minute_anchor_times

    tasks = [
        {"rStart": "2026-11-07 12:50:00", "endTime": "2026-11-07 13:20:00"},
        {"rStart": "2026-11-07 13:30:00", "endTime": "2026-11-07 14:00:00"},
        {"rStart": "2026-11-07 14:10:00", "endTime": "2026-11-07 14:40:00"},
    ]
    pack = {"evidence_time_window": {"processing_end_anchor": {"time": "2026-11-07 11:00:00"}},
            "quality_control": {"history": {"data": tasks}}}
    forward = _five_minute_anchor_times(pack)
    pack["quality_control"]["history"]["data"] = list(reversed(tasks))
    assert _five_minute_anchor_times(pack) == forward
    assert forward == ["2026-11-07 09:00:00", "2026-11-07 13:35:00"]


def test_update_evidence_source_preserves_all_review_metadata(isolated_registry):
    from app.services.jiangsu_work_order_review import update_evidence_source

    code = "FA5MIN-UPGRADE"
    save_evidence(_sample_package(code))
    attach_judgment(code, {"review_id": "review_keep", "version": 2,
                           "submission": {"decision": "reject", "comment": "保留人工结论",
                                          "data_impact": [{"pollutant": "PM10", "decision": "exclude",
                                                           "start": "2026-09-13 20:00:00", "end": "2026-09-13 21:00:00"}]}})
    record_operation(code, "archive", "已人工确认", {"username": "ops"})
    before = get_order(code)
    update_evidence_source(code, "station_5minute", {"status": "partial", "record_count": 1,
                                                     "data": {"rows": [{"no": "401(PS)"}]}})
    after = get_order(code)
    assert after["entry"]["status"] == before["entry"]["status"]
    for field in ("judgment", "operations", "mark_areas", "window"):
        assert after["index"][field] == before["index"][field]
    assert get_order_source(code, "station_5minute")["data"]["rows"][0]["no"] == "401(PS)"


def test_hourly_evidence_refresh_does_not_remove_existing_minute_source(isolated_registry):
    from app.services.jiangsu_work_order_review import update_evidence_source

    code = "FA5MIN-REFRESH"
    save_evidence(_sample_package(code))
    minute = {"status": "partial", "record_count": 1, "data": {"rows": [{"no": "401(PS)"}]}}
    update_evidence_source(code, "station_5minute", minute)
    save_evidence(_sample_package(code))
    assert get_order_source(code, "station_5minute")["data"] == minute["data"]
    failed = _sample_package(code)
    failed["sources"]["station_5minute"] = {"status": "failed", "record_count": 0, "data": {"rows": []}}
    save_evidence(failed)
    assert get_order(code)["index"]["sources"]["station_5minute"]["status"] == "failed"
    assert get_order_source(code, "station_5minute")["data"]["rows"] == []


def test_record_operation_feedback_keeps_status(isolated_registry):
    save_evidence(_sample_package())
    record_operation("FA260914178938611578927", "feedback", "建议复核采样流量", {"username": "ops"})

    doc = get_order("FA260914178938611578927")
    assert doc["entry"]["status"] == "待审核"
    assert doc["index"]["operations"][0]["label"] == "反馈"
    assert doc["index"]["operations"][0]["comment"] == "建议复核采样流量"


def test_record_operation_archive_without_review(isolated_registry):
    save_evidence(_sample_package())
    record_operation("FA260914178938611578927", "archive", "人工确认", {"username": "ops"})

    doc = get_order("FA260914178938611578927")
    assert doc["entry"]["status"] == "已归档"


def test_apply_human_decision_records_platform_sync_operation(isolated_registry, monkeypatch):
    from config.settings import settings
    from app.services.jiangsu_work_order_review import apply_human_decision
    from app.tools.jiangsu import platform_workflow as platform_module

    code = "FA260914178938611578927"
    save_evidence(_sample_package(code))
    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", True)

    calls = []

    async def fake_submit(work_order_code, *, action, approved, comment=""):
        calls.append((work_order_code, action, approved, comment))
        return {"status": "synced", "action": action, "work_order_code": code,
                "detail": "省中心审核节点通过，工单闭环", "at": "2026-10-23T12:00:00+08:00"}

    monkeypatch.setattr(platform_module, "submit_review_decision", fake_submit)

    apply_human_decision(
        {"subject_id": code},
        {"action": "confirm", "comment": "审核通过", "actor": {"username": "ops"}})

    assert calls == [(code, "confirm", True, "审核通过")]
    operations = get_order(code)["index"]["operations"]
    assert operations[-1]["action"] == "platform_sync"
    assert operations[-1]["label"] == "平台同步成功"
    assert operations[-1]["platform"]["sync_status"] == "synced"


def test_apply_human_decision_skips_platform_writeback_when_disabled(isolated_registry, monkeypatch):
    """开关关闭时 submit_review_decision 返回 disabled 描述符，证据包不落 platform_sync 操作。"""
    from app.services.jiangsu_work_order_review import apply_human_decision

    code = "FA260914178938611578927"
    save_evidence(_sample_package(code))

    apply_human_decision(
        {"subject_id": code},
        {"action": "confirm", "comment": "审核通过", "actor": {"username": "ops"}})

    operations = get_order(code)["index"]["operations"]
    assert [op["action"] for op in operations] == ["confirm"]


def test_apply_human_decision_skips_writeback_inside_running_loop(isolated_registry, monkeypatch):
    import asyncio

    from config.settings import settings
    from app.services.jiangsu_work_order_review import apply_human_decision
    from app.tools.jiangsu import platform_workflow as platform_module

    code = "FA260914178938611578927"
    save_evidence(_sample_package(code))
    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", True)

    async def unexpected_submit(*_args, **_kwargs):
        raise AssertionError("事件循环内不应触达平台写回")

    monkeypatch.setattr(platform_module, "submit_review_decision", unexpected_submit)

    async def drive():
        apply_human_decision(
            {"subject_id": code},
            {"action": "reject", "comment": "退回", "actor": {"username": "ops"}})

    asyncio.run(drive())

    operations = get_order(code)["index"]["operations"]
    assert [op["action"] for op in operations] == ["reject"]


def test_save_evidence_preserves_human_state(isolated_registry):
    save_evidence(_sample_package())
    record_operation("FA260914178938611578927", "archive", "人工确认", {"username": "ops"})

    # 重新采集证据不回退人工状态
    entry = save_evidence(_sample_package())
    assert entry["status"] == "已归档"
    doc = get_order("FA260914178938611578927")
    assert doc["index"]["operations"][0]["label"] == "归档"


def test_evidence_resources_declared_for_session(isolated_registry):
    from pathlib import Path

    from app.tools.jiangsu.fault_diagnosis import JiangsuReviewEvidenceTool

    folder = isolated_registry / "jiangsu_work_order_reviews" / "orders" / "abc"
    folder.mkdir(parents=True)
    index_path = folder / "index.json"
    index_path.write_text("{}", encoding="utf-8")
    entry = {"working_order_code": "FA1", "status": "待审核", "index_path": str(index_path),
             "source_files": {"station_hour": str(index_path)},
             "source_counts": {"station_hour": 3}}

    resources = JiangsuReviewEvidenceTool._evidence_resources(entry)

    assert resources[0]["kind"] == "data"
    assert resources[0]["group_key"] == "review_evidence:FA1"
    assert resources[0]["tool_name"] == "jiangsu_fetch_review_evidence"
    assert resources[1]["parent_key"] == "primary:data"
    assert resources[1]["relation"] == "attachment"
    # 发布管道按进程 CWD 解析相对路径会指向错误位置，声明必须携带绝对路径
    for resource in resources:
        assert Path(resource["locator"]["path"]).is_absolute()


def test_list_orders_filters_by_date_range(isolated_registry):
    from datetime import date

    save_evidence(_sample_package())  # window_start = 2026-09-13 19:41:00

    assert list_orders(start_date="2026-09-13", end_date="2026-09-13")["total"] == 1
    assert list_orders(start_date="2026-09-01", end_date="2026-09-30")["total"] == 1
    assert list_orders(start_date="2026-09-14")["total"] == 0
    assert list_orders(end_date="2026-09-12")["total"] == 0

    # 缺故障窗口的工单回退取证时间（存证当天）参与日期过滤
    package = _sample_package(code="FA-NO-WINDOW")
    package.pop("window")
    save_evidence(package)
    today = date.today().isoformat()
    assert list_orders(start_date="2026-09-13", end_date="2026-09-13")["total"] == 1
    assert list_orders(start_date=today, end_date=today)["total"] == 1


def _declaration_package(code, remark):
    package = _sample_package(code)
    package["sources"]["work_order"] = {
        "status": "success", "record_count": 1,
        "data": {"details": [{"submitRemark": remark}]},
    }
    return package


def _exclusion_submission(code, decision="approve"):
    return {
        "subject_id": code, "category": "工单审核", "decision": decision,
        "data_impact": [{"pollutant": "CO", "decision": "partial_exclude",
                         "start": "2026-10-23T15:00:00+08:00", "end": "2026-10-24T11:00:00+08:00"}],
    }


def test_approve_with_exclusion_blocked_by_no_removal_declaration(isolated_registry):
    """工单申报"无异常数据剔除"而 AI 建议剔除：approve 是结论性不一致，必须拒绝提交。"""
    code = "FA260914178938611578927"
    save_evidence(_declaration_package(code, "已校准，数据已恢复正常，无异常数据剔除"))

    with pytest.raises(ValueError, match="reject"):
        validate_removal_declaration_consistency(_exclusion_submission(code))


def test_declaration_check_variants(isolated_registry):
    code = "FA260914178938611578927"

    # 申报无剔除 + 建议退回：一致，放行
    save_evidence(_declaration_package(code, "现场已处理，无异常数据剔除"))
    validate_removal_declaration_consistency(_exclusion_submission(code, decision="reject"))

    # 通过且无剔除建议：无冲突
    validate_removal_declaration_consistency({
        "subject_id": code, "category": "工单审核", "decision": "approve",
        "data_impact": [{"pollutant": "CO", "decision": "keep"}],
    })

    # 申报为"申请剔除 X 至 Y"而非"无剔除"声明：区间比对交由 SOP 语义约束，不拦截
    save_evidence(_declaration_package(code, "故障期间数据已申请剔除10月23日15时至17时"))
    validate_removal_declaration_consistency(_exclusion_submission(code))


def test_declaration_check_skipped_without_evidence_pack(isolated_registry):
    """证据包尚未采集（如非江苏链路的工单审核）：不拦截，交由 SOP 语义约束。"""
    validate_removal_declaration_consistency(
        _exclusion_submission("FA-NEVER-COLLECTED"))
