"""
Database connection and session management for PostgreSQL + TimescaleDB.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
import os
from dotenv import load_dotenv
import structlog
import asyncio

load_dotenv()
logger = structlog.get_logger()

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/weather_db"
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_initialized")


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
            engine.dispose(close_wake_up=True)
        except Exception as e:
            logger.warning("database_force_close_failed", error=str(e))
    except Exception as e:
        logger.error("database_close_failed", error=str(e), exc_info=True)
