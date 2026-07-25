from pathlib import Path

import pytest

from app.db.database import _ensure_session_resources_schema

OPTIONAL_RESOURCE_COLUMNS = ("logical_key", "presentation_type", "presentation")


@pytest.mark.asyncio
async def test_startup_schema_keeps_non_presented_resource_fields_nullable():
    statements: list[str] = []

    class Connection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        async def execute(self, statement):
            statements.append(str(statement))

    await _ensure_session_resources_schema(Connection())

    create_table = next(
        statement
        for statement in statements
        if "CREATE TABLE IF NOT EXISTS session_resources" in statement
    )
    column_lines = {
        line.strip().split(maxsplit=1)[0]: line.strip()
        for line in create_table.splitlines()
        if line.strip()
    }

    for column in OPTIONAL_RESOURCE_COLUMNS:
        assert "NOT NULL" not in column_lines[column]


def test_nullable_resource_fields_have_an_idempotent_repair_migration():
    backend_root = Path(__file__).resolve().parents[2]
    migration = (
        backend_root / "app/db/migrations/012_allow_non_presented_session_resources.sql"
    ).read_text(encoding="utf-8")

    normalized = " ".join(migration.upper().split())
    assert "ALTER TABLE IF EXISTS SESSION_RESOURCES" in normalized
    for column in OPTIONAL_RESOURCE_COLUMNS:
        assert f"ALTER COLUMN {column.upper()} DROP NOT NULL" in normalized
