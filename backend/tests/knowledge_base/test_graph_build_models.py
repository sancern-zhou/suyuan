from sqlalchemy import create_engine, inspect

from app.db.database import Base
from app.knowledge_base.graph_build_models import KnowledgeGraphBuildTask


def test_graph_build_task_columns_and_defaults():
    cols = {c.name for c in KnowledgeGraphBuildTask.__table__.columns}
    assert {"id","kb_id","status","mode","created_by","created_at","started_at","completed_at","total_chunks","processed_chunks","failed_chunks","remaining_chunks","failed_chunk_ids","last_error","cancel_requested","lease_until","updated_at"} <= cols
    assert KnowledgeGraphBuildTask.__table__.c.status.default.arg == "queued"


def test_graph_build_task_sqlite_metadata_create_and_active_unique_index():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[KnowledgeGraphBuildTask.__table__])
    indexes = inspect(engine).get_indexes("knowledge_graph_build_tasks")
    assert any(i["name"] == "uq_kg_build_active_kb" for i in indexes)
