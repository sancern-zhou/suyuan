import asyncio
from datetime import datetime, timedelta

import pytest

from app.social.session_mapper import SessionMapper


@pytest.mark.asyncio
async def test_expired_mapping_cleanup_does_not_reacquire_mapper_lock(tmp_path):
    mapper = SessionMapper(data_dir=str(tmp_path))
    mapper._mappings["weixin:a:bot:sender"] = "old-session"
    mapper._timestamp_cache["weixin:a:bot:sender"] = datetime.now() - timedelta(hours=25)

    result = await asyncio.wait_for(
        mapper.get_session("weixin:a:bot:sender"), timeout=0.2
    )

    assert result is None


@pytest.mark.asyncio
async def test_delete_mapping_does_not_reacquire_mapper_lock(tmp_path):
    mapper = SessionMapper(data_dir=str(tmp_path))
    mapper._mappings["sender"] = "session"

    assert await asyncio.wait_for(mapper.delete_mapping("sender"), timeout=0.2) is True


@pytest.mark.asyncio
async def test_bulk_cleanup_does_not_reacquire_mapper_lock(tmp_path):
    mapper = SessionMapper(data_dir=str(tmp_path))
    mapper._mappings["sender"] = "session"
    mapper._timestamp_cache["sender"] = datetime.now() - timedelta(hours=25)

    assert await asyncio.wait_for(mapper.cleanup_expired(), timeout=0.2) == 1
