from __future__ import annotations

import json
from pathlib import Path

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
