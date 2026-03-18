"""
验证未来7天预报数据获取
"""
import asyncio
import sys
from datetime import date, timedelta

sys.path.insert(0, 'D:\\溯源\\backend')

from app.db.database import async_session
from app.db.models import AirQualityForecast
from sqlalchemy import select, and_


async def test_forecast_data():
    """测试未来7天预报数据查询"""

    print("=" * 80)
    print("验证未来7天预报数据获取")
    print("=" * 80)

    today = date.today()
    end_date = today + timedelta(days=6)

    print(f"\n查询时间范围:")
    print(f"  开始日期: {today} ({today.strftime('%Y-%m-%d')})")
    print(f"  结束日期: {end_date} ({end_date.strftime('%Y-%m-%d')})")
    print(f"  共计天数: {(end_date - today).days + 1} 天")

    async with async_session() as session:
        # 查询所有数据源
        print("\n" + "=" * 80)
        print("测试1: 查询所有数据源的预报数据")
        print("=" * 80)

        all_sources_query = select(AirQualityForecast).where(
            and_(
                AirQualityForecast.forecast_date >= today,
                AirQualityForecast.forecast_date <= end_date
            )
        ).order_by(AirQualityForecast.forecast_date, AirQualityForecast.source)

        all_result = await session.execute(all_sources_query)
        all_rows = all_result.scalars().all()

        print(f"\n所有数据源总计: {len(all_rows)} 条记录")

        # 按数据源和日期分组
        source_date_counts = {}
        for row in all_rows:
            source = row.source or "unknown"
            date_str = row.forecast_date.strftime("%Y-%m-%d")
            key = f"{source}:{date_str}"
            source_date_counts[key] = source_date_counts.get(key, 0) + 1

        # 按数据源统计
        source_stats = {}
        date_stats = {}

        for row in all_rows:
            source = row.source or "unknown"
            date_str = row.forecast_date.strftime("%Y-%m-%d")

            source_stats[source] = source_stats.get(source, 0) + 1
            date_stats[date_str] = date_stats.get(date_str, 0) + 1

        print(f"\n按数据源统计:")
        for source, count in sorted(source_stats.items()):
            print(f"  {source}: {count} 条")

        print(f"\n按日期统计:")
        for date_str, count in sorted(date_stats.items()):
            print(f"  {date_str}: {count} 条")

        # 查询指定数据源
        print("\n" + "=" * 80)
        print("测试2: 查询指定数据源的预报数据（qweather, waqi, combined, open-meteo, sql-server）")
        print("=" * 80)

        allowed_sources = ["qweather", "waqi", "combined", "open-meteo", "sql-server"]
        specific_query = select(AirQualityForecast).where(
            and_(
                AirQualityForecast.forecast_date >= today,
                AirQualityForecast.forecast_date <= end_date,
                AirQualityForecast.source.in_(allowed_sources)
            )
        ).order_by(AirQualityForecast.forecast_date)

        specific_result = await session.execute(specific_query)
        specific_rows = specific_result.scalars().all()

        print(f"\n指定数据源总计: {len(specific_rows)} 条记录")

        if specific_rows:
            print(f"\n预报日期列表:")
            dates_seen = set()
            for row in specific_rows:
                date_str = row.forecast_date.strftime("%Y-%m-%d")
                if date_str not in dates_seen:
                    dates_seen.add(date_str)
                    # 获取该日期的所有数据源
                    date_sources = set()
                    for r in specific_rows:
                        if r.forecast_date.strftime("%Y-%m-%d") == date_str:
                            date_sources.add(r.source)

                    print(f"  {date_str}: 数据源={', '.join(sorted(date_sources))}")

                    # 显示第一条记录的详细信息
                    for r in specific_rows:
                        if r.forecast_date.strftime("%Y-%m-%d") == date_str:
                            aqi = r.calculated_aqi if r.calculated_aqi is not None else r.aqi
                            primary = r.calculated_primary_pollutant if r.calculated_primary_pollutant else r.primary_pollutant
                            print(f"    示例: AQI={aqi}, 首要污染物={primary}, source={r.source}")
                            break

            # 检查是否有今天的数据
            today_str = today.strftime("%Y-%m-%d")
            if today_str in dates_seen:
                print(f"\n[OK] 包含今天({today_str})的预报数据")
            else:
                print(f"\n[WARNING] 缺少今天({today_str})的预报数据")

            # 检查数据完整性
            expected_dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
            missing_dates = [d for d in expected_dates if d not in dates_seen]

            if not missing_dates:
                print(f"[OK] 未来7天数据完整: {len(dates_seen)}/7 天")
            else:
                print(f"[WARNING] 缺少以下日期的数据: {', '.join(missing_dates)}")
                print(f"  实际有数据: {len(dates_seen)}/7 天")
        else:
            print("\n[ERROR] 未查询到任何预报数据")
            print("可能原因:")
            print("  1. 数据库中没有对应日期范围的数据")
            print("  2. 数据源的source字段值不在允许列表中")
            print("  3. 数据库连接问题")

        # 检查数据库中实际存在的source值
        print("\n" + "=" * 80)
        print("测试3: 检查数据库中实际存在的source值")
        print("=" * 80)

        from sqlalchemy import func
        source_query = select(AirQualityForecast.source, func.count(AirQualityForecast.id)).where(
            and_(
                AirQualityForecast.forecast_date >= today,
                AirQualityForecast.forecast_date <= end_date
            )
        ).group_by(AirQualityForecast.source)

        source_result = await session.execute(source_query)
        source_counts = source_result.all()

        print(f"\n数据库中实际存在的source值:")
        for source, count in source_counts:
            print(f"  '{source}': {count} 条")

        # 显示数据明细
        if specific_rows:
            print("\n" + "=" * 80)
            print("测试4: 显示详细数据（前10条）")
            print("=" * 80)

            for i, row in enumerate(specific_rows[:10], 1):
                aqi = row.calculated_aqi if row.calculated_aqi is not None else row.aqi
                primary = row.calculated_primary_pollutant if row.calculated_primary_pollutant else row.primary_pollutant

                pollutants_info = ""
                if row.pollutants:
                    pollutants = row.pollutants if isinstance(row.pollutants, dict) else {}
                    pm25 = pollutants.get("pm25")
                    pm10 = pollutants.get("pm10")
                    if pm25 or pm10:
                        pollutants_info = f", PM2.5={pm25}, PM10={pm10}"

                print(f"\n{i}. {row.forecast_date} | {row.source}")
                print(f"   AQI={aqi}, 首要污染物={primary}{pollutants_info}")


if __name__ == "__main__":
    asyncio.run(test_forecast_data())
