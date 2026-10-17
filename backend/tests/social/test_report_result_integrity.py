from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import insert

from app.social import report_service
from app.social.report_models import SocialReportResult
from app.social.targeted_broadcast_service import TargetedSocialBroadcastService


@pytest.mark.asyncio
async def test_report_cursor_handles_equal_times_and_rejects_other_owner(social_mapping_db, monkeypatch):
    monkeypatch.setattr(report_service, "async_session", social_mapping_db)
    async with social_mapping_db() as db:
        for key, owner in [("a", "owner"), ("b", "owner"), ("c", "other")]:
            await db.execute(insert(SocialReportResult).values(
                report_id=key, owner_user_id=owner, task_id=key, execution_id=key,
                task_name=key, title=key, generated_at=datetime(2026, 10, 17),
            ))
        await db.commit()
    page1 = await report_service.list_report_results("owner", limit=1)
    page2 = await report_service.list_report_results("owner", limit=1, before=page1[0].report_id)
    assert [page1[0].report_id, page2[0].report_id] == ["b", "a"]
    assert await report_service.list_report_results("owner", limit=1, before="c") == []


@pytest.mark.asyncio
async def test_report_attachment_is_copied_and_independent_of_working_directory(tmp_path, monkeypatch):
    from app.social import targeted_broadcast_service as service
    source = tmp_path / "source.pdf"
    source.write_bytes(b"original")
    registry = tmp_path / "registry"
    monkeypatch.setattr(service, "get_data_registry", lambda: registry)
    monkeypatch.setattr(service, "resolve_agent_path", lambda value: source.resolve())
    captured = []
    async def publish(**kwargs): captured.append(kwargs)
    monkeypatch.setattr(report_service, "publish_report_results", publish)
    args = dict(context_metadata={"report_type": "daily", "execution_id": "execution"},
                recipients=["app:android:alice"], message="report", media=["backend/reports/source.pdf"])
    await TargetedSocialBroadcastService._publish_report_if_requested(**args)
    target = Path(captured[0]["attachments"][0]["path"])
    assert target.is_absolute() and target.is_relative_to(registry)
    assert target.read_bytes() == b"original"
    source.write_bytes(b"changed")
    await TargetedSocialBroadcastService._publish_report_if_requested(**args)
    assert target.read_bytes() == b"original"
