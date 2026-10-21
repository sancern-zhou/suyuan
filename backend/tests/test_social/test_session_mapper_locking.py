import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from app.social.models import SocialSessionMapping as Mapping
from app.social.session_mapper import SessionMapper


@pytest.mark.asyncio
async def test_instances_observe_each_others_writes_and_deletes(social_mapping_db):
    first = SessionMapper(social_mapping_db)
    second = SessionMapper(social_mapping_db)
    await first.save_mapping("app:android:A", "A")
    await second.save_mapping("app:android:B", "B")
    assert await first.get_session("app:android:B") == "B"
    assert await second.get_session("app:android:A") == "A"
    assert await first.delete_mapping("app:android:A")
    assert await second.get_session("app:android:A") is None
    assert await first.get_all_social_user_ids() == ["app:android:B"]
    assert await second.count_active() == 1
    assert (await first.list_active())[0]["session_id"] == "B"


@pytest.mark.asyncio
async def test_creation_is_atomic_and_offsets_follow_the_mapping(social_mapping_db):
    first, second = SessionMapper(social_mapping_db), SessionMapper(social_mapping_db)
    sessions = await asyncio.gather(*[
        mapper.get_or_create_session("qq:bot:user", "social") for mapper in [first, second]
    ])
    assert len(set(sessions)) == 1
    await first.update_consolidation_offset("qq:bot:user", 4, 6, expected_session_id=sessions[0])
    assert (await second.get_mapping_info("qq:bot:user"))["last_consolidated_offset"] == 4
    await second.save_mapping("qq:bot:user", "replacement")
    await first.update_consolidation_offset("qq:bot:user", 10, 10, expected_session_id=sessions[0])
    assert (await second.get_mapping_info("qq:bot:user"))["last_consolidated_offset"] == 0


@pytest.mark.asyncio
async def test_expiration_renews_non_app_session_and_cleans_database(social_mapping_db):
    mapper = SessionMapper(social_mapping_db)
    for identity in ["qq:bot:user", "app:android:alice"]:
        await mapper.save_mapping(identity, "old")
    async with social_mapping_db() as db:
        await db.execute(update(Mapping).values(last_used=datetime.now() - timedelta(days=30)))
        await db.commit()
    assert await mapper.get_session("qq:bot:user") is None
    assert await mapper.get_session("app:android:alice") == "old"
    assert await mapper.get_or_create_session("qq:bot:user", "social") != "old"
    async with social_mapping_db() as db:
        await db.execute(update(Mapping).values(last_used=datetime.now() - timedelta(days=30)))
        await db.commit()
    assert await mapper.cleanup_expired() == 1
    assert await mapper.get_session("app:android:alice") == "old"


@pytest.mark.asyncio
async def test_failed_database_never_falls_back_to_local_files():
    def unavailable():
        raise RuntimeError("database unavailable")
    mapper = SessionMapper(unavailable)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await mapper.save_mapping("app:android:A", "A")
