import json

import pytest

from app.services import jiangsu_work_order_review as review_service


def test_review_evidence_expands_same_city_resource_without_mutating_agent_pack(tmp_path, monkeypatch):
    raw_path = tmp_path / "same_city.json"
    datasets = {key: {"data": [{"timePoint": "2026-09-06T08:00:00", "nO2": 12}], "record_count": 1}
                for key in ("station_hour_raw", "station_hour_audited")}
    raw_path.write_text(json.dumps(datasets))
    pack = {"same_city_monitoring": {"raw_resource": {"path": str(raw_path)},
            "station_hour_raw": {"record_count": 1}}}
    pack_path = tmp_path / "evidence.json"
    pack_path.write_text(json.dumps(pack))
    monkeypatch.setattr(review_service, "load_review", lambda _: {"evidence_pack_path": str(pack_path)})
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    loaded = review_service.load_review_evidence("test")
    assert loaded["same_city_monitoring"]["station_hour_raw"]["data"][0]["nO2"] == 12
    assert json.loads(pack_path.read_text()) == pack
    raw_path.unlink()
    with pytest.raises(ValueError, match="无法读取"):
        review_service.load_review_evidence("test")


def test_review_evidence_rejects_same_city_resource_outside_event(tmp_path, monkeypatch):
    pack_path = tmp_path / "evidence.json"
    pack_path.write_text(json.dumps({"same_city_monitoring": {"raw_resource": {"path": str(tmp_path.parent / "other.json")}}}))
    monkeypatch.setattr(review_service, "load_review", lambda _: {"evidence_pack_path": str(pack_path)})
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    with pytest.raises(ValueError, match="当前证据包目录"):
        review_service.load_review_evidence("test")


def _base_review():
    return {
        "event_id": "evt-1",
        "sop_id": "SOP-01",
        "work_order_code": "FA260901001",
        "station": {"station_code": "3001A", "station_name": "江宁九龙湖"},
        "pollutants": ["NO"],
        "gates": {
            "M1": {"status": "pass", "basis": "站点、设备和污染物一致"},
            "M2": {"status": "pass", "basis": "质控结果不合格"},
            "M3": {"status": "pass", "basis": "处置动作为校准"},
            "M4": {"status": "pass", "basis": "复测合格"},
            "M5": {"status": "pass", "basis": "影响区间明确"},
            "M6": {"status": "pass", "basis": "标识边界一致"},
            "M7": {"status": "pass", "basis": "流程到省中心审核"},
            "M8": {"status": "pass", "basis": "证据包已固化"},
        },
        "data_impact": [{
            "pollutant": "NO",
            "granularity": "hour",
            "start": "2026-09-01T00:20:00+08:00",
            "end": "2026-09-01T01:00:00+08:00",
            "decision": "partial_exclude",
        }],
        "exclusion_intervals": [{
            "data_impact_index": 0,
            "boundary_sources": ["质控任务结束时间", "复测合格时间"],
            "reasonableness_check": {
                "status": "pass",
                "basis": "异常区间与质控失败和复测闭环一致",
            },
        }],
        "work_order_decision": "approve",
        "review_comment": "核心闭环充分，建议通过并确认剔除候选。",
    }


@pytest.mark.parametrize("decision", ["keep", "partial_exclude", "exclude", "missing_no_delete"])
def test_minutes_cannot_be_submitted_as_review_targets(decision):
    with pytest.raises(ValueError, match="仅允许小时数据审核"):
        review_service._normalise_data_impact([{"decision": decision, "granularity": "5min"}])


def test_hour_is_the_default_review_granularity():
    assert review_service._normalise_data_impact([{"decision": "keep"}])[0]["granularity"] == "hour"


def test_confirm_revalidates_stored_minute_intervals(monkeypatch):
    review = _base_review()
    review["status"] = "pending_review"
    review["exclusion_required"] = True
    review["exclusion_intervals"] = [{"granularity": "5min"}]
    monkeypatch.setattr(review_service, "load_review", lambda _: review)
    with pytest.raises(ValueError, match="仅允许小时数据剔除"):
        review_service.mark_human_review("test", action="confirm", payload={}, actor={})


def test_review_submission_requires_exclusion_intervals_for_partial_exclude(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = _base_review()
    payload["exclusion_intervals"] = []

    with pytest.raises(ValueError, match="需要数据剔除时必须填写"):
        review_service.submit_agent_review(payload)


def test_review_submission_requires_explicit_time_for_exclusion_impact(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = _base_review()
    payload["data_impact"][0].pop("start")

    with pytest.raises(ValueError, match="建议剔除时必须填写明确 start/end"):
        review_service.submit_agent_review(payload)


def test_review_submission_requires_interval_for_each_exclusion_impact(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = _base_review()
    payload["data_impact"].append({
        "pollutant": "NO2",
        "granularity": "hour",
        "start": "2026-09-01T02:00:00+08:00",
        "end": "2026-09-01T03:00:00+08:00",
        "decision": "exclude",
    })

    with pytest.raises(ValueError, match="每个建议剔除的 data_impact 都必须提供确认区间，缺少索引：1"):
        review_service.submit_agent_review(payload)


def test_review_submission_requires_explicit_sop_id(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = _base_review()
    payload.pop("sop_id")

    with pytest.raises(ValueError, match="sop_id 必须为 SOP-01、SOP-02 或 SOP-03"):
        review_service.submit_agent_review(payload)


def test_review_submission_preserves_agent_gate_keys_without_sop_fill(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = _base_review()
    payload["gates"] = {
        "M1": {"status": "pass", "basis": "对象一致", "scope": "core"},
        "M2": {"status": "uncertain", "missing_evidence": ["缺少质控曲线"], "scope": "supporting"},
    }
    payload["work_order_decision"] = "needs_evidence"

    review = review_service.submit_agent_review(payload)

    assert set(review["gates"]) == {"M1", "M2"}
    assert review["gates"]["M2"]["missing_evidence"] == ["缺少质控曲线"]
    assert review["gates"]["M2"]["scope"] == "supporting"
    assert "M8" not in review["gates"]
    assert "M8_evidence_retention" not in review["gates"]


def test_review_submission_only_warns_on_uncertain_core_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = _base_review()
    payload["data_impact"] = []
    payload["exclusion_intervals"] = []
    payload["gates"] = {
        "M1": {"status": "pass", "basis": "对象一致", "scope": "core"},
        "M2": {"status": "uncertain", "missing_evidence": ["缺少同城对比"], "scope": "supporting"},
        "M3": {"status": "fail", "missing_evidence": ["缺少设备告警"], "scope": "rebuttal"},
    }
    payload["work_order_decision"] = "approve"

    review = review_service.submit_agent_review(payload)

    assert review["gates"]["M2"]["scope"] == "supporting"
    assert review["gates"]["M3"]["scope"] == "rebuttal"
    assert review["audit_warnings"] == []


def test_human_confirm_marks_exclusion_intervals_confirmed(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    review = review_service.submit_agent_review(_base_review())

    assert review["review_id"].startswith("jsworev_review_")
    assert review["exclusion_required"] is True
    interval = review["exclusion_intervals"][0]
    assert interval["data_impact_index"] == 0
    assert interval["pollutant"] == "NO"
    assert interval["start"] == "2026-09-01T00:20:00+08:00"
    assert interval["end"] == "2026-09-01T01:00:00+08:00"

    archived = review_service.mark_human_review(
        review["review_id"],
        action="confirm",
        actor={"user_id": "u1", "username": "auditor"},
        payload={
            "final_work_order_decision": "approve",
            "data_impact": review["data_impact"],
            "exclusion_required": True,
            "exclusion_intervals": review["exclusion_intervals"],
            "review_comment": "人工确认区间合理。",
        },
    )

    assert archived["status"] == "archived"
    assert archived["human_confirmed"] is True
    assert archived["final_exclusion_intervals"][0]["human_confirmed"] is True


def test_load_review_evidence_reads_pack_inside_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    evidence_path = tmp_path / "work_order_review_events" / "case-1" / "review_evidence_pack.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps({"sop_id": "SOP-01", "work_order_code": "FA260901001"}, ensure_ascii=False),
        encoding="utf-8",
    )
    payload = _base_review()
    payload["evidence_pack_path"] = str(evidence_path)
    review = review_service.submit_agent_review(payload)

    evidence = review_service.load_review_evidence(review["review_id"])

    assert evidence == {"sop_id": "SOP-01", "work_order_code": "FA260901001"}


def test_sop02_review_submission_uses_env_fields_and_e_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = {
        "event_id": "evt-env-1",
        "sop_id": "SOP-02",
        "work_order_code": "FA260903178839640293640",
        "station": {"station_code": "3003A", "station_name": "江阴虹桥邮政"},
        "device_id": "1762",
        "device_type": "PM10 分析仪",
        "pollutants": ["PM10"],
        "event_type": "low",
        "failure_fact": {"status": "suspected", "parameter_or_alarm": "平台抬放异常"},
        "disposal": {"action": "调整平台抬放后重启", "cause_action_match": True},
        "recovery": {"status": "not_verified", "verification": "未取得恢复稳定窗口"},
        "neighbor_comparison": "未查询：同城小时数据为空",
        "gates": {
            "E1": {"status": "pass", "basis": "站点、设备和 PM10 一致"},
            "E2": {"status": "pass", "basis": "工单称 PM10 偏低，原始曲线待核验"},
            "E3": {"status": "uncertain", "missing_evidence": ["平台抬放状态历史"]},
            "E4": {"status": "uncertain", "missing_evidence": ["同城站对比"]},
            "E5": {"status": "pass", "basis": "处置动作针对平台抬放"},
            "E6": {"status": "uncertain", "missing_evidence": ["处置后稳定期"]},
            "E7": {"status": "uncertain", "missing_evidence": ["审核标识"]},
            "E8": {"status": "uncertain", "missing_evidence": ["边界来源"]},
            "E9": {"status": "uncertain", "missing_evidence": ["流程闭环"]},
        },
        "data_impact": [{
            "pollutant": "PM10",
            "device_id": "1762",
            "granularity": "hour",
            "status": "uncertain",
            "decision": "needs_evidence",
        }],
        "work_order_decision": "needs_evidence",
        "review_comment": "平台抬放异常与 PM10 偏低相关，但缺少边界和恢复证据。",
    }

    review = review_service.submit_agent_review(payload)

    assert review["review_id"].startswith("jsworev_review_")
    assert review["sop_id"] == "SOP-02"
    assert "env_category" not in review
    assert review["event_type"] == "low"
    assert review["recovery"]["status"] == "not_verified"
    assert "E1" in review["gates"]
    assert "E9" in review["gates"]
    assert "M1" not in review["gates"]
    assert review["data_impact"][0]["decision"] == "needs_evidence"


def test_sop03_review_submission_uses_transmission_fields_and_t_gates(tmp_path, monkeypatch):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    payload = {
        "event_id": "evt-transmission-1",
        "sop_id": "SOP-03",
        "work_order_code": "FA260903TRAN",
        "station": {"station_code": "3008A", "station_name": "盱眙泵站路"},
        "device_id": "2395",
        "device_type": "SO2 分析仪",
        "pollutants": ["SO2"],
        "transmission_status": "not_uploaded",
        "event_type": "not_uploaded",
        "failure_fact": {"status": "suspected", "description": "平台无数据上传"},
        "transmission": {
            "local_data": "未取得本地缓存",
            "platform_receipt": "未取得平台接收明细",
            "retransmission": "未取得补传回执",
        },
        "gates": {
            "T1": {"status": "pass", "basis": "站点和 SO2 设备一致"},
            "T2": {"status": "uncertain", "missing_evidence": ["设备本地运行状态"], "scope": "core"},
            "T3": {"status": "uncertain", "missing_evidence": ["本地缓存"], "scope": "core"},
            "T4": {"status": "uncertain", "missing_evidence": ["平台接收记录"], "scope": "core"},
            "T5": {"status": "uncertain", "missing_evidence": ["补传回执"], "scope": "core"},
            "T6": {"status": "uncertain", "missing_evidence": ["时间戳连续性"], "scope": "core"},
            "T7": {"status": "uncertain", "missing_evidence": ["缺失分类"], "scope": "core"},
            "T8": {"status": "pass", "basis": "详单证据已固化"},
        },
        "data_impact": [{
            "station_code": "3008A",
            "device_id": "2395",
            "pollutant": "SO2",
            "granularity": "hour",
            "status": "uncertain",
            "decision": "needs_evidence",
        }],
        "work_order_decision": "needs_evidence",
        "review_comment": "无数据上传需要补充本地数据、平台接收和补传证据。",
    }

    review = review_service.submit_agent_review(payload)
    visual = review_service.create_review_visual(review)

    assert review["sop_id"] == "SOP-03"
    assert "transmission_category" not in review
    assert review["transmission_status"] == "not_uploaded"
    assert review["transmission"]["platform_receipt"] == "未取得平台接收明细"
    assert "T1" in review["gates"]
    assert "E1" not in review["gates"]
    assert visual["title"].startswith("传输缺失工单审核")


def test_review_visual_id_keeps_full_review_id_for_unique_chart_spec():
    first = _base_review()
    first["review_id"] = "exec_jiangsu_fault_work_order_review_20260903_183049_c2a1d046"
    second = _base_review()
    second["review_id"] = "exec_jiangsu_fault_work_order_review_20260903_183639_5ea338da"

    first_visual = review_service.create_review_visual(first)
    second_visual = review_service.create_review_visual(second)

    assert first_visual["id"] != second_visual["id"]
    assert first_visual["id"].endswith(first["review_id"])
    assert second_visual["id"].endswith(second["review_id"])
