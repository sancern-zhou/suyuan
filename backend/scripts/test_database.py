"""
数据库连接和数据写入测试脚本

功能：
1. 测试数据库连接
2. 测试写入 ERA5 数据
3. 测试写入观测数据
4. 测试查询功能
5. 测试 Repository 层功能

使用方法：
    python scripts/test_database.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import engine
from app.db.repositories.weather_repo import WeatherRepository
from app.external_apis.openmeteo_client import OpenMeteoClient
from sqlalchemy import text
import structlog

logger = structlog.get_logger()


async def test_connection():
    """测试数据库连接"""
    logger.info("test_connection_started")

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = (await result.fetchone())[0]
            logger.info("connection_successful", version=version[:50])

            # 检查 TimescaleDB
            result = await conn.execute(
                text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'")
            )
            has_timescaledb = (await result.fetchone())[0] > 0
            logger.info("timescaledb_check", installed=has_timescaledb)

            return True

    except Exception as e:
        logger.error("connection_failed", error=str(e))
        return False


async def test_weather_stations():
    """测试气象站查询"""
    logger.info("test_weather_stations_started")

    try:
        repo = WeatherRepository()
        stations = await repo.get_active_stations()

        logger.info(
            "stations_query_successful",
            count=len(stations),
            stations=[
                {"id": s.station_id, "name": s.station_name, "lat": s.lat, "lon": s.lon}
                for s in stations
            ]
        )

        return len(stations) > 0

    except Exception as e:
        logger.error("stations_query_failed", error=str(e))
        return False


async def test_era5_write():
    """测试 ERA5 数据写入"""
    logger.info("test_era5_write_started")

    try:
        # 使用第一个站点作为测试
        repo = WeatherRepository()
        stations = await repo.get_active_stations()

        if not stations:
            logger.error("no_stations_found")
            return False

        station = stations[0]
        logger.info("using_station", station=station.station_name, lat=station.lat, lon=station.lon)

        # 获取昨天的数据
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 调用 Open-Meteo API
        client = OpenMeteoClient()
        data = await client.fetch_era5_data(
            lat=station.lat,
            lon=station.lon,
            start_date=yesterday,
            end_date=yesterday
        )

        logger.info("api_data_fetched", hourly_points=len(data.get("hourly", {}).get("time", [])))

        # 写入数据库
        records_saved = await repo.save_era5_data(
            lat=station.lat,
            lon=station.lon,
            data=data
        )

        logger.info("era5_write_successful", records=records_saved)
        return records_saved > 0

    except Exception as e:
        logger.error("era5_write_failed", error=str(e), exc_info=True)
        return False


async def test_observed_write():
    """测试观测数据写入"""
    logger.info("test_observed_write_started")

    try:
        # 使用第一个站点作为测试
        repo = WeatherRepository()
        stations = await repo.get_active_stations()

        if not stations:
            logger.error("no_stations_found")
            return False

        station = stations[0]
        logger.info("using_station", station=station.station_name, lat=station.lat, lon=station.lon)

        # 调用 Open-Meteo API 获取当前天气
        client = OpenMeteoClient()
        data = await client.fetch_current_weather(lat=station.lat, lon=station.lon)

        logger.info("current_weather_fetched", data_keys=list(data.keys()))

        # 构造观测数据点（需要导入 ObservedDataPoint）
        from app.fetchers.weather.observed_fetcher import ObservedDataPoint

        current = data.get("current", {})
        time_str = current.get("time")

        if not time_str:
            logger.error("no_time_in_data")
            return False

        data_point = ObservedDataPoint(
            station_id=station.station_id,
            time=datetime.fromisoformat(time_str.replace("Z", "+00:00")),
            temperature_2m=current.get("temperature_2m"),
            relative_humidity_2m=current.get("relative_humidity_2m"),
            dew_point_2m=current.get("dew_point_2m"),
            wind_speed_10m=current.get("wind_speed_10m"),
            wind_direction_10m=current.get("wind_direction_10m"),
            surface_pressure=current.get("surface_pressure"),
            precipitation=current.get("precipitation"),
            cloud_cover=current.get("cloud_cover"),
            data_source="Open-Meteo",
            data_quality="good"
        )

        # 写入数据库
        success = await repo.save_observed_data(data_point)

        logger.info("observed_write_result", success=success)
        return success

    except Exception as e:
        logger.error("observed_write_failed", error=str(e), exc_info=True)
        return False


async def test_era5_query():
    """测试 ERA5 数据查询"""
    logger.info("test_era5_query_started")

    try:
        repo = WeatherRepository()
        stations = await repo.get_active_stations()

        if not stations:
            logger.error("no_stations_found")
            return False

        station = stations[0]

        # 查询昨天的数据
        yesterday_start = datetime.now() - timedelta(days=1)
        yesterday_start = yesterday_start.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start + timedelta(days=1)

        data = await repo.get_weather_data(
            lat=station.lat,
            lon=station.lon,
            start_time=yesterday_start,
            end_time=yesterday_end
        )

        logger.info("era5_query_successful", records=len(data))

        if data:
            first = data[0]
            logger.info(
                "sample_data",
                time=first.time.isoformat(),
                temp=first.temperature_2m,
                wind=first.wind_speed_10m
            )

        return len(data) > 0

    except Exception as e:
        logger.error("era5_query_failed", error=str(e))
        return False


async def test_observed_query():
    """测试观测数据查询"""
    logger.info("test_observed_query_started")

    try:
        repo = WeatherRepository()
        stations = await repo.get_active_stations()

        if not stations:
            logger.error("no_stations_found")
            return False

        station = stations[0]

        # 查询今天的数据
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        data = await repo.get_observed_data(
            station_id=station.station_id,
            start_time=today_start,
            end_time=today_end
        )

        logger.info("observed_query_successful", records=len(data))

        if data:
            first = data[0]
            logger.info(
                "sample_data",
                time=first.time.isoformat(),
                temp=first.temperature_2m,
                station=first.station_id
            )

        return True  # 可能没有数据，所以不检查数量

    except Exception as e:
        logger.error("observed_query_failed", error=str(e))
        return False


async def main():
    """主函数：运行所有测试"""
    logger.info("database_tests_started")

    tests = [
        ("数据库连接", test_connection),
        ("气象站查询", test_weather_stations),
        ("ERA5数据写入", test_era5_write),
        ("观测数据写入", test_observed_write),
        ("ERA5数据查询", test_era5_query),
        ("观测数据查询", test_observed_query),
    ]

    results = {}

    for test_name, test_func in tests:
        logger.info("running_test", test=test_name)
        try:
            result = await test_func()
            results[test_name] = "✅ 通过" if result else "❌ 失败"
        except Exception as e:
            results[test_name] = f"❌ 异常: {str(e)}"
            logger.error("test_exception", test=test_name, error=str(e))

    # 打印测试结果
    logger.info("=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    for test_name, result in results.items():
        logger.info(f"{test_name}: {result}")

    # 统计
    passed = sum(1 for r in results.values() if "✅" in r)
    total = len(results)

    logger.info("=" * 60)
    logger.info(f"通过: {passed}/{total}")
    logger.info("=" * 60)

    await engine.dispose()

    # 返回退出码
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
