"""
Database connection and session management for PostgreSQL + TimescaleDB.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from typing import AsyncGenerator
import os
from dotenv import load_dotenv
import structlog
import asyncio
from app.kingbase_dialect import register_kingbase_dialect

load_dotenv()
register_kingbase_dialect()
logger = structlog.get_logger()

# Database URL from environment
def _normalize_async_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


DATABASE_URL = _normalize_async_database_url(
    os.getenv("DATABASE_URL")
    or "postgresql+asyncpg://user:password@localhost:5432/weather_db"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_size=20,        # 增加到20个连接（支持更多并发查询）
    max_overflow=30,     # 增加到30个溢出连接（峰值时最多50个连接）
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=300,    # Recycle connections after 5 minutes
    pool_timeout=120,    # 增加到120秒（给更多时间等待连接）
    connect_args={
        "command_timeout": 300,  # 5 minutes command timeout for long operations
        "server_settings": {
            "statement_timeout": "300000",  # 5 minutes in milliseconds
        }
    }
)

# Create async session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for all models
Base = declarative_base()


def _schema_init_lock_sql(dialect_name: str) -> str | None:
    """Serialize schema initialization across multi-worker process startup."""
    if dialect_name == "postgresql":
        return "SELECT pg_advisory_xact_lock(hashtext('suyuan_schema_init'))"
    return None


def _uploaded_files_session_id_alter_sql(dialect_name: str) -> str | None:
    """Return dialect-specific SQL for widening uploaded_files.session_id."""
    if dialect_name == "postgresql":
        return "ALTER TABLE uploaded_files ALTER COLUMN session_id TYPE VARCHAR(255)"
    if dialect_name in {"mysql", "mariadb"}:
        return "ALTER TABLE uploaded_files MODIFY session_id VARCHAR(255)"
    return None


async def _ensure_uploaded_files_schema(conn) -> None:
    """Apply lightweight compatibility fixes for existing uploaded_files tables."""
    sql = _uploaded_files_session_id_alter_sql(conn.dialect.name)
    if not sql:
        return

    try:
        await conn.execute(text(sql))
        logger.info("uploaded_files_session_id_column_ensured", dialect=conn.dialect.name)
    except Exception as exc:
        message = str(exc).lower()
        if "uploaded_files" in message and ("does not exist" in message or "undefinedtable" in message):
            return
        logger.warning("uploaded_files_session_id_column_migration_failed", error=str(exc))


async def _ensure_social_binding_schema(conn) -> None:
    """Apply compatibility fixes for social binding tables."""
    if conn.dialect.name != "postgresql":
        return

    statements = (
        """
        ALTER TABLE social_users
            ADD COLUMN IF NOT EXISTS platform_user_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS platform_username VARCHAR(255),
            ADD COLUMN IF NOT EXISTS platform_display_name VARCHAR(255),
            ADD COLUMN IF NOT EXISTS account_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS ilink_user_id VARCHAR(255)
        """,
        """
        CREATE TABLE IF NOT EXISTS weixin_scan_tasks (
            id VARCHAR(36) PRIMARY KEY,
            account_id VARCHAR(255) NOT NULL UNIQUE,
            owner_user_id VARCHAR(255) NOT NULL,
            owner_username VARCHAR(255) NOT NULL,
            owner_display_name VARCHAR(255) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'created',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_weixin_scan_tasks_owner_status
            ON weixin_scan_tasks(owner_user_id, status)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_social_users_active_platform_user
            ON social_users(platform_user_id)
            WHERE status = 'active' AND platform_user_id IS NOT NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_social_users_active_ilink_user
            ON social_users(ilink_user_id)
            WHERE status = 'active' AND ilink_user_id IS NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_social_users_active_account
            ON social_users(account_id, status)
        """,
    )
    for statement in statements:
        await conn.execute(text(statement))

    logger.info("social_binding_schema_ensured", dialect=conn.dialect.name)


async def _ensure_session_resources_schema(conn) -> None:
    """Create the grouped resource delivery schema for a clean database."""
    if conn.dialect.name != "postgresql":
        return
    statements = (
        """
        CREATE TABLE IF NOT EXISTS session_resources (
            resource_id VARCHAR(64) PRIMARY KEY,
            session_id VARCHAR(255) NOT NULL,
            group_id VARCHAR(64) NOT NULL,
            parent_resource_id VARCHAR(64)
                REFERENCES session_resources(resource_id) ON DELETE CASCADE,
            resource_key VARCHAR(255) NOT NULL,
            relation VARCHAR(32) NOT NULL,
            kind VARCHAR(32) NOT NULL,
            role VARCHAR(32) NOT NULL,
            label VARCHAR(512) NOT NULL,
            locator JSONB NOT NULL,
            format VARCHAR(64) NOT NULL,
            media_type VARCHAR(255) NOT NULL,
            renderer VARCHAR(64) NOT NULL,
            capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            tool_name VARCHAR(255) NOT NULL DEFAULT '',
            run_id VARCHAR(255) NOT NULL,
            turn_sequence INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (session_id, group_id, version, resource_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS session_resource_versions (
            session_id VARCHAR(255) PRIMARY KEY,
            version INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_session_resources_catalog
            ON session_resources(session_id, status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_session_resources_group
            ON session_resources(session_id, group_id, version)
        """,
    )
    for statement in statements:
        await conn.execute(text(statement))
    logger.info("session_resources_schema_ensured")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints to get database session.

    Usage:
        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            # Use db session
            pass
    """
    # 记录连接池状态
    pool_status = engine.pool.status()
    logger.debug(
        "db_connection_requested",
        pool_status=pool_status,
        pool_size=engine.pool.size(),
        checked_out=engine.pool.checkedout(),
        overflow=engine.pool.overflow(),
        queue_size=engine.pool._queue.qsize() if hasattr(engine.pool, '_queue') else 'N/A'
    )

    async with async_session() as session:
        try:
            yield session
            # 尝试commit，但如果连接已断开则忽略（长时间操作可能导致连接超时）
            try:
                await session.commit()
                logger.debug("db_session_committed")
            except Exception as commit_error:
                # 如果是连接断开的错误，记录日志但不抛出（service层可能已经用新session处理了）
                if "closed" in str(commit_error).lower() or "InterfaceError" in str(type(commit_error).__name__):
                    logger.warning("db_connection_closed_on_commit", error=str(commit_error))
                else:
                    logger.error(
                        "db_commit_failed",
                        error=str(commit_error),
                        error_type=type(commit_error).__name__
                    )
                    raise
        except Exception as e:
            logger.error(
                "db_session_error",
                error=str(e),
                error_type=type(e).__name__,
                pool_status=engine.pool.status()
            )
            try:
                await session.rollback()
                logger.debug("db_session_rolled_back")
            except Exception as rollback_error:
                logger.warning(
                    "db_rollback_failed",
                    error=str(rollback_error)
                )
                pass  # 连接已断开，无法rollback
            raise
        finally:
            # 记录连接归还后的状态
            logger.debug(
                "db_connection_returned",
                pool_status=engine.pool.status()
            )


async def init_db():
    """
    Initialize database tables.
    Should be called on application startup.
    """
    # Import optional model modules so their tables are registered on Base.metadata
    # before create_all runs.
    import app.social.models  # noqa: F401
    # Web Agent conversation persistence uses SessionDB / SessionMessageDB.
    # Import it before create_all so isolated project databases receive the
    # required `sessions` tables on their first startup as well.
    # Session persistence historically owns a separate SQLAlchemy Base, so it
    # must be initialized explicitly in addition to the application Base.
    import app.db.models_session as session_models
    import app.knowledge_base.models  # noqa: F401
    import app.knowledge_base.graph_models  # noqa: F401
    import app.knowledge_base.graph_build_models  # noqa: F401
    import app.boards.models  # noqa: F401
    import app.exam.models  # noqa: F401

    async with engine.begin() as conn:
        dialect_name = getattr(getattr(conn, "dialect", None), "name", "")
        lock_sql = _schema_init_lock_sql(dialect_name)
        if lock_sql:
            await conn.execute(text(lock_sql))
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(session_models.Base.metadata.create_all)
        await _ensure_uploaded_files_schema(conn)
        await _ensure_social_binding_schema(conn)
        await _ensure_session_resources_schema(conn)
    logger.info("database_initialized")


async def check_db_connection() -> None:
    """Verify database availability without mutating the schema."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db():
    """
    Close database connections.
    Should be called on application shutdown.
    """
    try:
        # 尝试优雅关闭连接池（最多等待10秒）
        await asyncio.wait_for(engine.dispose(), timeout=10.0)
        logger.info("database_closed")
    except asyncio.TimeoutError:
        logger.warning("database_close_timeout", message="Database close timed out, forcing disposal")
        # 超时后尝试强制关闭（忽略错误）
        try:
            engine.dispose(close=True)  # ✅ 修复：使用正确的参数名
        except Exception as e:
            logger.warning("database_force_close_failed", error=str(e))
    except Exception as e:
        logger.error("database_close_failed", error=str(e), exc_info=True)
