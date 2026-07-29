import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from app.db.database import Base
from app.knowledge_base.graph_build_models import KnowledgeGraphBuildTask


def test_graph_build_task_columns_and_defaults():
    cols = {c.name for c in KnowledgeGraphBuildTask.__table__.columns}
    assert {"id","kb_id","status","mode","created_by","created_at","started_at","completed_at","total_chunks","processed_chunks","failed_chunks","remaining_chunks","failed_chunk_ids","last_error","cancel_requested","lease_until","updated_at"} <= cols
    assert KnowledgeGraphBuildTask.__table__.c.status.default.arg == "queued"
    assert KnowledgeGraphBuildTask.__table__.c.mode.default.arg == "pending"


def test_graph_build_task_sqlite_metadata_create_and_active_unique_index():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[KnowledgeGraphBuildTask.__table__])
    indexes = inspect(engine).get_indexes("knowledge_graph_build_tasks")
    assert any(i["name"] == "uq_kg_build_active_kb" for i in indexes)


def test_graph_build_task_rejects_invalid_mode_and_status():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[KnowledgeGraphBuildTask.__table__])
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(KnowledgeGraphBuildTask.__table__.insert().values(kb_id="kb", created_by="u", mode="full"))
        with pytest.raises(IntegrityError):
            conn.execute(KnowledgeGraphBuildTask.__table__.insert().values(kb_id="kb", created_by="u", status="bogus"))


def test_active_unique_allows_terminal_but_not_two_active_tasks():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[KnowledgeGraphBuildTask.__table__])
    with engine.begin() as conn:
        conn.execute(KnowledgeGraphBuildTask.__table__.insert().values(id="a", kb_id="kb", created_by="u", status="queued"))
        with pytest.raises(IntegrityError):
            conn.execute(KnowledgeGraphBuildTask.__table__.insert().values(id="b", kb_id="kb", created_by="u", status="running"))
        conn.execute(KnowledgeGraphBuildTask.__table__.insert().values(id="c", kb_id="kb", created_by="u", status="completed"))
