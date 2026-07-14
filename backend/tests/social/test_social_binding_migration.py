from pathlib import Path


def test_social_binding_migration_preserves_legacy_rows_and_adds_unique_active_indexes():
    sql = Path("backend/app/db/migrations/007_add_platform_social_bindings.sql").read_text()

    assert "ADD COLUMN IF NOT EXISTS platform_user_id" in sql
    assert "CREATE TABLE IF NOT EXISTS weixin_scan_tasks" in sql
    assert "WHERE status = 'active'" in sql
    assert "UPDATE social_users SET platform_user_id" not in sql
