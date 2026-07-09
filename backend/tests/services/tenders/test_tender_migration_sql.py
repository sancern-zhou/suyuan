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


def test_tender_migration_uses_compact_notice_schema():
    sql = Path("backend/migrations/create_tender_information_tables.sql").read_text(
        encoding="utf-8"
    )

    notice_table_sql = sql.split("CREATE TABLE tender_notices", 1)[1].split(");", 1)[0]

    assert "CREATE TABLE tender_notice_contents" in sql
    assert "project_category" in notice_table_sql
    assert "extraction_meta_json" in notice_table_sql
    assert "raw_content" not in notice_table_sql
    assert "structured_json" not in notice_table_sql
    assert "attachment_urls_json" not in notice_table_sql
    assert "environment_relevance" not in notice_table_sql
    assert "filter_reason" not in notice_table_sql


def test_tender_compaction_migration_moves_content_and_drops_redundant_columns():
    sql = Path("backend/migrations/compact_tender_notice_schema.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE tender_notice_contents" in sql
    assert "INSERT INTO tender_notice_contents" in sql
    assert "project_category" in sql
    assert "extraction_meta_json" in sql
    assert "DROP COLUMN" in sql
    assert "'raw_content'" in sql
    assert "'structured_json'" in sql
    assert "'filter_reason'" in sql
