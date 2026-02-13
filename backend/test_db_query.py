"""
测试数据库查询 - 验证空气质量数据查询
"""
import asyncio
import sys
from datetime import datetime, timedelta

# 设置路径
sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from app.db.models.weather_models import AirQualityForecast, CityAQIPublishHistory
from sqlalchemy import select, and_, desc


async def test_air_quality_query():
    """测试空气质量数据查询"""
    async with async_session() as session:
        print("=" * 60)
        print("测试 1: 查询未来7天空气质量预报数据")
        print("=" * 60)

        # 查询未来7天的预报数据
        tomorrow = datetime.now().date() + timedelta(days=1)
        end_date = datetime.now().date() + timedelta(days=7)

        forecast_query = select(AirQualityForecast).where(
            and_(
                AirQualityForecast.forecast_date >= tomorrow,
                AirQualityForecast.forecast_date <= end_date
            )
        ).order_by(AirQualityForecast.forecast_date)

        forecast_result = await session.execute(forecast_query)
        forecast_records = forecast_result.scalars().all()

        print(f"找到 {len(forecast_records)} 条预报数据:")
        for record in forecast_records:
            # 使用字段优先级: calculated_aqi > aqi
            aqi = record.calculated_aqi if record.calculated_aqi is not None else record.aqi
            primary = record.calculated_primary_pollutant if record.calculated_primary_pollutant else record.primary_pollutant

            print(f"  日期: {record.forecast_date}")
            print(f"  AQI: {aqi} (优先使用calculated_aqi)")
            print(f"  首要污染物: {primary}")
            print(f"  数据源: {record.source}")
            print()

        print("=" * 60)
        print("测试 2: 查询周边城市历史12小时数据")
        print("=" * 60)

        # 查询历史12小时数据
        twelve_hours_ago = datetime.now() - timedelta(hours=12)

        # 测试查询济宁市数据（用户提供的示例）
        history_query = select(CityAQIPublishHistory).where(
            and_(
                CityAQIPublishHistory.area == "济宁市",
                CityAQIPublishHistory.time_point >= twelve_hours_ago
            )
        ).order_by(desc(CityAQIPublishHistory.time_point)).limit(5)

        history_result = await session.execute(history_query)
        history_records = history_result.scalars().all()

        print(f"找到 {len(history_records)} 条济宁市历史数据:")
        for record in history_records:
            print(f"  时间: {record.time_point}")
            print(f"  城市: {record.area} (代码: {record.city_code})")
            print(f"  AQI: {record.aqi}")
            print(f"  PM2.5: {record.pm2_5}")
            print(f"  PM10: {record.pm10}")
            print(f"  O3: {record.o3}")
            print(f"  NO2: {record.no2}")
            print(f"  SO2: {record.so2}")
            print(f"  CO: {record.co}")
            print(f"  首要污染物: {record.primary_pollutant}")
            print(f"  空气质量等级: {record.quality}")
            print()

        if len(history_records) == 0:
            print("  未找到济宁市数据，尝试查询所有城市最新数据...")
            all_query = select(CityAQIPublishHistory).order_by(
                desc(CityAQIPublishHistory.time_point)
            ).limit(5)
            all_result = await session.execute(all_query)
            all_records = all_result.scalars().all()

            print(f"  全部最新数据 (前5条):")
            for record in all_records:
                print(f"    {record.time_point} - {record.area} - AQI: {record.aqi}")


async def main():
    await test_air_quality_query()


if __name__ == "__main__":
    asyncio.run(main())
