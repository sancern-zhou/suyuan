from pathlib import Path

import pytest

from app.db.database import _ensure_session_resources_schema


REQUIRED_RESOURCE_COLUMNS = (
    "resource_id",
    "session_id",
    "group_id",
    "parent_resource_id",
    "resource_key",
    "relation",
    "kind",
    "role",
    "label",
    "locator",
    "format",
    "media_type",
    "renderer",
    "capabilities",
    "version",
    "status",
)


@pytest.mark.asyncio
async def test_startup_schema_creates_grouped_resource_delivery_table():
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
    normalized = " ".join(create_table.lower().split())
    for column in REQUIRED_RESOURCE_COLUMNS:
        assert column in normalized
    assert "presentation_type" not in normalized
    assert " presentation " not in f" {normalized} "
    assert "logical_key" not in normalized


def test_hard_cutover_migration_has_grouped_resource_schema():
    backend_root = Path(__file__).resolve().parents[2]
    migration = (
        backend_root / "app/db/migrations/014_hard_cutover_resource_delivery.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.upper().split())

    for column in (
        "GROUP_ID",
        "PARENT_RESOURCE_ID",
        "RELATION",
        "FORMAT",
        "MEDIA_TYPE",
        "RENDERER",
        "CAPABILITIES",
        "VERSION",
    ):
        assert column in normalized
    assert "DROP TABLE IF EXISTS SESSION_RESOURCE_MANIFESTS" in normalized
    assert "DROP COLUMN IF EXISTS DATA_IDS" in normalized
    assert "DROP COLUMN IF EXISTS VISUAL_IDS" in normalized
    assert "DROP COLUMN IF EXISTS OFFICE_DOCUMENTS" in normalized
    assert "DROP TABLE IF EXISTS SESSION_RESOURCES" in normalized
