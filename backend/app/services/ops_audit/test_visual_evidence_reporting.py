from __future__ import annotations

import json
from pathlib import Path

from app.services.ops_audit import rule_engine
from app.services.ops_audit.final_issue_list import build_final_issue_list
from app.services.ops_audit.rule_engine import run_rule_engine
from app.services.ops_audit.visual_evidence import archive_visual_evidence


def _visual_issue(rule_id: str, evidence: dict) -> dict:
    return {
        "rule_id": rule_id,
        "category": "附件质量问题",
        "field": f"attachment.vision.{rule_id}",
        "message": "视觉证据待复核",
        "evidence": json.dumps(evidence, ensure_ascii=False),
    }


def test_archive_visual_evidence_keeps_all_images_and_reuses_duplicate_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    photos = []
    for index in range(4):
        photo = source_dir / f"curve-{index}.jpg"
        photo.write_bytes(f"image-{index}".encode())
        photos.append(photo)

    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "scoring_issues": [
                    _visual_issue(
                        "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
                        {"source": str(photos[0]), "needs_visual_review": True},
                    ),
                    _visual_issue(
                        "ATTACHMENT_MULTIPOINT_GRADIENT_REVIEW",
                        {
                            "needs_manual_review": True,
                            "reviewed_images": [
                                {
                                    "attachment_filename": photo.name,
                                    "attachment_local_path": str(photo),
                                }
                                for photo in photos
                            ],
                        },
                    ),
                ],
            }
        ]
    }

    result = archive_visual_evidence(audit, tmp_path / "output")

    assert result["success_count"] == 5
    assert result["unique_file_count"] == 4
    assert Path(result["manifest_path"]).is_file()
    issues = audit["records"][0]["scoring_issues"]
    assert len(json.loads(issues[0]["evidence"])["evidence_images"]) == 1
    assert len(json.loads(issues[1]["evidence"])["evidence_images"]) == 4
    assert all(
        Path(item["local_path"]).is_file()
        for item in result["items"]
        if item["status"] == "success"
    )


def test_archive_visual_evidence_resolves_webfiles_from_attachment_root(
    tmp_path: Path, monkeypatch
) -> None:
    attachment = tmp_path / "attachments" / "WebFiles" / "photo.jpg"
    attachment.parent.mkdir(parents=True)
    attachment.write_bytes(b"root-image")
    monkeypatch.setenv("OPS_ATTACHMENT_ROOT", str(tmp_path / "attachments"))
    audit = {
        "records": [
            {
                "working_order_code": "WO-ROOT",
                "scoring_issues": [
                    _visual_issue(
                        "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
                        {"source": "/WebFiles/photo.jpg", "needs_visual_review": True},
                    )
                ],
            }
        ]
    }

    result = archive_visual_evidence(audit, tmp_path / "output")

    assert result["success_count"] == 1
    assert Path(result["items"][0]["local_path"]).read_bytes() == b"root-image"


def test_archive_visual_evidence_downloads_remote_source(tmp_path: Path, monkeypatch) -> None:
    class Response:
        content = b"remote-image"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setenv("OPS_ATTACHMENT_BASE_URL", "https://attachments.example")
    monkeypatch.setattr(
        "app.services.ops_audit.visual_evidence.requests.get",
        lambda url, timeout: Response(),
    )
    audit = {
        "records": [
            {
                "working_order_code": "WO-REMOTE",
                "scoring_issues": [
                    _visual_issue(
                        "ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH",
                        {"source": "/WebFiles/remote.jpg", "needs_visual_review": True},
                    )
                ],
            }
        ]
    }

    result = archive_visual_evidence(audit, tmp_path / "output")

    assert result["success_count"] == 1
    assert Path(result["items"][0]["local_path"]).read_bytes() == b"remote-image"


def test_archive_visual_evidence_records_failure_without_aborting(tmp_path: Path) -> None:
    audit = {
        "records": [
            {
                "working_order_code": "WO-MISSING",
                "scoring_issues": [
                    _visual_issue(
                        "ATTACHMENT_FLOW_VISUAL_ERROR",
                        {"source": "/missing/photo.jpg"},
                    )
                ],
            }
        ]
    }

    result = archive_visual_evidence(audit, tmp_path / "output")

    assert result["failed_count"] == 1
    evidence = json.loads(audit["records"][0]["scoring_issues"][0]["evidence"])
    assert evidence["evidence_images"][0]["status"] == "failed"
    assert evidence["evidence_images"][0]["error"]


def test_final_issue_list_exposes_archived_visual_evidence() -> None:
    evidence_images = [
        {
            "source": "/WebFiles/photo.jpg",
            "filename": "photo.jpg",
            "status": "success",
            "local_path": "/audit/visual_evidence/WO-1/RULE/photo.jpg",
            "relative_path": "visual_evidence/WO-1/RULE/photo.jpg",
        }
    ]
    evidence = {
        "working_order_code": "WO-1",
        "rf_table": "RF_TW_PmFlowCalibrate",
        "vision_confidence": 0.95,
        "comparisons": [
            {
                "field": "Prev_S",
                "visual_value": 15.8,
                "visual_unit": "L/min",
                "form_value": 16.7,
                "status": "mismatch",
            }
        ],
        "evidence_images": evidence_images,
    }
    audit = {
        "records": [
            {
                "working_order_code": "WO-1",
                "scoring_issues": [
                    _visual_issue(
                        "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
                        evidence,
                    )
                ],
            }
        ]
    }

    result = build_final_issue_list(audit)

    assert result["items"][0]["evidence_images"] == evidence_images


def test_rule_engine_persists_and_returns_visual_evidence_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    photo = tmp_path / "source.jpg"
    photo.write_bytes(b"visual")
    issue = _visual_issue(
        "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
        {
            "source": str(photo),
            "needs_visual_review": True,
            "vision_confidence": 0.95,
            "comparisons": [
                {
                    "field": "Prev_S",
                    "visual_value": 15.8,
                    "visual_unit": "L/min",
                    "form_value": 16.7,
                    "status": "mismatch",
                }
            ],
        },
    )
    audit = {
        "audit_info": {"generated_at": "2026-07-14", "order_count": 1},
        "summary": {},
        "records": [
            {
                "working_order_code": "WO-ENGINE",
                "scoring_issues": [issue],
                "deterministic_issues": [issue],
            }
        ],
    }
    monkeypatch.setattr(rule_engine, "audit_dataset", lambda *args, **kwargs: audit)
    monkeypatch.setattr(rule_engine, "build_semantic_candidates", lambda value: {"candidate_count": 0})
    monkeypatch.setattr(rule_engine, "build_semantic_review_tasks", lambda value: {"task_count": 0})
    monkeypatch.setattr(
        rule_engine,
        "build_semantic_review_results",
        lambda current_audit, dataset: {"result_count": 0, "results": []},
    )

    result = run_rule_engine({}, output_dir=tmp_path / "output", persist_outputs=True)

    assert Path(result["visual_evidence_manifest_path"]).is_file()
    assert result["visual_evidence_success_count"] == 1
    persisted = json.loads(Path(result["audit_result_path"]).read_text(encoding="utf-8"))
    persisted_evidence = json.loads(
        persisted["records"][0]["scoring_issues"][0]["evidence"]
    )
    assert Path(persisted_evidence["evidence_images"][0]["local_path"]).is_file()
