import json
from pathlib import Path

import pytest

from app.api import jiangsu_work_order_review_routes as review_routes
from app.auth.models import CurrentUser
from app.services import jiangsu_work_order_review as review_service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_name", "content_type", "expected_media_type", "image_bytes"),
    [
        ("现场照片.jpg", "application/jpg", "image/jpeg", b"\xff\xd8\xff\xe0fake-image-data"),
        ("趋势截图.png", "application/png", "image/png", b"\x89PNG\r\n\x1a\nfake-image-data"),
    ],
)
async def test_review_evidence_exposes_attachment_content_urls_and_inline_file_response(
    tmp_path,
    monkeypatch,
    file_name,
    content_type,
    expected_media_type,
    image_bytes,
):
    monkeypatch.setattr(review_service, "get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(review_routes, "get_data_registry", lambda: tmp_path)

    image_path = tmp_path / "work_order_review_attachments" / "FA260901001" / file_name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)

    evidence_path = tmp_path / "work_order_review_events" / "case-1" / "review_evidence_pack.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {
                "sop_id": "SOP-01",
                "work_order_code": "FA260901001",
                "work_order": {
                    "detail": {
                        "data": [
                            {
                                "attachments": [
                                    {
                                        "fileName": file_name,
                                        "local_path": str(image_path),
                                        "content_type": content_type,
                                    }
                                ]
                            }
                        ]
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    review = review_service.submit_agent_review(
        {
            "event_id": "evt-1",
            "sop_id": "SOP-01",
            "evidence_pack_path": str(evidence_path),
            "work_order_code": "FA260901001",
            "station": {"station_code": "3001A", "station_name": "江宁九龙湖"},
            "pollutants": ["NO"],
            "gates": {"M1": {"status": "pass", "basis": "对象一致", "scope": "core"}},
            "data_impact": [],
            "work_order_decision": "approve",
            "review_comment": "ok",
        }
    )
    user = CurrentUser(id="u1", username="auditor", display_name="Auditor")

    evidence_response = await review_routes.get_work_order_review_evidence(review["review_id"], user=user)
    attachment = evidence_response["evidence"]["work_order"]["detail"]["data"][0]["attachments"][0]
    assert attachment["content_url"].endswith("/attachments/0/content")
    assert attachment["download_url"] == attachment["content_url"]
    assert attachment["preview_url"] == attachment["content_url"]

    file_response = await review_routes.get_work_order_review_attachment_content(review["review_id"], 0, user=user)
    assert Path(file_response.path).read_bytes() == image_bytes
    assert file_response.media_type == expected_media_type
    assert file_response.headers["content-disposition"].startswith("inline;")
    assert file_response.headers["x-content-type-options"] == "nosniff"
