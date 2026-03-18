"""
Database Initialization Script.

Creates tables and TimescaleDB hypertables for meteorological data storage.

Requirements:
1. PostgreSQL 14+ with TimescaleDB extension installed
2. Database created: CREATE DATABASE weather_db;
3. TimescaleDB extension enabled: CREATE EXTENSION IF NOT EXISTS timescaledb;

Usage:
    python init_db.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import engine, Base
from app.db.models import ERA5ReanalysisData, ObservedWeatherData, WeatherStation, WeatherDataCache
from sqlalchemy import text
import structlog

logger = structlog.get_logger()


async def create_timescale_extension():
    """Enable TimescaleDB extension."""
    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            logger.info("timescaledb_extension_enabled")
        except Exception as e:
            logger.error("timescaledb_extension_failed", error=str(e))
            logger.warning("continuing_without_timescaledb")


async def create_tables():
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("tables_created")


async def create_hypertables():
    """
    Convert tables to TimescaleDB hypertables.

    This enables automatic partitioning and compression for time-series data.
    """
    async with engine.begin() as conn:
        try:
            # Convert ERA5 table to hypertable
            await conn.execute(text("""
                SELECT create_hypertable(
                    'era5_reanalysis_data',
                    'time',
                    chunk_time_interval => INTERVAL '1 month',
                    if_not_exists => TRUE
                )
            """))
            logger.info("hypertable_created", table="era5_reanalysis_data")

            # Convert Observed Weather table to hypertable
            await conn.execute(text("""
                SELECT create_hypertable(
                    'observed_weather_data',
                    'time',
                    chunk_time_interval => INTERVAL '1 month',
                    if_not_exists => TRUE
                )
            """))
            logger.info("hypertable_created", table="observed_weather_data")

        except Exception as e:
            logger.error("hypertable_creation_failed", error=str(e))
            logger.warning("tables_will_work_without_hypertables")


async def enable_compression():
    """
    Enable compression on hypertables to save storage space.

    TimescaleDB can compress data by 50-90%, reducing storage costs.
    Compression is applied to chunks older than 7 days.
    """
    async with engine.begin() as conn:
        try:
            # Enable compression for ERA5 data
            await conn.execute(text("""
                ALTER TABLE era5_reanalysis_data SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'lat,lon',
                    timescaledb.compress_orderby = 'time DESC'
                )
            """))
            logger.info("compression_enabled", table="era5_reanalysis_data")

            # Add compression policy (compress data older than 7 days)
            await conn.execute(text("""
                SELECT add_compression_policy(
                    'era5_reanalysis_data',
                    INTERVAL '7 days',
                    if_not_exists => TRUE
                )
            """))
            logger.info("compression_policy_added", table="era5_reanalysis_data", threshold="7 days")

            # Enable compression for Observed Weather data
            await conn.execute(text("""
                ALTER TABLE observed_weather_data SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'station_id',
                    timescaledb.compress_orderby = 'time DESC'
                )
            """))
            logger.info("compression_enabled", table="observed_weather_data")

            await conn.execute(text("""
                SELECT add_compression_policy(
                    'observed_weather_data',
                    INTERVAL '7 days',
                    if_not_exists => TRUE
                )
            """))
            logger.info("compression_policy_added", table="observed_weather_data", threshold="7 days")

        except Exception as e:
            logger.error("compression_setup_failed", error=str(e))
            logger.warning("tables_will_work_without_compression")


async def create_additional_indexes():
    """
    Create additional indexes for optimized queries.

    TimescaleDB creates some indexes automatically, but we add more for
    specific query patterns.
    """
    async with engine.begin() as conn:
        try:
            # Spatial index for ERA5 data
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_era5_spatial
                ON era5_reanalysis_data (lat, lon, time DESC)
            """))

            # Time-only index for ERA5 data
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_era5_time_only
                ON era5_reanalysis_data (time DESC)
            """))

            # Station + time index for observed data
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_observed_station_time
                ON observed_weather_data (station_id, time DESC)
            """))

            logger.info("additional_indexes_created")

        except Exception as e:
            logger.error("index_creation_failed", error=str(e))


async def insert_sample_stations():
    """
    Insert sample weather station data for testing.

    This adds a few key stations in Guangdong province.
    """
    from app.db.database import async_session
    from app.db.models import WeatherStation

    sample_stations = [
        {
            "station_id": "59287",
            "station_name": "广州",
            "lat": 23.13,
            "lon": 113.26,
            "elevation": 21.0,
            "province": "广东",
            "city": "广州",
            "station_type": "ground",
            "has_pbl_observation": False,
            "has_upper_air": True,
            "data_provider": "CMA",
            "is_active": True
        },
        {
            "station_id": "59316",
            "station_name": "深圳",
            "lat": 22.53,
            "lon": 114.05,
            "elevation": 19.0,
            "province": "广东",
            "city": "深圳",
            "station_type": "ground",
            "has_pbl_observation": False,
            "has_upper_air": False,
            "data_provider": "CMA",
            "is_active": True
        },
        {
            "station_id": "59280",
            "station_name": "东莞",
            "lat": 23.05,
            "lon": 113.75,
            "elevation": 15.0,
            "province": "广东",
            "city": "东莞",
            "station_type": "ground",
            "has_pbl_observation": False,
            "has_upper_air": False,
            "data_provider": "CMA",
            "is_active": True
        }
    ]

    async with async_session() as session:
        for station_data in sample_stations:
            # Check if station already exists
            result = await session.execute(
                text("SELECT station_id FROM weather_stations WHERE station_id = :sid"),
                {"sid": station_data["station_id"]}
            )
            if result.first():
                logger.info("station_exists", station_id=station_data["station_id"])
                continue

            station = WeatherStation(**station_data)
            session.add(station)

        await session.commit()

    logger.info("sample_stations_inserted", count=len(sample_stations))


async def verify_setup():
    """Verify database setup is working."""
    async with engine.begin() as conn:
        # Check TimescaleDB version
        result = await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"))
        version = result.scalar()
        if version:
            logger.info("timescaledb_version", version=version)
        else:
            logger.warning("timescaledb_not_installed")

        # Check hypertables
        result = await conn.execute(text("""
            SELECT hypertable_name, num_chunks
            FROM timescaledb_information.hypertables
        """))
        hypertables = result.fetchall()
        if hypertables:
            for ht in hypertables:
                logger.info("hypertable_verified", name=ht[0], chunks=ht[1])
        else:
            logger.warning("no_hypertables_found")

        # Check compression policies
        result = await conn.execute(text("""
            SELECT hypertable_name, older_than, compress_after
            FROM timescaledb_information.compression_settings
        """))
        policies = result.fetchall()
        if policies:
            for policy in policies:
                logger.info("compression_policy_verified", hypertable=policy[0])

    logger.info("database_setup_verified")


async def main():
    """Main initialization flow."""
    logger.info("starting_database_initialization")

    try:
        # Step 1: Enable TimescaleDB extension
        logger.info("step_1_enabling_timescaledb")
        await create_timescale_extension()

        # Step 2: Create tables
        logger.info("step_2_creating_tables")
        await create_tables()

        # Step 3: Convert to hypertables
        logger.info("step_3_creating_hypertables")
        await create_hypertables()

        # Step 4: Enable compression
        logger.info("step_4_enabling_compression")
        await enable_compression()

        # Step 5: Create additional indexes
        logger.info("step_5_creating_indexes")
        await create_additional_indexes()

        # Step 6: Insert sample stations
        logger.info("step_6_inserting_sample_stations")
        await insert_sample_stations()

        # Step 7: Verify setup
        logger.info("step_7_verifying_setup")
        await verify_setup()

        logger.info("database_initialization_complete", status="success")

    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        raise

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
