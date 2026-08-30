from app.db.database import (
    _normalize_async_database_url,
    _resolve_session_database_url,
    session_engine,
    _schema_init_lock_sql,
)


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


def test_session_database_prefers_explicit_url():
    assert _resolve_session_database_url("shared", "local", "session") == "session"


def test_session_database_defaults_to_project_local_url():
    assert _resolve_session_database_url("shared", "local", None) == "local"


def test_session_database_uses_shared_url_without_a_local_store():
    assert _resolve_session_database_url("shared", None, None) == "shared"


def test_session_repositories_share_the_dedicated_engine():
    from app.conversations.repository import ConversationCatalogRepository
    from app.db.database import session_async_session
    from app.db.session_repository import SessionRepository
    from app.db.session_resources_repository import SessionResourcesRepository

    assert SessionRepository().engine is session_engine
    assert SessionResourcesRepository().engine is session_engine
    assert ConversationCatalogRepository().session_factory is session_async_session
