"""
数据库初始化脚本

功能：
1. 创建所有表结构
2. 创建 TimescaleDB hypertables（如果支持）
3. 创建索引
4. 初始化气象站数据（示例站点）

使用方法：
    python scripts/init_database.py
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.database import engine, init_db
from app.db.models import Base, WeatherStation
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
import structlog

logger = structlog.get_logger()


async def create_timescaledb_hypertables():
    """
    创建 TimescaleDB hypertables

    将普通表转换为 TimescaleDB 的时序表（hypertable）
    这样可以自动按时间分区，大幅提升查询性能
    """
    async with engine.begin() as conn:
        try:
            # 检查 TimescaleDB 扩展是否安装
            result = await conn.execute(
                text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'")
            )
            has_timescaledb = (await result.fetchone())[0] > 0

            if not has_timescaledb:
                logger.warning(
                    "timescaledb_not_installed",
                    message="TimescaleDB extension not found. Tables will be created as normal PostgreSQL tables."
                )
                return

            logger.info("timescaledb_detected", message="Creating hypertables...")

            # 创建 ERA5 hypertable（按时间分区）
            try:
                await conn.execute(text("""
                    SELECT create_hypertable(
                        'era5_reanalysis_data',
                        'time',
                        chunk_time_interval => INTERVAL '1 week',
                        if_not_exists => TRUE
                    )
                """))
                logger.info("hypertable_created", table="era5_reanalysis_data")
            except Exception as e:
                logger.warning("hypertable_creation_failed", table="era5_reanalysis_data", error=str(e))

            # 创建观测数据 hypertable
            try:
                await conn.execute(text("""
                    SELECT create_hypertable(
                        'observed_weather_data',
                        'time',
                        chunk_time_interval => INTERVAL '1 day',
                        if_not_exists => TRUE
                    )
                """))
                logger.info("hypertable_created", table="observed_weather_data")
            except Exception as e:
                logger.warning("hypertable_creation_failed", table="observed_weather_data", error=str(e))

            # 启用压缩（可选，节省存储空间）
            try:
                await conn.execute(text("""
                    ALTER TABLE era5_reanalysis_data SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'lat,lon'
                    )
                """))

                await conn.execute(text("""
                    SELECT add_compression_policy('era5_reanalysis_data', INTERVAL '7 days')
                """))
                logger.info("compression_enabled", table="era5_reanalysis_data")
            except Exception as e:
                logger.warning("compression_setup_failed", error=str(e))

        except Exception as e:
            logger.error("timescaledb_setup_failed", error=str(e))


async def init_sample_stations():
    """
    初始化示例气象站数据

    创建3个示例站点用于测试：
    - 广州天河站
    - 深圳南山站
    - 佛山顺德站
    """
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            # 示例站点数据
            sample_stations = [
                WeatherStation(
                    station_id="GZ_TIANHE_001",
                    station_name="广州天河气象站",
                    lat=23.1291,
                    lon=113.3644,
                    elevation=21.0,
                    province="广东省",
                    city="广州市",
                    station_type="ground",
                    has_pbl_observation=False,
                    has_upper_air=False,
                    data_provider="Open-Meteo",
                    is_active=True
                ),
                WeatherStation(
                    station_id="SZ_NANSHAN_001",
                    station_name="深圳南山气象站",
                    lat=22.5329,
                    lon=113.9344,
                    elevation=18.0,
                    province="广东省",
                    city="深圳市",
                    station_type="ground",
                    has_pbl_observation=False,
                    has_upper_air=False,
                    data_provider="Open-Meteo",
                    is_active=True
                ),
                WeatherStation(
                    station_id="FS_SHUNDE_001",
                    station_name="佛山顺德气象站",
                    lat=22.8055,
                    lon=113.2936,
                    elevation=5.0,
                    province="广东省",
                    city="佛山市",
                    station_type="ground",
                    has_pbl_observation=False,
                    has_upper_air=False,
                    data_provider="Open-Meteo",
                    is_active=True
                ),
            ]

            # 检查站点是否已存在
            for station in sample_stations:
                # 使用 merge 避免重复插入
                await session.merge(station)

            await session.commit()

            logger.info(
                "sample_stations_initialized",
                count=len(sample_stations),
                stations=[s.station_name for s in sample_stations]
            )

        except Exception as e:
            await session.rollback()
            logger.error("sample_stations_init_failed", error=str(e))
            raise


async def main():
    """主函数"""
    logger.info("database_initialization_started")

    try:
        # 1. 创建所有表
        logger.info("creating_tables")
        await init_db()
        logger.info("tables_created")

        # 2. 创建 TimescaleDB hypertables（如果支持）
        logger.info("setting_up_timescaledb")
        await create_timescaledb_hypertables()

        # 3. 初始化示例站点
        logger.info("initializing_sample_stations")
        await init_sample_stations()

        logger.info("database_initialization_completed", status="success")

    except Exception as e:
        logger.error("database_initialization_failed", error=str(e), exc_info=True)
        sys.exit(1)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
