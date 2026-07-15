from pathlib import Path

import pytest

from app.db.database import _ensure_session_resource_manifest_schema


def test_manifest_migration_is_independent_and_bounded():
    sql = Path("app/db/migrations/008_create_session_resource_manifests.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS session_resource_manifests" in sql
    assert "session_id VARCHAR(255) PRIMARY KEY" in sql
    assert "resource_refs JSONB NOT NULL" in sql
    assert "FOREIGN KEY" not in sql.upper()


@pytest.mark.asyncio
async def test_startup_ensures_manifest_schema_for_postgresql():
    statements = []

    class Connection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        async def execute(self, statement):
            statements.append(str(statement))

    await _ensure_session_resource_manifest_schema(Connection())
    joined = "\n".join(statements)
    assert "session_resource_manifests" in joined
    assert "FOREIGN KEY" not in joined.upper()
