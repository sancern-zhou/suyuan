from pathlib import Path


def test_tender_migration_creates_required_tables_and_unique_indexes():
    sql = Path("backend/migrations/create_tender_information_tables.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE tender_candidates" in sql
    assert "CREATE TABLE tender_notices" in sql
    assert "CREATE TABLE tender_fetch_runs" in sql
    assert "UX_tender_candidates_url" in sql
    assert "UX_tender_notices_url" in sql
