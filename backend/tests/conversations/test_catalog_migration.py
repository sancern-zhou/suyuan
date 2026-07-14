from pathlib import Path


MIGRATION = Path("backend/app/db/migrations/006_create_conversation_catalog.sql")


def test_catalog_migration_is_idempotent_and_backfills_required_sources():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS conversation_catalog" in sql
    assert "ON CONFLICT (session_id) DO NOTHING" in sql
    assert "FROM sessions" in sql
    assert "FROM knowledge_conversation_sessions" in sql
    assert "'1', 'ScGuanLy', '超级管理员'" in sql
    assert "WHERE user_id IS NULL" in sql
    assert "BTRIM(user_id) = ''" in sql
    assert "social_session_mappings" not in sql


def test_catalog_migration_enforces_source_and_owner_indexes():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CHECK (source IN ('web', 'knowledge_qa', 'social'))" in sql
    assert "ix_conversation_catalog_owner_updated" in sql
    assert "ix_conversation_catalog_source_updated" in sql
