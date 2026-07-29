"""SQLAlchemy dialect shim for KingbaseES PostgreSQL-compatible mode."""

from __future__ import annotations

from sqlalchemy.dialects import registry
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg


class KingbaseAsyncpgDialect(PGDialect_asyncpg):
    """PostgreSQL asyncpg dialect with KingbaseES version parsing support."""

    supports_statement_cache = True

    def _get_server_version_info(self, connection):
        version = connection.exec_driver_sql("select version()").scalar()
        if isinstance(version, str) and version.startswith("KingbaseES "):
            return (12, 0)
        return super()._get_server_version_info(connection)


def register_kingbase_dialect() -> None:
    registry.register(
        "kingbase.asyncpg",
        "app.kingbase_dialect",
        "KingbaseAsyncpgDialect",
    )
