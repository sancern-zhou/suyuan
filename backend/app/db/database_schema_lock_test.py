from app.db.database import _normalize_async_database_url, _schema_init_lock_sql


def test_postgres_schema_initialization_uses_transaction_advisory_lock():
    assert _schema_init_lock_sql("postgresql") == (
        "SELECT pg_advisory_xact_lock(hashtext('suyuan_schema_init'))"
    )


def test_non_postgres_schema_initialization_needs_no_advisory_lock():
    assert _schema_init_lock_sql("sqlite") is None


def test_plain_postgresql_url_is_normalized_for_async_engine():
    assert (
        _normalize_async_database_url("postgresql://user:pass@localhost/db")
        == "postgresql+asyncpg://user:pass@localhost/db"
    )
