from app.services.ops_audit.rules import attachment_rules
from app.services.ops_audit.semantic import reviewer


def test_station_maintenance_candidate_prioritizes_matching_form_attachments():
    issues = []
    unrelated = [
        {
            "filename": f"流量检查照片-{index}.jpg",
            "typecode": "RF_Q_GaseousFlowCheck",
            "filepath": f"/WebFiles/NewFiles/Check/RF_Q_GaseousFlowCheck/{index}.jpg",
        }
        for index in range(25)
    ]
    station_maintain = [
        {
            "filename": "仪器显示数据及时间-1.jpg",
            "typecode": "RF_M_StationDeviceMaintain",
            "filepath": "/WebFiles/NewFiles/Check/RF_M_StationDeviceMaintain/1.jpg",
        },
        {
            "filename": "数采显示数据及时间.jpg",
            "typecode": "RF_M_StationDeviceMaintain",
            "filepath": "/WebFiles/NewFiles/Check/RF_M_StationDeviceMaintain/2.jpg",
        },
        {
            "filename": "空调滤网及仪器防尘网清洗.jpg",
            "typecode": "RF_M_StationDeviceMaintain",
            "filepath": "/WebFiles/NewFiles/Check/RF_M_StationDeviceMaintain/3.jpg",
        },
    ]

    attachment_rules.check_attachment_requirements(
        {
            "WORKINGORDERCODE": "CH2605191779157293812",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Month",
        },
        [("RF_M_STATIONDEVICEMAINTAIN", {})],
        unrelated + station_maintain,
        [],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING"]
    assert len(matched) == 1
    evidence = __import__("json").loads(matched[0].evidence)
    filenames = [item["name"] for item in evidence["sample_attachments"]]
    assert "仪器显示数据及时间-1.jpg" in filenames
    assert "数采显示数据及时间.jpg" in filenames
    assert "空调滤网及仪器防尘网清洗.jpg" in filenames
    assert "流量检查照片-0.jpg" not in filenames


def test_station_maintenance_photos_emit_semantic_candidate():
    issues = []
    attachment_rules.check_attachment_requirements(
        {
            "WORKINGORDERCODE": "CH2605151778803777982",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Month",
        },
        [("RF_M_STATIONDEVICEMAINTAIN", {})],
        [
            {"filename": "时间一致性 (1).jpg"},
            {"filename": "检查颗粒物 (1).jpg"},
            {"filename": "过滤网清洗.jpg"},
        ],
        [],
        issues,
    )

    matched = [issue for issue in issues if issue.rule_id == "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING"]
    assert len(matched) == 1
    assert "文件名语义判断" in matched[0].message


def test_station_maintenance_photos_emit_candidate_for_mobile_or_not_applicable_maintenance():
    issues = []
    attachment_rules.check_attachment_requirements(
        {
            "WORKINGORDERCODE": "WO-MOBILE-STATION",
            "DDWORKINGORDERTYPE": "Check",
            "MAINTENANCETYPE": "Month",
        },
        [
            (
                "RF_M_STATIONDEVICEMAINTAIN",
                {
                    "WORKINGORDERCODE": "WO-MOBILE-STATION",
                    "REMARK": "本工单为流动监测车月度开机维护记录，跟常规站点月度工单维护内容不完全一样，过滤网清洗无需每月执行。",
                },
            )
        ],
        [],
        [],
        issues,
    )

    assert any(issue.rule_id == "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING" for issue in issues)


def test_station_maintenance_filename_batch_clears_covered_photos(monkeypatch):
    captured_payload = {}

    def fake_llm(_prompt, payload, **_kwargs):
        captured_payload.update(__import__("json").loads(payload))
        return {
            "results": [
                {
                    "working_order_code": "WO-A",
                    "covered_types": {
                        "particle_clock_photo": ["检查颗粒物 (1).jpg"],
                        "data_logger_clock_photo": ["时间一致性 (1).jpg"],
                        "filter_cleaning_photo": ["过滤网清洗.jpg"],
                    },
                    "missing_types": [],
                    "uncertain_types": [],
                    "evidence": [],
                    "confidence": 0.9,
                }
            ]
        }

    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        fake_llm,
    )

    results = reviewer.build_semantic_review_results(_audit_with_attachment_candidate("WO-A"), {})

    assert results["results"][0]["judgment"] == "cleared"
    assert results["results"][0]["can_promote_to_final_issue"] is False
    assert captured_payload["items"][0]["type_definitions"]["particle_clock_photo"]


def test_station_maintenance_filename_batch_sends_rf_remarks_and_clears_exemptions(monkeypatch):
    captured_payload = {}

    def fake_llm(_prompt, payload, **_kwargs):
        captured_payload.update(__import__("json").loads(payload))
        return {
            "results": [
                {
                    "working_order_code": "WO-EXEMPT",
                    "is_exempt": True,
                    "exemption_reason": "RF备注说明为流动监测车，过滤网清洗无需每月执行。",
                    "covered_types": {},
                    "missing_types": ["particle_clock_photo", "data_logger_clock_photo", "filter_cleaning_photo"],
                    "uncertain_types": [],
                    "evidence": [],
                    "confidence": 0.88,
                }
            ]
        }

    monkeypatch.setattr(reviewer, "_call_semantic_llm_json", fake_llm)

    results = reviewer.build_semantic_review_results(
        _audit_with_attachment_candidate("WO-EXEMPT"),
        {
            "rf_forms": {
                "RF_M_STATIONDEVICEMAINTAIN": [
                    {
                        "WORKINGORDERCODE": "WO-EXEMPT",
                        "REMARK": "本工单为流动监测车月度开机维护记录，跟常规站点月度工单维护内容不完全一样，过滤网清洗无需每月执行。",
                    }
                ]
            }
        },
    )

    item = captured_payload["items"][0]
    assert "流动监测车" in item["rf_remarks"]
    assert item["exemption_review_required"] is True
    assert results["results"][0]["judgment"] == "cleared"
    assert results["results"][0]["can_promote_to_final_issue"] is False


def test_station_maintenance_filename_batch_confirms_missing_photos(monkeypatch):
    monkeypatch.setattr(
        reviewer,
        "_call_semantic_llm_json",
        lambda *args, **kwargs: {
            "results": [
                {
                    "working_order_code": "WO-B",
                    "covered_types": {"filter_cleaning_photo": ["过滤网清洗.jpg"]},
                    "missing_types": ["particle_clock_photo", "data_logger_clock_photo"],
                    "uncertain_types": [],
                    "evidence": [],
                    "confidence": 0.91,
                }
            ]
        },
    )

    results = reviewer.build_semantic_review_results(_audit_with_attachment_candidate("WO-B"), {})

    assert results["results"][0]["judgment"] == "confirmed_issue"
    assert results["results"][0]["supported_rule_ids"] == ["ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING"]
    assert "particle_clock_photo" in results["results"][0]["conclusion"]


def _audit_with_attachment_candidate(code: str) -> dict:
    evidence = {
        "working_order_code": code,
        "requirement_id": "MONTH_STATION_MAINTAIN_PHOTOS",
        "requirement_name": "站点设备维护现场照片",
        "required_types": ["particle_clock_photo", "data_logger_clock_photo", "filter_cleaning_photo"],
        "sample_attachments": [
            {"name": "时间一致性 (1).jpg"},
            {"name": "检查颗粒物 (1).jpg"},
            {"name": "过滤网清洗.jpg"},
        ],
    }
    issue = {
        "rule_id": "ATTACHMENT_STATION_MAINTAIN_PHOTO_SEMANTIC_MISSING",
        "severity": "中",
        "assessment": "candidate_issue",
        "field": "attachment.MONTH_STATION_MAINTAIN_PHOTOS.filename_semantics",
        "message": "站点设备维护现场照片需通过文件名语义判断是否覆盖必需照片类型",
        "evidence": __import__("json").dumps(evidence, ensure_ascii=False),
    }
    return {
        "records": [
            {
                "working_order_code": code,
                "station_id": "1",
                "order_type": "Check",
                "maintenance_type": "Month",
                "finish_time": "2026-05-27 10:00:00",
                "audit_level": "需语义复核",
                "score": 80,
                "attachment_count": 3,
                "workflow_steps": [],
                "rf_tables": ["RF_M_STATIONDEVICEMAINTAIN"],
                "scoring_issues": [issue],
            }
        ]
    }
