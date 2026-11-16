from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def compile_jsonb_as_sqlite_json(type_, compiler, **kwargs):
    return "JSON"


from app.db.database import Base
from app.db.models.smart_event_db import SmartEventDB, SmartEventStateDB
from app.db.models.task_review_db import TaskReviewDB
from app.services import smart_event_db


@pytest.mark.asyncio
async def test_overview_stats_follow_all_filters_instead_of_page_or_store(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'events.db').as_posix()}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def isolated_session():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("app.db.sync_bridge.bridge_session", isolated_session)

    def event(event_id, *, name, status="待研判", event_type="数据", level="P1",
              site_id="A", site_name="甲站", response="已完成", occurred="2026-09-10T10:00:00",
              review_id=None, archived=False):
        return SmartEventDB(
            event_id=event_id,
            data={"event_id": event_id, "ai_judgment": {"final_response": response}, "review_id": review_id},
            event_name=name,
            initial_event_name=name,
            event_status=status,
            event_type=event_type,
            ai_suggested_level=level,
            site_id=site_id,
            site_name=site_name,
            latest_occurrence_time=datetime.fromisoformat(occurred) if occurred else None,
            archived=archived,
        )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[
            SmartEventDB.__table__, SmartEventStateDB.__table__, TaskReviewDB.__table__,
        ])
    try:
        async with sessions() as session:
            session.add_all([
                event("1", name="仪器波动", review_id="archived"),
                event("2", name="仪器波动", response=""),
                event("3", name="站房环境", response="", site_id="", site_name="乙站", occurred="2026-09-10T09:00:00"),
                event("4", name="历史波动", response="", site_id="C", site_name="丙站", occurred="2026-09-01T10:00:00"),
                event("5", name="其他类型", response="", event_type="运维", site_id="D", site_name="丁站"),
                event("6", name="较低等级", response="", level="P2", site_id="E", site_name="戊站"),
                event("7", name="不同关键词", response="", site_id="F", site_name="己站"),
                event("8", name="无时间波动", response="", site_id="G", site_name="庚站", occurred=None),
            ])
            session.add_all([
                TaskReviewDB(review_id="archived", subject_id="1", status="archived"),
                SmartEventStateDB(key="last_sync", value={"synced_at": "2026-09-10T10:30:00"}),
            ])
            await session.commit()

        window = {"start_time": datetime(2026, 9, 10), "end_time": datetime(2026, 9, 11)}
        overview = await smart_event_db.query_events_overview_async(
            **window, event_type="数据", level="P1", keyword="波动", limit=1, offset=0,
        )
        second_page = await smart_event_db.query_events_overview_async(
            **window, event_type="数据", level="P1", keyword="波动", limit=1, offset=1,
        )

        expected_stats = {"total": 3, "pending": 2, "stations": 2}
        assert [item["event_id"] for item in overview["events"]] == ["1"]
        assert [item["event_id"] for item in second_page["events"]] == ["2"]
        assert overview["total"] == second_page["total"] == 3
        assert overview["stats"] == second_page["stats"] == expected_stats
        assert overview["filters"] == {"statuses": ["待研判"], "types": ["数据", "运维"], "levels": ["P1", "P2"]}
        assert overview["last_sync"] == {"synced_at": "2026-09-10T10:30:00"}

        archived = await smart_event_db.query_events_overview_async(
            **window, status="已归档", keyword="波动", limit=10,
        )
        assert [item["event_id"] for item in archived["events"]] == ["1"]
        assert archived["stats"] == {"total": 1, "pending": 0, "stations": 1}

        pending = await smart_event_db.query_events_overview_async(
            **window, status="待研判", keyword="波动", station_codes=["A"], limit=10,
        )
        assert {item["event_id"] for item in pending["events"]} == {"2"}
        assert pending["stats"] == {"total": 1, "pending": 1, "stations": 1}

        no_match = await smart_event_db.query_events_overview_async(**window, keyword="不存在", limit=10)
        assert no_match["total"] == 0
        assert no_match["stats"] == {"total": 0, "pending": 0, "stations": 0}

        named_site = await smart_event_db.query_events_overview_async(**window, keyword="站房环境", limit=10)
        assert named_site["stats"] == {"total": 1, "pending": 1, "stations": 1}
        assert named_site["filters"]["types"] == ["数据", "运维"]
    finally:
        await engine.dispose()
