from pathlib import Path

from app.services.ops_audit.rule_engine import run_rule_engine
from app.services.ops_audit.semantic import reviewer


def test_build_semantic_review_results_is_generated(monkeypatch) -> None:
    monkeypatch.setattr(
        reviewer,
        "review_remark_semantic",
        lambda remark, context=None: {
            "is_complete": False,
            "has_cause": False,
            "has_action": False,
            "has_result": False,
            "suggestion": "补充原因、措施和结果。",
            "confidence": 0.6,
            "remark": remark,
        },
    )
    monkeypatch.setattr(
        reviewer,
        "review_attachment_quality",
        lambda attachment_path, attachment_type: {
            "is_complete": True,
            "issues": [],
            "suggestion": "",
            "confidence": 0.8,
            "source": attachment_path,
            "attachment_type": attachment_type,
            "mode": "metadata",
        },
    )

    dataset = {
        "orders": [
            {
                "WORKINGORDERCODE": "WO-SEM",
                "STATIONID": "1007",
                "DEVICEID": "DEV-1",
                "CREATETIME": "2026-05-20 10:00:00",
                "FINISHTIME": "2026-05-20 11:00:00",
                "DDWORKINGORDERTYPE": "Check",
                "DDWORKINGORDERSTATUS": "Finish",
                "CURRENTWORKFLOWSTATUS": "Finish",
                "MAINTENANCETYPE": "Week",
                "ORDERTITLE": "计划任务单",
                "ORDERCONTENT": "计划任务单",
            }
        ],
        "details": [
            {"WORKINGORDERCODE": "WO-SEM", "PROCESSSTEP": "CreateOrder", "SUBMITREMARK": ""},
            {"WORKINGORDERCODE": "WO-SEM", "PROCESSSTEP": "CheckOrder", "SUBMITREMARK": ""},
        ],
        "rf_forms": {},
        "attachments": [],
        "wo_commonfile": [],
        "device_history": {"orders": [], "rf_forms": {}},
    }

    result = run_rule_engine(dataset, output_dir=Path("backend/backend_data_registry/memory/ops/audit"), persist_outputs=False)

    assert result["semantic_review_result_count"] >= 1
    assert "semantic_review_results" in result
